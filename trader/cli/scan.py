from __future__ import annotations
import asyncio, json, sys
import click
from trader.adapters.factory import get_adapter
from trader.cli.__main__ import output_json

# ── Curated reference tables (teach the user without overwhelming them) ────────

_COMMON_TYPES = {
    # Momentum / price action
    "TOP_PERC_GAIN":       "Top % Gainers",
    "TOP_PERC_LOSE":       "Top % Losers",
    "MOST_ACTIVE":         "Most Active by Volume",
    "MOST_ACTIVE_USD":     "Most Active by Dollar Volume",
    "HIGH_OPEN_GAP":       "Top Close-to-Open Gap Up",
    "LOW_OPEN_GAP":        "Top Close-to-Open Gap Down",
    "TOP_OPEN_PERC_GAIN":  "Top % Gainers Since Open",
    "TOP_AFTER_HOURS_PERC_GAIN": "Top After-Hours Gainers",
    # 52-week range
    "HIGH_VS_52W_HL":      "Near 52-Week High",
    "LOW_VS_52W_HL":       "Near 52-Week Low",
    "HIGH_VS_13W_HL":      "Near 13-Week High",
    "HIGH_VS_26W_HL":      "Near 26-Week High",
    # Options flow
    "HIGH_OPT_IMP_VOLAT":  "Highest Implied Volatility",
    "TOP_OPT_IMP_VOLAT_GAIN": "Biggest IV% Gainers",
    "OPT_VOLUME_MOST_ACTIVE": "Most Active by Option Volume",
    "HIGH_OPT_VOLUME_PUT_CALL_RATIO": "High Put/Call Ratio (bearish flow)",
    "LOW_OPT_VOLUME_PUT_CALL_RATIO":  "Low Put/Call Ratio (bullish flow)",
    # Fundamentals (Refinitiv)
    "HIGH_GROWTH_RATE":    "High Growth Rate",
    "HIGH_RETURN_ON_EQUITY": "High Return on Equity",
    "LOW_PE_RATIO":        "Low P/E Ratio",
    "HIGH_PRICE_2_BOOK_RATIO": "High Price/Book",
    "WSH_PREV_EARNINGS":   "Recent Earnings (WSH)",
    "WSH_NEXT_MAJOR_EVENT": "Upcoming Major Event (WSH)",
    # Short interest
    "SCAN_sharesAvailableNorm_ASC": "Shortable Shares (Low→High)",
    "SCAN_utilization_DESC": "Short Utilization (High→Low)",
}

_COMMON_MARKETS = {
    "STK.US.MAJOR":    "US Stocks — Listed/NASDAQ (default)",
    "STK.US.MINOR":    "US Stocks — OTC Markets",
    "ETF.EQ.US.MAJOR": "US Equity ETFs",
    "ETF.FI.US.MAJOR": "US Fixed Income ETFs",
    "STK.EU.LSE":      "Europe — London (LSE)",
    "STK.EU.IBIS":     "Europe — Germany (XETRA)",
    "STK.EU.SBF":      "Europe — France (Euronext)",
    "STK.HK.TSE_JPN":  "Asia — Japan (TSE)",
    "STK.HK.SEHK":     "Asia — Hong Kong (SEHK)",
    "STK.HK.ASX":      "Asia — Australia (ASX)",
    "STK.NA.CANADA":   "Americas — Canada (TSX)",
    "FUT.CME":         "US Futures — CME",
    "FUT.NYMEX":       "US Futures — NYMEX",
}

_COMMON_FILTERS = {
    "priceAbove":      "Minimum price (e.g. 5)",
    "priceBelow":      "Maximum price",
    "volumeAbove":     "Minimum daily volume",
    "avgVolumeAbove":  "Minimum average volume",
    "avgUsdVolumeAbove": "Minimum avg dollar volume",
    "changePercAbove": "Minimum day change %",
    "changePercBelow": "Maximum day change %",
    "curEMA20Above":   "Price above 20-day EMA",
    "curEMA50Above":   "Price above 50-day EMA",
    "curEMA200Above":  "Price above 200-day EMA",
    "curEMA200Below":  "Price below 200-day EMA",
    "marketCapAbove":  "Min market cap (millions)",
    "marketCapBelow":  "Max market cap (millions)",
    "impVolatAbove":   "Min implied volatility",
    "hasOptionsIs":    "Has listed options (1=yes)",
}


