# tests/unit/test_news_alphavantage.py
from __future__ import annotations

import httpx
import pytest
from unittest.mock import AsyncMock, patch

from trader.news.alphavantage import AlphaVantageProvider


MOCK_RESPONSE = {
    "feed": [
        {
            "title": "NVDA surges on AI demand",
            "url": "https://example.com/nvda-ai",
            "time_published": "20260331T120000",
            "summary": "NVIDIA stock rallies after earnings beat.",
            "source": "TestNews",
            "ticker_sentiment": [
                {
                    "ticker": "NVDA",
                    "relevance_score": "0.95",
                    "ticker_sentiment_score": "0.85",
                },
            ],
        },
        {
            "title": "Market roundup",
            "url": "https://example.com/roundup",
            "time_published": "20260331T140000",
            "summary": "Broad market summary.",
            "source": "MarketWatch",
            "ticker_sentiment": [
                {
                    "ticker": "SPY",
                    "relevance_score": "0.50",
                    "ticker_sentiment_score": "0.10",
                },
            ],
        },
    ],
}


@pytest.mark.asyncio
async def test_alphavantage_returns_news_items():
    """Mock response produces correct NewsItem fields and time parsing."""
    provider = AlphaVantageProvider(api_key="test-key")

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = lambda: None
    mock_response.json = lambda: MOCK_RESPONSE

    with patch.object(provider._http, "get", return_value=mock_response) as mock_get:
        items = await provider.get_news(["NVDA"], limit=5)

    assert len(items) == 2

    # First article matches requested ticker
    assert items[0].ticker == "NVDA"
    assert items[0].headline == "NVDA surges on AI demand"
    assert items[0].summary == "NVIDIA stock rallies after earnings beat."
    assert items[0].published_at == "2026-03-31T12:00:00"
    assert items[0].source == "TestNews"
    assert items[0].url == "https://example.com/nvda-ai"

    # Second article has no matching ticker
    assert items[1].ticker is None
    assert items[1].published_at == "2026-03-31T14:00:00"

    # Verify API call params
    mock_get.assert_awaited_once()
    call_kwargs = mock_get.call_args
    params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
    assert params["function"] == "NEWS_SENTIMENT"
    assert params["tickers"] == "NVDA"
    assert params["apikey"] == "test-key"

    await provider.aclose()


@pytest.mark.asyncio
async def test_alphavantage_returns_empty_on_error():
    """Provider returns [] on HTTP error."""
    provider = AlphaVantageProvider(api_key="test-key")

    with patch.object(
        provider._http,
        "get",
        side_effect=httpx.HTTPStatusError(
            "Server Error",
            request=httpx.Request("GET", "https://example.com"),
            response=httpx.Response(500),
        ),
    ):
        items = await provider.get_news(["AAPL"], limit=5)

    assert items == []

    await provider.aclose()
