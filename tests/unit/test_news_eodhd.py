# tests/unit/test_news_eodhd.py
from __future__ import annotations

import pytest
import httpx
from unittest.mock import AsyncMock, patch

from trader.news.eodhd import EODHDProvider


SAMPLE_RESPONSE = [
    {
        "date": "2026-03-30T14:00:00+00:00",
        "title": "Microsoft announces new AI features",
        "content": "Microsoft Corp announced a suite of new AI-powered features " * 20,
        "link": "https://example.com/msft-ai",
        "symbols": ["MSFT.US"],
        "tags": ["AI", "Technology"],
        "sentiment": {"polarity": 0.3, "neg": 0.1, "neu": 0.5, "pos": 0.4},
    },
]


@pytest.mark.asyncio
async def test_eodhd_returns_news_items():
    """Mock successful response — verify all NewsItem fields."""
    provider = EODHDProvider(api_key="test-key")

    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.raise_for_status = lambda: None
    mock_response.json.return_value = SAMPLE_RESPONSE

    with patch.object(provider._http, "get", return_value=mock_response) as mock_get:
        items = await provider.get_news(["MSFT"], limit=5)

    assert len(items) == 1
    item = items[0]
    assert item.ticker == "MSFT"
    assert item.headline == "Microsoft announces new AI features"
    assert item.published_at == "2026-03-30T14:00:00+00:00"
    assert item.source == "eodhd"
    assert item.url == "https://example.com/msft-ai"
    assert len(item.summary) <= 500

    # Verify API was called with correct params
    mock_get.assert_awaited_once()
    call_kwargs = mock_get.call_args
    assert call_kwargs.kwargs["params"]["s"] == "MSFT.US"
    assert call_kwargs.kwargs["params"]["fmt"] == "json"

    await provider.aclose()


@pytest.mark.asyncio
async def test_eodhd_returns_empty_on_error():
    """HTTP error returns empty list, no exception raised."""
    provider = EODHDProvider(api_key="test-key")

    with patch.object(
        provider._http, "get", side_effect=httpx.HTTPStatusError(
            "Server Error", request=httpx.Request("GET", "https://eodhd.com/api/news"),
            response=httpx.Response(500),
        ),
    ):
        items = await provider.get_news(["MSFT"], limit=5)

    assert items == []
    await provider.aclose()


@pytest.mark.asyncio
async def test_eodhd_strips_exchange_suffix_from_symbols():
    """Symbols like 'MSFT.US' should become 'MSFT' in the ticker field."""
    response_data = [
        {
            "date": "2026-03-30T10:00:00+00:00",
            "title": "Test headline",
            "content": "Short content",
            "link": "https://example.com/1",
            "symbols": ["AAPL.US", "GOOG.US"],
            "tags": [],
            "sentiment": {},
        },
    ]

    provider = EODHDProvider(api_key="test-key")

    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.raise_for_status = lambda: None
    mock_response.json.return_value = response_data

    with patch.object(provider._http, "get", return_value=mock_response):
        items = await provider.get_news(["AAPL"], limit=5)

    assert len(items) == 1
    assert items[0].ticker == "AAPL"  # Not "AAPL.US"

    await provider.aclose()
