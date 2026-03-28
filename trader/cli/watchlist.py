from __future__ import annotations
import asyncio, json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import click
from trader.adapters.factory import get_adapter
from trader.cli.__main__ import output_json

# Storage: outputs/watchlists.json
# Format:
#   {"default": {"tickers": ["NVDA","AAPL"], "sectors": {"NVDA": "Technology"}}}
# Legacy format (plain list) is auto-migrated on load.

def _wl_path(ctx) -> Path:
    output_dir = Path(ctx.find_root().obj.get("output_dir", "outputs"))
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / "watchlists.json"

def _load(ctx) -> dict:
    p = _wl_path(ctx)
    if p.exists():
        raw = json.loads(p.read_text())
        # Auto-migrate legacy format: {"name": ["AAPL"]} → {"name": {"tickers": [...], "sectors": {}}}
        migrated = False
        for k, v in raw.items():
            if isinstance(v, list):
                raw[k] = {"tickers": v, "sectors": {}}
                migrated = True
        if migrated:
            p.write_text(json.dumps(raw, indent=2))
        return raw
    return {}

def _save(ctx, data: dict) -> None:
    _wl_path(ctx).write_text(json.dumps(data, indent=2))

def _get_tickers(data: dict, list_name: str) -> list[str]:
    entry = data.get(list_name, {})
    if isinstance(entry, list):
        return entry
    return entry.get("tickers", [])

def _get_sectors(data: dict, list_name: str) -> dict[str, str]:
    entry = data.get(list_name, {})
    if isinstance(entry, dict):
        return entry.get("sectors", {})
    return {}


@click.group()
def watchlist():
    """
    Watchlists: track tickers across sessions.

    \b
    Quick examples:
      trader watchlist add NVDA MSFT PLTR
      trader watchlist add VRT AGX --list 52wk-highs
      trader watchlist show
      trader watchlist show 52wk-highs --strategy rsi
      trader watchlist from-scan HIGH_VS_52W_HL --ema200-above --list 52wk-highs

    Stored in: outputs/watchlists.json
    """


@watchlist.command("add")
@click.argument("tickers", nargs=-1, required=True)
@click.option("--list", "list_name", default="default", show_default=True,
              help="Watchlist name to add tickers to.")
@click.pass_context
def add(ctx, tickers, list_name):
    """
    Add one or more tickers to a watchlist.

    \b
    Examples:
      trader watchlist add NVDA MSFT AAPL
      trader watchlist add VRT AGX UTHR --list 52wk-highs
    """
    data = _load(ctx)
    entry = data.get(list_name, {"tickers": [], "sectors": {}})
    if isinstance(entry, list):
        entry = {"tickers": entry, "sectors": {}}
    existing = set(entry["tickers"])
    added = [t.upper() for t in tickers if t.upper() not in existing]
    entry["tickers"] = sorted(existing | set(t.upper() for t in tickers))
    data[list_name] = entry
    _save(ctx, data)
    output_json({
        "list": list_name,
        "added": added,
        "tickers": entry["tickers"],
        "total": len(entry["tickers"]),
    })


@watchlist.command("remove")
@click.argument("tickers", nargs=-1, required=True)
@click.option("--list", "list_name", default="default", show_default=True,
              help="Watchlist name to remove tickers from.")
@click.pass_context
def remove(ctx, tickers, list_name):
    """
    Remove one or more tickers from a watchlist.

    Example: trader watchlist remove NVDA MSFT --list 52wk-highs
    """
    data = _load(ctx)
    entry = data.get(list_name, {"tickers": [], "sectors": {}})
    if isinstance(entry, list):
        entry = {"tickers": entry, "sectors": {}}
    upper = {t.upper() for t in tickers}
    removed = [t for t in entry["tickers"] if t in upper]
    entry["tickers"] = [t for t in entry["tickers"] if t not in upper]
    # Clean sector entries
    for t in removed:
        entry.get("sectors", {}).pop(t, None)
    if not entry["tickers"]:
        del data[list_name]
    else:
        data[list_name] = entry
    _save(ctx, data)
    output_json({
        "list": list_name,
        "removed": removed,
        "tickers": entry.get("tickers", []),
        "total": len(entry.get("tickers", [])),
    })


@watchlist.command("list")
@click.pass_context
def list_watchlists(ctx):
    """
    List all watchlists and their tickers.

    Example: trader watchlist list
    """
    data = _load(ctx)
    if not data:
        output_json([])
        return
    output_json([
        {"list": name, "tickers": _get_tickers(data, name), "count": len(_get_tickers(data, name))}
        for name in sorted(data.keys())
    ])


@watchlist.command("show")
@click.argument("list_name", default="default")
@click.option("--signals", is_flag=True, default=False,
              help="Include sentiment scores alongside quotes (legacy).")
@click.option("--strategy", default=None,
              help="Run strategy signals on each ticker (e.g. rsi, macd, ma_cross).")
