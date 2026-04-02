from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from trader.pipeline.models import (
    CandidateSet, Candidate, Proposal, ProposalOrder, ProposalSizing,
    ProposalSet, SectorProposals, VixContext,
)
from trader.market.vix import vix_gate
from trader.strategies.factory import get_strategy, list_strategies, get_regime_thresholds
from trader.strategies.risk_filter import RiskFilter
from trader.strategies.stop_loss import (
    atr as compute_atr,
    stop_level as compute_stop,
    position_size as compute_position_size,
    regime_atr_multiplier,
)
from trader.config import Config
from trader.models import Position, Order, SentimentResult

logger = logging.getLogger(__name__)

# Hard cap: no single proposal should exceed this % of NLV
_MAX_POSITION_PCT = 10.0
# Minimum price for candidates (filter out penny stocks with unreliable signals)
_MIN_PRICE = 1.0

from trader.market.ticker_map import resolve_yf_ticker as _resolve_yf_ticker


def _fetch_ohlcv(ticker: str, period: str = "90d", interval: str = "1d") -> pd.DataFrame:
    """Fetch OHLCV data via yfinance. Separate function for easy mocking."""
    df = yf.download(_resolve_yf_ticker(ticker), period=period, interval=interval, progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [c.lower() for c in df.columns]
    return df


def _get_sector(ticker: str) -> str:
    """Look up GICS sector via yfinance info. Returns empty string on failure."""
    try:
        info = yf.Ticker(_resolve_yf_ticker(ticker)).info
        return info.get("sector", "")
    except Exception:
        return ""


def _next_monthly_expiry(min_dte: int = 30) -> str:
    """Return the next monthly options expiry (3rd Friday) at least min_dte days out."""
    target = date.today() + timedelta(days=min_dte)
    # Find 3rd Friday of target month
    first = target.replace(day=1)
    # weekday(): Monday=0 … Friday=4
    days_to_friday = (4 - first.weekday()) % 7
    third_friday = first + timedelta(days=days_to_friday + 14)
    if third_friday < target:
        # Move to next month
        if target.month == 12:
            first = target.replace(year=target.year + 1, month=1, day=1)
        else:
            first = target.replace(month=target.month + 1, day=1)
        days_to_friday = (4 - first.weekday()) % 7
        third_friday = first + timedelta(days=days_to_friday + 14)
    return third_friday.strftime("%Y-%m-%d")


def _run_all_strategies(
    df: pd.DataFrame, sector: str, regime: str | None = None
) -> dict[str, int]:
    """Run all strategies on OHLCV data, return {strategy_name: signal}."""
    results = {}
    for name in list_strategies():
        try:
            strat = get_strategy(name, sector=sector or None, regime=regime)
            sig_series = strat.signals(df)
            results[name] = int(sig_series.iloc[-1])
        except Exception:
            results[name] = 0
    return results


_INTERVAL_PERIOD: dict[str, str] = {
    "1m": "7d",
    "5m": "30d",
    "15m": "30d",
    "1h": "30d",
    "4h": "30d",
    "1d": "90d",
}


def run_analyze(
    pipeline_dir: Path,
    regime: str,
    account_value: float,
    existing_positions: list[Position],
    open_orders: list[Order],
    consensus_threshold: int | None = None,
    watchlist_consensus_threshold: int | None = None,
    paper_mode: bool = False,
    interval: str = "1d",
) -> ProposalSet:
    """Analyze candidates and produce ranked trade proposals.

    Parameters
    ----------
    pipeline_dir : Path
        Directory containing candidates.json (written by discover)
    regime : str
        "bull", "caution", or "bear"
    account_value : float
        Account NLV for position sizing
    existing_positions : list[Position]
        Current positions for exposure checks
    open_orders : list[Order]
        Open orders for dedup
    consensus_threshold : int
        Minimum strategies agreeing for discovery candidates (default 3/6)
    watchlist_consensus_threshold : int
        Minimum strategies agreeing for watchlist candidates (default 2/6)
    """
    # Resolve consensus thresholds: CLI explicit > regime config > hardcoded defaults
    _default_discovery = 3
    _default_watchlist = 2
    regime_thresholds = get_regime_thresholds(regime)
    if consensus_threshold is None:
        consensus_threshold = (
            regime_thresholds["discovery"]
            if regime_thresholds and "discovery" in regime_thresholds
            else _default_discovery
        )
    if watchlist_consensus_threshold is None:
        watchlist_consensus_threshold = (
            regime_thresholds["watchlist"]
            if regime_thresholds and "watchlist" in regime_thresholds
            else _default_watchlist
        )

    period = _INTERVAL_PERIOD.get(interval, "90d")

    candidates_path = pipeline_dir / "candidates.json"
    cs = CandidateSet.model_validate_json(candidates_path.read_text())
    ticker_sentiment = cs.ticker_sentiment  # {ticker: float}

    # VIX-based entry gate — check once for the entire run
    vix_result = vix_gate()
    vix_ctx = VixContext(
        current=vix_result["vix_current"],
        peak=vix_result["vix_peak"],
        days_since_peak=vix_result["days_since_peak"],
        blocked=vix_result["blocked"],
        reason=vix_result["reason"],
    )
    if vix_ctx.blocked:
        logger.warning("VIX gate active: %s", vix_ctx.reason)

    rf = RiskFilter()
    atr_mult = regime_atr_multiplier(regime)

    # Auto-detect paper mode from config — relaxes bear regime gate
    if not paper_mode:
        try:
            paper_mode = Config().ibkr_mode == "paper"
        except Exception:
            pass
    existing_tickers = {p.ticker for p in existing_positions}
    open_order_tickers = {(o.ticker, o.side) for o in open_orders if o.status == "open"}

    all_proposals: list[Proposal] = []

    option_expiry = _next_monthly_expiry(min_dte=30)

    for sector_name, candidates in cs.sectors.items():
        for candidate in candidates:
            try:
                df = _fetch_ohlcv(candidate.ticker, period=period, interval=interval)
                if df.empty or len(df) < 30:
                    continue
            except Exception:
                continue

            entry_price = float(df["close"].iloc[-1])

            # Skip penny stocks / micro-caps with unreliable signals
            if entry_price < _MIN_PRICE:
                continue

            # Enrich sector if missing
            resolved_sector = candidate.sector or sector_name
            if not resolved_sector or resolved_sector == "Unknown":
                resolved_sector = _get_sector(candidate.ticker) or "Unknown"

            # Multi-strategy consensus
            signals = _run_all_strategies(df, resolved_sector, regime=regime)
            buy_count = sum(1 for s in signals.values() if s == 1)
            sell_count = sum(1 for s in signals.values() if s == -1)

            # Determine direction and consensus
            if buy_count >= sell_count:
                direction_signal = 1
                consensus = buy_count
                agree = [k for k, v in signals.items() if v == 1]
                disagree = [k for k, v in signals.items() if v != 1]
            else:
                direction_signal = -1
                consensus = sell_count
                agree = [k for k, v in signals.items() if v == -1]
                disagree = [k for k, v in signals.items() if v != -1]

            # VIX gate: block new longs when VIX is elevated; hedges/shorts always allowed
            if vix_result["blocked"] and direction_signal == 1:
                logger.info(
                    "VIX gate skipping long candidate %s: %s",
                    candidate.ticker, vix_result["reason"],
                )
                continue

            # Threshold check
            threshold = (
                watchlist_consensus_threshold
                if candidate.source == "watchlist"
                else consensus_threshold
            )
            if consensus < threshold:
                continue

            # Build SentimentResult from discover's scored sentiment
            sentiment = None
            agg_score = ticker_sentiment.get(candidate.ticker)
            if agg_score is not None:
                if agg_score > 0.1:
                    sig = "bullish"
                elif agg_score < -0.1:
                    sig = "bearish"
                else:
                    sig = "neutral"
                sentiment = SentimentResult(
                    ticker=candidate.ticker,
                    score=agg_score,
                    signal=sig,
                    article_count=len(candidate.news),
                    lookback_hours=24,
                    top_headlines=[n.headline for n in candidate.news[:3]],
                )

            # Risk filter (with regime and sentiment!)
            filtered = rf.filter(
                signal=direction_signal,
                quote=None,
                position=None,
                sentiment=sentiment,
                regime=regime,
                paper_mode=paper_mode,
                account_value=account_value,
                ticker=candidate.ticker,
            )
            if filtered["filtered"]:
                continue

            # Compute ATR, stop, sizing
            try:
                current_atr = float(compute_atr(df).iloc[-1])
                sl = compute_stop(df, entry_price=entry_price, atr_multiplier=atr_mult)
                qty = compute_position_size(
                    df, entry_price=entry_price,
                    account_value=account_value,
                    atr_multiplier=atr_mult,
                )
            except Exception:
                continue

            if qty <= 0 or entry_price <= 0:
                continue

            # Cap position size at _MAX_POSITION_PCT of NLV
            position_value = entry_price * qty
            pct_of_nlv = (position_value / account_value * 100) if account_value > 0 else 0
            if pct_of_nlv > _MAX_POSITION_PCT:
                qty = max(1, int(account_value * _MAX_POSITION_PCT / 100 / entry_price))
                position_value = entry_price * qty
                pct_of_nlv = (position_value / account_value * 100) if account_value > 0 else 0

            risk_per_share = entry_price - sl if direction_signal == 1 else sl - entry_price

            # Determine direction label and order construction
            if direction_signal == 1:
                direction = "long"
                take_profit = round(entry_price + atr_mult * current_atr * 1.5, 2)
                order = ProposalOrder(
                    side="buy",
                    order_type="bracket",
                    contract_type=candidate.asset_class,
                    qty=qty,
                    price=round(entry_price, 2),
                    stop_loss=round(sl, 2),
                    take_profit=take_profit,
                )
            else:
                direction = "hedge"
                # For bearish plays, propose a put option if it's a stock with options
                raw_strike = entry_price - current_atr
                # Round to nearest standard strike increment
                if raw_strike >= 100:
                    strike = round(raw_strike)           # $1 increments
                elif raw_strike >= 25:
                    strike = round(raw_strike * 2) / 2   # $0.50 increments
                else:
                    strike = round(raw_strike * 2) / 2   # $0.50 increments
                strike = max(strike, 0.50)  # floor strike at $0.50
                option_qty = max(1, qty // 100)  # option contracts = shares / 100
                premium_est = round(max(0.05, current_atr * 0.5), 2)
                order = ProposalOrder(
                    side="buy",
                    order_type="limit",
                    contract_type="option",
                    qty=option_qty,
                    price=premium_est,
                    right="put",
                    strike=strike,
                    expiry=option_expiry,
                )
                # Recalc position value for options (premium × 100 × qty)
                position_value = premium_est * 100 * option_qty
                pct_of_nlv = (position_value / account_value * 100) if account_value > 0 else 0

                # For ETFs, use direct sell instead
                if candidate.asset_class == "etf":
                    order = ProposalOrder(
                        side="sell",
                        order_type="limit",
                        contract_type="etf",
                        qty=qty,
                        price=round(entry_price, 2),
                    )
                    position_value = entry_price * qty
                    pct_of_nlv = (position_value / account_value * 100) if account_value > 0 else 0

            # Conviction scoring
            if consensus >= 5:
                conviction = "high"
            elif consensus >= 3:
                conviction = "medium"
            else:
                conviction = "low"

            sizing = ProposalSizing(
                atr=round(current_atr, 4),
                risk_per_share=round(abs(risk_per_share), 4),
                position_value=round(position_value, 2),
                pct_of_nlv=round(pct_of_nlv, 2),
            )

            news_context = ""
            if candidate.news:
                news_context = "; ".join(n.headline for n in candidate.news[:3])

            all_proposals.append(Proposal(
                rank=0,  # will be set after sorting
                ticker=candidate.ticker,
                source=candidate.source,
                direction=direction,
                consensus=consensus,
                strategies_agree=agree,
                strategies_disagree=disagree,
                conviction=conviction,
                order=order,
                sizing=sizing,
                news_context=news_context,
                sector=resolved_sector,
            ))

    # Rank proposals: consensus desc, watchlist first, ticker alpha
    all_proposals.sort(
        key=lambda p: (
            -p.consensus,
            0 if p.source == "watchlist" else 1,
            p.ticker,
        )
    )
    for i, p in enumerate(all_proposals, 1):
        p.rank = i

    # Group into sectors
    sector_proposals: dict[str, SectorProposals] = {}
    for p in all_proposals:
        sector = p.sector or "Unknown"
        if sector not in sector_proposals:
            sector_proposals[sector] = SectorProposals()
        sector_proposals[sector].proposals.append(p)

    # Generate sector summaries
    for sector, sp in sector_proposals.items():
        longs = sum(1 for p in sp.proposals if p.direction == "long")
        hedges = sum(1 for p in sp.proposals if p.direction in ("hedge", "short"))
        sp.summary = f"{longs} long, {hedges} hedge"

    result = ProposalSet(
        run_id=datetime.now(timezone.utc).isoformat(),
        regime=regime,
        available_capital=account_value,
        geo_context=cs.geo_context,
        vix_context=vix_ctx,
        sectors=sector_proposals,
    )

    # Write output
    pipeline_dir.mkdir(parents=True, exist_ok=True)
    out_path = pipeline_dir / "proposals.json"
    out_path.write_text(result.model_dump_json(indent=2))

    return result
