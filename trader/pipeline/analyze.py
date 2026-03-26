from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from trader.pipeline.models import (
    CandidateSet, Candidate, Proposal, ProposalOrder, ProposalSizing,
    ProposalSet, SectorProposals,
)
from trader.strategies.factory import get_strategy, list_strategies
from trader.strategies.risk_filter import RiskFilter
from trader.strategies.stop_loss import (
    atr as compute_atr,
    stop_level as compute_stop,
    position_size as compute_position_size,
    regime_atr_multiplier,
)
from trader.models import Position, Order


# Re-use the yfinance ticker resolution from strategies CLI
_YF_TICKER_MAP: dict[str, str] = {
    "CSPX": "CSPX.L", "VUSA": "VUSA.AS", "IWDA": "IWDA.L", "SWDA": "SWDA.L",
    "EQQQ": "EQQQ.L", "IMEU": "IMEU.L", "EMIM": "EMIM.L",
    "SGLN": "SGLN.L", "PHAU": "PHAU.L", "AGGH": "AGGG.L", "IBTA": "IBTA.L",
    "IDTL": "IDTL.L", "IUES": "IUES.L", "XLES": "XLES.L",
}


def _resolve_yf_ticker(ticker: str) -> str:
    return _YF_TICKER_MAP.get(ticker.upper(), ticker)


def _fetch_ohlcv(ticker: str, period: str = "90d") -> pd.DataFrame:
    """Fetch OHLCV data via yfinance. Separate function for easy mocking."""
    df = yf.download(_resolve_yf_ticker(ticker), period=period, progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [c.lower() for c in df.columns]
    return df


def _run_all_strategies(
    df: pd.DataFrame, sector: str
) -> dict[str, int]:
    """Run all strategies on OHLCV data, return {strategy_name: signal}."""
    results = {}
    for name in list_strategies():
        try:
            strat = get_strategy(name, sector=sector or None)
            sig_series = strat.signals(df)
            results[name] = int(sig_series.iloc[-1])
        except Exception:
            results[name] = 0
    return results


def run_analyze(
    pipeline_dir: Path,
    regime: str,
    account_value: float,
    existing_positions: list[Position],
    open_orders: list[Order],
    consensus_threshold: int = 3,
    watchlist_consensus_threshold: int = 2,
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
    candidates_path = pipeline_dir / "candidates.json"
    cs = CandidateSet.model_validate_json(candidates_path.read_text())

    rf = RiskFilter()
    atr_mult = regime_atr_multiplier(regime)
    existing_tickers = {p.ticker for p in existing_positions}
    open_order_tickers = {(o.ticker, o.side) for o in open_orders if o.status == "open"}

    all_proposals: list[Proposal] = []

    for sector_name, candidates in cs.sectors.items():
        for candidate in candidates:
            try:
                df = _fetch_ohlcv(candidate.ticker)
                if df.empty or len(df) < 30:
                    continue
            except Exception:
                continue

            # Multi-strategy consensus
            signals = _run_all_strategies(df, candidate.sector)
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

            # Threshold check
            threshold = (
                watchlist_consensus_threshold
                if candidate.source == "watchlist"
                else consensus_threshold
            )
            if consensus < threshold:
                continue

            # Risk filter (with regime!)
            filtered = rf.filter(
                signal=direction_signal,
                quote=None,
                position=None,
                sentiment=None,
                regime=regime,
            )
            if filtered["filtered"]:
                continue

            # Compute ATR, stop, sizing
            try:
                current_atr = float(compute_atr(df).iloc[-1])
                entry_price = float(df["close"].iloc[-1])
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

            risk_per_share = entry_price - sl if direction_signal == 1 else sl - entry_price
            position_value = entry_price * qty
            pct_of_nlv = (position_value / account_value * 100) if account_value > 0 else 0

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
                order = ProposalOrder(
                    side="buy",
                    order_type="limit",
                    contract_type="option",
                    qty=max(1, qty // 100),  # option contracts = shares / 100
                    price=round(current_atr * 0.5, 2),  # rough premium estimate
                    right="put",
                    strike=round(entry_price - current_atr, 2),
                )
                # For ETFs, use direct sell instead
                if candidate.asset_class == "etf":
                    order = ProposalOrder(
                        side="sell",
                        order_type="limit",
                        contract_type="etf",
                        qty=qty,
                        price=round(entry_price, 2),
                    )

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
                sector=sector_name,
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
        sectors=sector_proposals,
    )

    # Write output
    pipeline_dir.mkdir(parents=True, exist_ok=True)
    out_path = pipeline_dir / "proposals.json"
    out_path.write_text(result.model_dump_json(indent=2))

    return result