@click.option("--interval", default="1d", help="Bar interval for strategy signals.")
@click.option("--lookback", default="90d", help="History window for strategy signals.")
@click.pass_context
def show(ctx, list_name, signals, strategy, interval, lookback):
    """
    Get live quotes for all tickers in a watchlist.

    Pass --strategy to run buy/sell/hold strategy signals on each ticker.
    Uses sector-optimized parameters when sector data is available.

    \b
    Examples:
      trader watchlist show
      trader watchlist show momentum --strategy rsi
      trader watchlist show 52wk-highs --strategy macd --lookback 180d
      trader watchlist show 52wk-highs --signals
    """
    data = _load(ctx)
    tickers = _get_tickers(data, list_name)
    sector_map = _get_sectors(data, list_name)
    if not tickers:
        output_json({"error": f"Watchlist '{list_name}' is empty or does not exist."})
        sys.exit(1)

    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])

    async def run():
        await adapter.connect()
        try:
            quotes = await adapter.get_quotes(tickers)
            result = [q.model_dump() for q in quotes]

            # Attach stored sector info to each quote
            for r in result:
                r["sector"] = sector_map.get(r["ticker"], "")

            if strategy:
                import yfinance as yf
                from trader.strategies.factory import get_strategy
                from trader.strategies.risk_filter import RiskFilter
                from trader.strategies.stop_loss import atr as compute_atr, stop_level as compute_stop
                from trader.cli.strategies import _fetch_ohlcv

                rf = RiskFilter()
                for r in result:
                    ticker = r["ticker"]
                    try:
                        df = _fetch_ohlcv(ticker, interval, lookback)
                        sector = r.get("sector", "")
                        strat = get_strategy(strategy, sector=sector)
                        sig_series = strat.signals(df)
                        raw_signal = int(sig_series.iloc[-1])
                        try:
                            current_atr = round(float(compute_atr(df).iloc[-1]), 4)
                            entry = float(df["close"].iloc[-1])
                            sl = round(compute_stop(df, entry_price=entry), 4)
                        except Exception:
                            current_atr = None
                            sl = None
                        filtered = rf.filter(signal=raw_signal, quote=None,
                                             position=None, sentiment=None)
                        r["signal"] = filtered["signal"]
                        r["signal_label"] = {1: "buy", -1: "sell", 0: "hold"}[filtered["signal"]]
                        r["strategy"] = strategy
                        r["strategy_params"] = strat.params
                        r["filtered"] = filtered["filtered"]
                        r["filter_reason"] = filtered["filter_reason"]
                        r["atr"] = current_atr
                        r["stop_level"] = sl
                    except Exception as e:
                        r["signal"] = None
                        r["signal_error"] = str(e)

            if signals:
                from trader.news.benzinga import BenzingaClient
                from trader.news.sentiment import SentimentScorer

                benzinga = BenzingaClient(ctx.obj["config"])
                scorer = SentimentScorer()

                async def score_ticker(ticker):
                    try:
                        news = await benzinga.get_news([ticker], limit=5)
                        sentiment = scorer.score(news)
                        return {"ticker": ticker, "sentiment": sentiment}
                    except Exception:
                        return {"ticker": ticker, "sentiment": 0.0}

                sentiments = await asyncio.gather(*[score_ticker(t) for t in tickers])
                sent_map = {s["ticker"]: s["sentiment"] for s in sentiments}

                for r in result:
                    r["sentiment_score"] = sent_map.get(r["ticker"], 0.0)

            return {"list": list_name, "count": len(result), "quotes": result}
        finally:
            await adapter.disconnect()

    try:
        output_json(asyncio.run(run()))
    except Exception as e:
        click.echo(json.dumps({"error": str(e), "code": type(e).__name__}))
        sys.exit(1)


@watchlist.command("clear")
@click.argument("list_name", default="default")
@click.confirmation_option(prompt="Clear all tickers from this watchlist?")
@click.pass_context
def clear(ctx, list_name):
    """
    Remove all tickers from a watchlist (keeps the list name).

    Example: trader watchlist clear momentum
    """
    data = _load(ctx)
    if list_name in data:
        count = len(_get_tickers(data, list_name))
        del data[list_name]
        _save(ctx, data)
        output_json({"cleared": list_name, "removed_count": count})
    else:
        output_json({"error": f"Watchlist '{list_name}' not found."})


@watchlist.command("from-scan")
@click.argument("scan_type")
@click.option("--list", "list_name", default="default", show_default=True,
              help="Watchlist name to populate.")
@click.option("--replace", is_flag=True, default=False,
              help="Replace existing tickers instead of merging.")
@click.option("--market", default="STK.US.MAJOR", show_default=True,
              help="Market/location code. Run 'trader scan markets' to see options.")
