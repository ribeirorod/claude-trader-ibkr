# trader/news/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from trader.models import NewsItem


class NewsProvider(ABC):
    """Common interface for all news data providers."""

    @abstractmethod
    async def get_news(self, tickers: list[str], limit: int = 10) -> list[NewsItem]:
        """Fetch news articles for the given tickers. Returns [] on failure."""

    @abstractmethod
    async def aclose(self) -> None:
        """Release any underlying HTTP client resources."""