@click.group()
def scan():
    """
    Market scanner: discover tickers by type, market, and filters.

    \b
    Quick examples:
      trader scan run TOP_PERC_GAIN
      trader scan run MOST_ACTIVE --market STK.US.MAJOR --volume-above 1000000
      trader scan run HIGH_VS_52W_HL --price-above 10 --ema200-above --limit 30

    \b
    Discovery commands (learn what's available):
      trader scan types      — curated list of common scan types
      trader scan markets    — available markets / locations
      trader scan filters    — available filter parameters
      trader scan params     — full raw params from IBKR (all 563 types)
    """


def _run(ctx, coro):
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    async def run():
        await adapter.connect()
        try:
            return await coro(adapter)
        finally:
            await adapter.disconnect()
    try:
        output_json(asyncio.run(run()))
    except Exception as e:
        click.echo(json.dumps({"error": str(e), "code": type(e).__name__}))
        sys.exit(1)


@scan.command("run")
@click.argument("scan_type", metavar="TYPE")
@click.option("--market", default="STK.US.MAJOR", show_default=True,
              help="Market/location code. Run 'trader scan markets' to see all options.")
@click.option("--limit", default=20, show_default=True, type=int,
              help="Max results to return (1–50).")
# ── Price / volume filters ──────────────────────────────────────────────────
@click.option("--price-above", type=float, default=None, metavar="N",
              help="Only include contracts priced above N.")
@click.option("--price-below", type=float, default=None, metavar="N",
              help="Only include contracts priced below N.")
@click.option("--volume-above", type=int, default=None, metavar="N",
              help="Minimum daily volume.")
@click.option("--avg-volume-above", type=int, default=None, metavar="N",
              help="Minimum average daily volume.")
@click.option("--avg-usd-volume-above", type=float, default=None, metavar="N",
              help="Minimum average dollar volume (e.g. 5000000 for $5M avg).")
# ── Technical filters ───────────────────────────────────────────────────────
@click.option("--ema20-above", is_flag=True, default=False,
              help="Only stocks trading above their 20-day EMA.")
@click.option("--ema50-above", is_flag=True, default=False,
              help="Only stocks trading above their 50-day EMA.")
@click.option("--ema200-above", is_flag=True, default=False,
              help="Only stocks trading above their 200-day EMA (uptrend filter).")
@click.option("--ema200-below", is_flag=True, default=False,
              help="Only stocks trading below their 200-day EMA (downtrend filter).")
@click.option("--change-above", type=float, default=None, metavar="PCT",
              help="Minimum day change %% (e.g. 2.0 for +2%% or more).")
@click.option("--change-below", type=float, default=None, metavar="PCT",
              help="Maximum day change %% (e.g. -2.0 for -2%% or worse).")
# ── Fundamental filters ─────────────────────────────────────────────────────
@click.option("--mktcap-above", type=float, default=None, metavar="M",
              help="Minimum market cap in millions (e.g. 300 for small-cap+).")
@click.option("--mktcap-below", type=float, default=None, metavar="M",
              help="Maximum market cap in millions.")
@click.option("--has-options", is_flag=True, default=False,
              help="Only include contracts with listed options.")
# ── Signal overlay ─────────────────────────────────────────────────────────
@click.option("--signals", is_flag=True, default=False,
              help="Run strategy signals on each scan result (uses sector-optimized params).")
@click.option("--strategy", default="rsi",
              help="Strategy to run when --signals is set (rsi, macd, ma_cross, bnf, momentum).")
@click.option("--lookback", default="90d",
              help="History window for signals (e.g. 30d, 90d, 1y).")
