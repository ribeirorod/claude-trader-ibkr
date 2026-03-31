# tests/unit/test_news_finnhub.py
from __future__ import annotations

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from trader.models import NewsItem
from trader.news.finnhub import FinnhubProvider


SAMPLE_RESPONSE = [
    {
        "id": 123456,
        "datetime": 1711900800,  # 2024-03-31T16:00:00Z
        "headline": "NVDA beats Q4 estimates",
        "summary": "Nvidia reported record revenue.",
        "source": "Reuters",
        "url": "https://example.com/nvda-q4",
        "related": "NVDA",
    },
    {
        "id": 123457,
        "datetime": 1711897200,  # 2024-03-31T15:00:00Z
        "headline": "NVDA announces new GPU",
        "summary": "Blackwell architecture revealed.",
        "source": "Bloomberg",
        "url": "https://example.com/nvda-gpu",
        "related": "NVDA",
    },
]


@pytest.mark.asyncio
async def test_finnhub_returns_news_items():
    """Mock httpx response with sample data, verify NewsItem fields."""
    provider = FinnhubProvider(api_key="test-key")

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = SAMPLE_RESPONSE

    provider._http.get = AsyncMock(return_value=mock_response)

    items = await provider.get_news(["NVDA"], limit=10)

    assert len(items) == 2
    assert items[0].id == "123456"
    assert items[0].ticker == "NVDA"
    assert items[0].headline == "NVDA beats Q4 estimates"
    assert items[0].summary == "Nvidia reported record revenue."
    assert items[0].source == "Reuters"
    assert items[0].url == "https://example.com/nvda-q4"
    # Unix 1711900800 -> ISO with UTC timezone
    assert "2024-03-31" in items[0].published_at

    assert items[1].id == "123457"
    assert items[1].headline == "NVDA announces new GPU"

    await provider.aclose()


@pytest.mark.asyncio
async def test_finnhub_returns_empty_on_error():
    """Mock httpx to raise, verify returns []."""
    provider = FinnhubProvider(api_key="test-key")

    provider._http.get = AsyncMock(side_effect=httpx.HTTPStatusError(
        "Server Error", request=MagicMock(), response=MagicMock(),
    ))

    items = await provider.get_news(["NVDA"], limit=10)
    assert items == []

    await provider.aclose()


@pytest.mark.asyncio
async def test_finnhub_queries_per_ticker():
    """Verify multiple tickers = multiple HTTP calls (per-ticker API)."""
    provider = FinnhubProvider(api_key="test-key")

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = [SAMPLE_RESPONSE[0]]

    provider._http.get = AsyncMock(return_value=mock_response)

    items = await provider.get_news(["NVDA", "AAPL", "TSLA"], limit=10)

    # 3 tickers = 3 HTTP calls
    assert provider._http.get.await_count == 3
    # Each ticker returns 1 item -> 3 total
    assert len(items) == 3
    # Verify tickers are assigned correctly
    assert items[0].ticker == "NVDA"
    assert items[1].ticker == "AAPL"
    assert items[2].ticker == "TSLA"

    await provider.aclose()
