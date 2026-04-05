# tests/unit/test_webscrape_provider.py
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, patch
from trader.models import NewsItem
from trader.news.base import NewsProvider


FAKE_ITEMS = [
    NewsItem(
        id="abc123",
        ticker="AAPL",
        headline="Apple beats estimates",
        summary="",
        published_at="2026-04-03T15:56:00",
        source="Reuters",
        url="https://example.com/article1",
    )
]


@pytest.mark.asyncio
async def test_webscrape_provider_implements_interface():
    from trader.news.webscrape import WebScrapeProvider

    provider = WebScrapeProvider()
    assert isinstance(provider, NewsProvider)
    await provider.aclose()


@pytest.mark.asyncio
async def test_webscrape_provider_calls_finviz_per_ticker():
    from trader.news.webscrape import WebScrapeProvider

    provider = WebScrapeProvider()

    with patch(
        "trader.news.webscrape.fetch_finviz_news",
        new_callable=AsyncMock,
        return_value=FAKE_ITEMS,
    ) as mock_fetch:
        result = await provider.get_news(["AAPL", "MSFT"], limit=5)
        assert mock_fetch.await_count == 2
        tickers_called = [call.args[1] for call in mock_fetch.call_args_list]
        assert "AAPL" in tickers_called
        assert "MSFT" in tickers_called

    assert len(result) == 2  # FAKE_ITEMS returned for each ticker
    await provider.aclose()


@pytest.mark.asyncio
async def test_webscrape_provider_rate_limits():
    """Verify delay between requests (at least 0.5s gap)."""
    import time
    from trader.news.webscrape import WebScrapeProvider

    provider = WebScrapeProvider()
    call_times = []

    async def mock_fetch(client, ticker, *, limit=20):
        call_times.append(time.monotonic())
        return FAKE_ITEMS

    with patch("trader.news.webscrape.fetch_finviz_news", side_effect=mock_fetch):
        await provider.get_news(["AAPL", "MSFT", "GOOG"], limit=5)

    for i in range(1, len(call_times)):
        assert call_times[i] - call_times[i - 1] >= 0.4  # small tolerance
    await provider.aclose()


@pytest.mark.asyncio
async def test_webscrape_provider_handles_partial_failure():
    from trader.news.webscrape import WebScrapeProvider

    provider = WebScrapeProvider()

    async def mock_fetch(client, ticker, *, limit=20):
        if ticker == "MSFT":
            return []
        return FAKE_ITEMS

    with patch("trader.news.webscrape.fetch_finviz_news", side_effect=mock_fetch):
        result = await provider.get_news(["AAPL", "MSFT"], limit=5)

    assert len(result) == 1
    assert result[0].ticker == "AAPL"
    await provider.aclose()