@click.option("--limit", default=20, show_default=True, type=int)
@click.option("--price-above", type=float, default=None)
@click.option("--price-below", type=float, default=None)
@click.option("--volume-above", type=int, default=None)
@click.option("--avg-volume-above", type=int, default=None)
@click.option("--ema20-above", is_flag=True, default=False)
@click.option("--ema50-above", is_flag=True, default=False)
@click.option("--ema200-above", is_flag=True, default=False)
@click.option("--mktcap-above", type=float, default=None)
@click.option("--has-options", is_flag=True, default=False)
@click.pass_context
def from_scan(ctx, scan_type, list_name, replace, market, limit,
              price_above, price_below, volume_above, avg_volume_above,
              ema20_above, ema50_above, ema200_above, mktcap_above, has_options):
    """
    Populate a watchlist from a live IBKR scan.

    Stores sector metadata for each ticker to enable sector-optimized strategy signals.

    \b
    Examples:
      trader watchlist from-scan HIGH_VS_52W_HL --ema200-above --list 52wk-highs
      trader watchlist from-scan TOP_PERC_GAIN --mktcap-above 500 --list momentum
      trader watchlist from-scan MOST_ACTIVE_USD --list active --replace
    """
    filters = []
    def _f(code, value):
        if value is not None:
            filters.append({"code": code, "value": value})

    _f("priceAbove", price_above)
    _f("priceBelow", price_below)
    _f("volumeAbove", volume_above)
    _f("avgVolumeAbove", avg_volume_above)
    _f("marketCapAbove", mktcap_above)
    if ema20_above:
        filters.append({"code": "curEMA20Above", "value": 1})
    if ema50_above:
        filters.append({"code": "curEMA50Above", "value": 1})
    if ema200_above:
        filters.append({"code": "curEMA200Above", "value": 1})
    if has_options:
        filters.append({"code": "hasOptionsIs", "value": 1})

    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])

    async def run():
        await adapter.connect()
        try:
            results = await adapter.scan(scan_type, market, filters or None, limit)
            return results
        finally:
            await adapter.disconnect()

    try:
        results = asyncio.run(run())
    except Exception as e:
        click.echo(json.dumps({"error": str(e), "code": type(e).__name__}))
        sys.exit(1)

    new_tickers = [r.symbol for r in results]
    new_sectors = {r.symbol: r.sector for r in results if r.sector}

    data = _load(ctx)
    if replace:
        data[list_name] = {
            "tickers": sorted(set(new_tickers)),
            "sectors": new_sectors,
        }
    else:
        entry = data.get(list_name, {"tickers": [], "sectors": {}})
        if isinstance(entry, list):
            entry = {"tickers": entry, "sectors": {}}
        existing = set(entry["tickers"])
        entry["tickers"] = sorted(existing | set(new_tickers))
        entry["sectors"] = {**entry.get("sectors", {}), **new_sectors}
        data[list_name] = entry
    _save(ctx, data)

    output_json({
        "list": list_name,
        "scan_type": scan_type,
        "added": new_tickers,
        "sectors": new_sectors,
        "tickers": _get_tickers(data, list_name),
        "total": len(_get_tickers(data, list_name)),
    })


@watchlist.command("prune")
@click.option("--ttl-days", default=14, type=int, show_default=True,
              help="Remove discovery tickers older than this many days.")
@click.option("--dry-run", is_flag=True, default=False,
              help="Show what would be pruned without modifying.")
@click.pass_context
def prune(ctx, ttl_days, dry_run):
    """
    Remove stale discovery-added tickers from all watchlists.

    Only removes tickers that have metadata with source='discovery' and
    added_at older than --ttl-days. User-added tickers (no metadata) are
    never pruned.

    \b
    Examples:
      trader watchlist prune
      trader watchlist prune --dry-run
      trader watchlist prune --ttl-days 7
    """
    data = _load(ctx)
    cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
    all_pruned: list[str] = []

    for list_name, entry in data.items():
        if not isinstance(entry, dict):
            continue
        metadata = entry.get("metadata", {})
        to_remove: list[str] = []
        for ticker in entry.get("tickers", []):
            meta = metadata.get(ticker)
            if meta is None:
                continue  # user-added, never prune
            if meta.get("source") != "discovery":
                continue  # not discovery-sourced, never prune
            added_at_str = meta.get("added_at")
            if not added_at_str:
                continue
            added_at = datetime.fromisoformat(added_at_str)
            if added_at < cutoff:
                to_remove.append(ticker)

        if not dry_run:
            for ticker in to_remove:
                entry["tickers"].remove(ticker)
                metadata.pop(ticker, None)
                entry.get("sectors", {}).pop(ticker, None)

        all_pruned.extend(to_remove)

    if dry_run:
        output_json({"would_prune": all_pruned, "ttl_days": ttl_days})
    else:
        _save(ctx, data)
        output_json({"pruned": all_pruned, "ttl_days": ttl_days})