@click.pass_context
def run_scan(ctx, scan_type, market, limit, price_above, price_below,
             volume_above, avg_volume_above, avg_usd_volume_above,
             ema20_above, ema50_above, ema200_above, ema200_below,
             change_above, change_below, mktcap_above, mktcap_below,
             has_options, signals, strategy, lookback):
    """
    Run a market scan by TYPE and return matching tickers.

    \b
    TYPE is the scan code, e.g.:
      TOP_PERC_GAIN       Top % Gainers
      MOST_ACTIVE         Most Active by Volume
      HIGH_VS_52W_HL      Near 52-Week High
      HIGH_OPT_IMP_VOLAT  Highest Implied Volatility
      WSH_PREV_EARNINGS   Recent Earnings

    Run 'trader scan types' for a curated list, or 'trader scan params' for all 563.

    \b
    Examples:
      trader scan run TOP_PERC_GAIN
      trader scan run MOST_ACTIVE --market STK.US.MAJOR --volume-above 500000 --price-above 5
      trader scan run HIGH_VS_52W_HL --ema200-above --avg-volume-above 200000 --limit 30
      trader scan run TOP_PERC_GAIN --signals --strategy rsi
      trader scan run HIGH_VS_52W_HL --signals --strategy macd --lookback 180d
    """
    filters = []

    def _f(code, value):
        if value is not None:
            filters.append({"code": code, "value": value})

    _f("priceAbove", price_above)
    _f("priceBelow", price_below)
    _f("volumeAbove", volume_above)
    _f("avgVolumeAbove", avg_volume_above)
    _f("avgUsdVolumeAbove", avg_usd_volume_above)
    _f("changePercAbove", change_above)
    _f("changePercBelow", change_below)
    _f("marketCapAbove", mktcap_above)
    _f("marketCapBelow", mktcap_below)
    if ema20_above:
        filters.append({"code": "curEMA20Above", "value": 1})
    if ema50_above:
        filters.append({"code": "curEMA50Above", "value": 1})
    if ema200_above:
        filters.append({"code": "curEMA200Above", "value": 1})
    if ema200_below:
        filters.append({"code": "curEMA200Below", "value": 1})
    if has_options:
        filters.append({"code": "hasOptionsIs", "value": 1})

    if not signals:
        _run(ctx, lambda a: a.scan(scan_type, market, filters or None, limit))
        return

    # Scan-to-signals pipeline: scan → enrich with sector → run strategy signals
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])

    async def run_with_signals():
        await adapter.connect()
        try:
            results = await adapter.scan(scan_type, market, filters or None, limit)
            return results
        finally:
            await adapter.disconnect()

    try:
        results = asyncio.run(run_with_signals())
    except Exception as e:
        click.echo(json.dumps({"error": str(e), "code": type(e).__name__}))
        sys.exit(1)

    # Run strategy signals on each scan result
    from trader.strategies.factory import get_strategy
    from trader.strategies.risk_filter import RiskFilter
    from trader.strategies.stop_loss import atr as compute_atr, stop_level as compute_stop
    from trader.cli.strategies import _fetch_ohlcv

    rf = RiskFilter()
    output = []
    for r in results:
        entry = r.model_dump()
        try:
            df = _fetch_ohlcv(r.symbol, "1d", lookback)
            strat = get_strategy(strategy, sector=r.sector or None)
            sig_series = strat.signals(df)
            raw_signal = int(sig_series.iloc[-1])
            try:
                current_atr = round(float(compute_atr(df).iloc[-1]), 4)
                price = float(df["close"].iloc[-1])
                sl = round(compute_stop(df, entry_price=price), 4)
            except Exception:
                current_atr = None
                sl = None
            filtered = rf.filter(signal=raw_signal, quote=None,
                                 position=None, sentiment=None)
            entry["signal"] = filtered["signal"]
            entry["signal_label"] = {1: "buy", -1: "sell", 0: "hold"}[filtered["signal"]]
            entry["strategy"] = strategy
            entry["strategy_params"] = strat.params
            entry["filtered"] = filtered["filtered"]
            entry["filter_reason"] = filtered["filter_reason"]
            entry["atr"] = current_atr
            entry["stop_level"] = sl
        except Exception as e:
            entry["signal"] = None
            entry["signal_error"] = str(e)
        output.append(entry)
    output_json(output)


@scan.command("types")
@click.pass_context
def list_types(ctx):
    """
    Show curated common scan types.

    For the full list of all 563 types run: trader scan params
    """
    output_json([
        {"code": code, "description": desc}
        for code, desc in _COMMON_TYPES.items()
    ])


@scan.command("markets")
@click.pass_context
def list_markets(ctx):
    """
    Show available market / location codes for --market.

    For the full tree run: trader scan params
    """
    output_json([
        {"code": code, "description": desc}
        for code, desc in _COMMON_MARKETS.items()
    ])


@scan.command("filters")
@click.pass_context
def list_filters(ctx):
    """
    Show available filter parameters for 'trader scan run'.

    For the complete filter list run: trader scan params
    """
    output_json([
        {"filter": f, "description": d}
        for f, d in _COMMON_FILTERS.items()
    ])


@scan.command("params")
@click.option("--section", default="all",
              type=click.Choice(["all", "types", "markets", "filters"]),
              help="Which section to return.")
@click.pass_context
def raw_params(ctx, section):
    """
    Fetch the full raw scanner parameter list from IBKR (all 563 scan types,
    all markets, all filters).

    Use --section to narrow the output:
      --section types    scan_type_list only
      --section markets  location_tree only
      --section filters  filter_list only
    """
    async def coro(a):
        data = await a.scan_params()
        if section == "types":
            return data.get("scan_type_list", [])
        if section == "markets":
            return data.get("location_tree", [])
        if section == "filters":
            return data.get("filter_list", [])
        return data
    _run(ctx, coro)
