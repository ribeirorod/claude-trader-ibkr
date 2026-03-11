from __future__ import annotations
import asyncio, json, sys
from pathlib import Path
import click
from trader.adapters.factory import get_adapter
from trader.cli.__main__ import output_json

# Storage: outputs/watchlists.json
# Format: {"default": ["NVDA", "AAPL"], "momentum": ["PLTR", "VRT"]}

def _wl_path(ctx) -> Path:
    output_dir = Path(ctx.find_root().obj.get("output_dir", "outputs"))
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / "watchlists.json"

def _load(ctx) -> dict[str, list[str]]:
    p = _wl_path(ctx)
    if p.exists():
        return json.loads(p.read_text())
    return {}

def _save(ctx, data: dict[str, list[str]]) -> None:
    _wl_path(ctx).write_text(json.dumps(data, indent=2))


@click.group()
def watchlist():
    """
    Watchlists: track tickers across sessions.

    \b
    Quick examples:
      trader watchlist add NVDA MSFT PLTR
      trader watchlist add VRT AGX --list 52wk-highs
      trader watchlist show
      trader watchlist show 52wk-highs
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
    existing = set(data.get(list_name, []))
    added = [t.upper() for t in tickers if t.upper() not in existing]
    data[list_name] = sorted(existing | set(t.upper() for t in tickers))
    _save(ctx, data)
    output_json({
        "list": list_name,
        "added": added,
        "tickers": data[list_name],
        "total": len(data[list_name]),
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
    upper = {t.upper() for t in tickers}
    current = data.get(list_name, [])
    removed = [t for t in current if t in upper]
    data[list_name] = [t for t in current if t not in upper]
    if not data[list_name]:
        del data[list_name]
    _save(ctx, data)
    output_json({
        "list": list_name,
        "removed": removed,
        "tickers": data.get(list_name, []),
        "total": len(data.get(list_name, [])),
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
        {"list": name, "tickers": tickers, "count": len(tickers)}
        for name, tickers in sorted(data.items())
    ])


@watchlist.command("show")
@click.argument("list_name", default="default")
@click.option("--signals", is_flag=True, default=False,
              help="Include RSI strategy signals alongside quotes.")
@click.pass_context
def show(ctx, list_name, signals):
    """
    Get live quotes for all tickers in a watchlist.

    Pass --signals to also run RSI signals on each ticker.

    \b
    Examples:
      trader watchlist show
      trader watchlist show momentum
      trader watchlist show 52wk-highs --signals
      trader --save watchlist show
    """
    data = _load(ctx)
    tickers = data.get(list_name, [])
    if not tickers:
        output_json({"error": f"Watchlist '{list_name}' is empty or does not exist."})
        sys.exit(1)

    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])

    async def run():
        await adapter.connect()
        try:
            quotes = await adapter.get_quotes(tickers)
            result = [q.model_dump() for q in quotes]

            if signals:
                from trader.strategies.factory import get_strategy
                from trader.news.benzinga import BenzingaClient
                from trader.news.sentiment import SentimentScorer

                strategy = get_strategy("rsi")
                benzinga = BenzingaClient(ctx.obj["config"])
                scorer = SentimentScorer()

                async def score_ticker(ticker):
                    try:
                        news = await benzinga.get_news([ticker], limit=5)
                        sentiment = scorer.score(news)
                        sig = strategy.signal([])  # placeholder — no price history here
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
        count = len(data[list_name])
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
            return [r.symbol for r in results]
        finally:
            await adapter.disconnect()

    try:
        new_tickers = asyncio.run(run())
    except Exception as e:
        click.echo(json.dumps({"error": str(e), "code": type(e).__name__}))
        sys.exit(1)

    data = _load(ctx)
    if replace:
        data[list_name] = sorted(set(new_tickers))
    else:
        existing = set(data.get(list_name, []))
        data[list_name] = sorted(existing | set(new_tickers))
    _save(ctx, data)

    output_json({
        "list": list_name,
        "scan_type": scan_type,
        "added": new_tickers,
        "tickers": data[list_name],
        "total": len(data[list_name]),
    })
