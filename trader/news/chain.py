# trader/news/chain.py
from __future__ import annotations
from trader.models import NewsItem
from trader.news.base import NewsProvider


def is_stub(items: list[NewsItem], tickers: list[str]) -> bool:
    """
    Detect stub/useless API responses.

    A result is stub if:
    - It's empty
    - All tickers share the same set of headlines (identical API response for every ticker)
    """
    if not items:
        return True

    if len(tickers) < 2:
        return False  # Can't detect cross-ticker duplication with one ticker

    # Group headlines by ticker
    by_ticker: dict[str, set[str]] = {}
    for item in items:
        t = item.ticker or ""
        by_ticker.setdefault(t, set()).add(item.headline)

    ticker_sets = [v for v in by_ticker.values() if v]
    if len(ticker_sets) < 2:
        return False

    # Stub if every ticker got the exact same headlines
    return all(s == ticker_sets[0] for s in ticker_sets[1:])


class NewsProviderChain(NewsProvider):
    """
    Tries providers in order. Returns the first non-stub result.
    Falls back to next provider on exception or stub detection.
    Returns [] only if all providers fail or return stub data.

    Order: Marketaux → Benzinga → Massive (configured via factory.py)
    """

    def __init__(self, providers: list[NewsProvider]) -> None:
        self.providers = providers

    async def get_news(self, tickers: list[str], limit: int = 10) -> list[NewsItem]:
        for provider in self.providers:
            try:
                items = await provider.get_news(tickers, limit)
            except Exception:
                continue
            if not is_stub(items, tickers):
                return items
        return []

    async def aclose(self) -> None:
        for provider in self.providers:
            try:
                await provider.aclose()
            except Exception:
                pass
