from __future__ import annotations
import asyncio
import click
from trader.news.benzinga import BenzingaClient
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
    """News and sentiment analysis via Benzinga."""

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
    client = BenzingaClient(ctx.obj["config"])
    async def run():
        try:
            return await client.get_news(ticker_list, limit=limit)
        finally:
            await client.aclose()
    output_json(asyncio.get_event_loop().run_until_complete(run()))

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
    client = BenzingaClient(ctx.obj["config"])
    scorer = SentimentScorer()
    async def run():
        try:
            items = await client.get_news([ticker], limit=50)
        finally:
            await client.aclose()
        return scorer.score(ticker, items, lookback_hours=hours)
    output_json(asyncio.get_event_loop().run_until_complete(run()))
