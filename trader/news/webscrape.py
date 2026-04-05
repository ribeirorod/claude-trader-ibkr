# trader/news/webscrape.py
"""Web-scrape fallback news provider — last resort in NewsProviderChain."""
from __future__ import annotations

import asyncio
import logging

import httpx

from trader.models import NewsItem
from trader.news.base import NewsProvider
from trader.news.scrape_finviz import fetch_finviz_news

logger = logging.getLogger(__name__)

_REQUEST_DELAY = 0.6


class WebScrapeProvider(NewsProvider):
    """
    Scrapes publicly accessible stock news pages.
    No API key required. Intended as the last fallback in the chain.
    Currently scrapes: Finviz.
    """

    def __init__(self) -> None:
        self._http = httpx.AsyncClient(timeout=15.0)

    async def get_news(self, tickers: list[str], limit: int = 10) -> list[NewsItem]:
        items: list[NewsItem] = []
        for i, ticker in enumerate(tickers):
            if i > 0:
                await asyncio.sleep(_REQUEST_DELAY)
            fetched = await fetch_finviz_news(
                self._http, ticker, limit=limit
            )
            items.extend(fetched)
        return items

    async def aclose(self) -> None:
        await self._http.aclose()
