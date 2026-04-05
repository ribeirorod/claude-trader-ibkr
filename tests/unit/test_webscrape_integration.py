# tests/unit/test_webscrape_integration.py
"""Verify WebScrapeProvider works as chain fallback when all API providers fail."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock
from trader.models import NewsItem
from trader.news.base import NewsProvider
from trader.news.chain import NewsProviderChain
from trader.news.webscrape import WebScrapeProvider


SCRAPE_ITEMS = [
    NewsItem(
        id="finviz1",
        ticker="NVDA",
        headline="NVDA GTC keynote: Blackwell GPU unveiled",
        summary="",
        published_at="2026-04-03T10:00:00",
        source="Reuters",
        url="https://example.com/nvda",
    )
]


@pytest.mark.asyncio
async def test_chain_falls_back_to_webscrape():
    """When all API providers fail, WebScrapeProvider returns data."""
    api_provider = MagicMock(spec=NewsProvider)
    api_provider.get_news = AsyncMock(side_effect=RuntimeError("API key exhausted"))
    api_provider.aclose = AsyncMock()

    scrape_provider = WebScrapeProvider()

    async def mock_get_news(tickers, limit=10):
        return SCRAPE_ITEMS

    scrape_provider.get_news = mock_get_news

    chain = NewsProviderChain([api_provider, scrape_provider])
    result = await chain.get_news(["NVDA"], limit=5)

    assert len(result) == 1
    assert result[0].headline == "NVDA GTC keynote: Blackwell GPU unveiled"

    api_provider.get_news.assert_awaited_once()
    await chain.aclose()


@pytest.mark.asyncio
async def test_chain_prefers_api_over_webscrape():
    """When API provider succeeds, WebScrapeProvider is never called."""
    api_items = [
        NewsItem(
            id="api1",
            ticker="NVDA",
            headline="NVDA from API",
            summary="",
            published_at="2026-04-03T10:00:00",
            source="marketaux",
        )
    ]

    api_provider = MagicMock(spec=NewsProvider)
    api_provider.get_news = AsyncMock(return_value=api_items)
    api_provider.aclose = AsyncMock()

    scrape_provider = MagicMock(spec=NewsProvider)
    scrape_provider.get_news = AsyncMock(return_value=SCRAPE_ITEMS)
    scrape_provider.aclose = AsyncMock()

    chain = NewsProviderChain([api_provider, scrape_provider])
    result = await chain.get_news(["NVDA"], limit=5)

    assert result[0].source == "marketaux"
    scrape_provider.get_news.assert_not_awaited()
    await chain.aclose()
