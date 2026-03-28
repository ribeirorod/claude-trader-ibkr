from __future__ import annotations
import asyncio, json
import click
from trader.news.factory import get_news_provider
from trader.news.sentiment import SentimentScorer
from trader.cli.__main__ import output_json

def _parse_lookback(s: str) -> int:
    s = s.lower().strip()
    if s.endswith("d"):
        return int(s[:-1]) * 24
    if s.endswith("h"):
        return int(s[:-1])
    return 24

@click.group()
def news():
    """News and sentiment analysis (Marketaux → Benzinga)."""

@news.command()
@click.option("--tickers", required=True,
              help="Comma or space-separated tickers e.g. AAPL,MSFT or 'AAPL MSFT'.")
@click.option("--limit", default=10, type=int, help="Max articles per ticker.")
@click.pass_context
def latest(ctx, tickers, limit):
    """
    Get latest news articles for one or more tickers.

    Example: trader news latest --tickers AAPL,MSFT --limit 5
    """
    ticker_list = [t.strip() for t in tickers.replace(",", " ").split()]
    client = get_news_provider(ctx.obj["config"])
    async def run():
        try:
            return await client.get_news(ticker_list, limit=limit)
        finally:
            await client.aclose()
    try:
        output_json(asyncio.run(run()))
    except Exception as e:
        import sys
        click.echo(json.dumps({"error": str(e), "code": type(e).__name__}))
        sys.exit(1)

@news.command()
@click.argument("ticker")
@click.option("--lookback", default="24h",
              help="Lookback window e.g. 24h (default), 48h, 7d.")
@click.pass_context
def sentiment(ctx, ticker, lookback):
    """
    Score news sentiment for TICKER from -1.0 (bearish) to 1.0 (bullish).

    Example: trader news sentiment AAPL --lookback 48h
    """
    hours = _parse_lookback(lookback)
    client = get_news_provider(ctx.obj["config"])
    scorer = SentimentScorer()
    async def run():
        try:
            items = await client.get_news([ticker], limit=50)
        finally:
            await client.aclose()
        return scorer.score(ticker, items, lookback_hours=hours)
    try:
        output_json(asyncio.run(run()))
    except Exception as e:
        import sys
        click.echo(json.dumps({"error": str(e), "code": type(e).__name__}))
        sys.exit(1)
