# tests/unit/test_news_chain.py
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from trader.models import NewsItem


def _make_items(ticker: str, headlines: list[str], score_override: float | None = None) -> list[NewsItem]:
    return [
        NewsItem(id=str(i), ticker=ticker, headline=h, summary="",
                 published_at="2026-03-19T10:00:00Z", source="test")
        for i, h in enumerate(headlines)
    ]


def _stub_items(ticker: str) -> list[NewsItem]:
    """Simulate Benzinga stub: 3 articles with identical generic headlines."""
    return _make_items(ticker, [
        "Iran cyberattack on Stryker",
        "BYD enters F1",
        "Energean Angola deal",
    ])


@pytest.fixture
def mock_config():
    cfg = MagicMock()
    cfg.benzinga_api_key = "bz-key"
    cfg.marketaux_api_key = "mx-key"
    cfg.massive_api_key = ""
    cfg.finnhub_api_key = "fh-key"
    cfg.alphavantage_api_key = "av-key"
    cfg.eodhd_api_key = "eod-key"
    return cfg


# ── stub detection ──────────────────────────────────────────────────────────

def test_is_stub_identical_headlines_across_tickers():
    """Identical headlines for different tickers = stub."""
    from trader.news.chain import is_stub

    items_nvda = _stub_items("NVDA")
    items_aapl = _stub_items("AAPL")
    assert is_stub(items_nvda + items_aapl, tickers=["NVDA", "AAPL"]) is True


def test_is_stub_returns_false_for_real_data():
    """Diverse headlines for different tickers = not stub."""
    from trader.news.chain import is_stub

    items = [
        NewsItem(id="1", ticker="NVDA", headline="NVDA GTC keynote: new Blackwell GPU",
                 summary="", published_at="2026-03-19T10:00:00Z", source="test"),
        NewsItem(id="2", ticker="AAPL", headline="Apple Vision Pro 2 delayed to 2027",
                 summary="", published_at="2026-03-19T10:00:00Z", source="test"),
    ]
    assert is_stub(items, tickers=["NVDA", "AAPL"]) is False


def test_is_stub_empty_list():
    """Empty result = treat as stub (no usable data)."""
    from trader.news.chain import is_stub
    assert is_stub([], tickers=["NVDA"]) is True


# ── chain fallback ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chain_returns_first_provider_when_good(mock_config):
    """Chain returns Marketaux result without trying Benzinga if data is good."""
    from trader.news.chain import NewsProviderChain
    from trader.news.base import NewsProvider

    good_items = _make_items("NVDA", ["NVDA GTC keynote: Blackwell GPU unveiled"])

    provider_a = MagicMock(spec=NewsProvider)
    provider_a.get_news = AsyncMock(return_value=good_items)
    provider_a.aclose = AsyncMock()

    provider_b = MagicMock(spec=NewsProvider)
    provider_b.get_news = AsyncMock(return_value=[])
    provider_b.aclose = AsyncMock()

    chain = NewsProviderChain([provider_a, provider_b])
    result = await chain.get_news(["NVDA"], limit=5)

    assert result == good_items
    provider_b.get_news.assert_not_awaited()


@pytest.mark.asyncio
async def test_chain_falls_back_when_stub(mock_config):
    """Chain skips stub result and tries next provider."""
    from trader.news.chain import NewsProviderChain
    from trader.news.base import NewsProvider

    stub = _stub_items("NVDA") + _stub_items("AAPL")  # same headlines = stub
    real = _make_items("NVDA", ["NVDA GTC: Blackwell GPU announced"])

    provider_a = MagicMock(spec=NewsProvider)
    provider_a.get_news = AsyncMock(return_value=stub)
    provider_a.aclose = AsyncMock()

    provider_b = MagicMock(spec=NewsProvider)
    provider_b.get_news = AsyncMock(return_value=real)
    provider_b.aclose = AsyncMock()

    chain = NewsProviderChain([provider_a, provider_b])
    result = await chain.get_news(["NVDA", "AAPL"], limit=5)

    assert result == real
    provider_b.get_news.assert_awaited_once()


@pytest.mark.asyncio
async def test_chain_falls_back_on_exception(mock_config):
    """Chain catches provider exception and tries next."""
    from trader.news.chain import NewsProviderChain
    from trader.news.base import NewsProvider

    real = _make_items("NVDA", ["NVDA beats estimates"])

    provider_a = MagicMock(spec=NewsProvider)
    provider_a.get_news = AsyncMock(side_effect=RuntimeError("API down"))
    provider_a.aclose = AsyncMock()

    provider_b = MagicMock(spec=NewsProvider)
    provider_b.get_news = AsyncMock(return_value=real)
    provider_b.aclose = AsyncMock()

    chain = NewsProviderChain([provider_a, provider_b])
    result = await chain.get_news(["NVDA"], limit=5)

    assert result == real


@pytest.mark.asyncio
async def test_chain_returns_empty_when_all_stub(mock_config):
    """Chain returns [] when all providers return stub data."""
    from trader.news.chain import NewsProviderChain
    from trader.news.base import NewsProvider

    provider_a = MagicMock(spec=NewsProvider)
    provider_a.get_news = AsyncMock(return_value=[])
    provider_a.aclose = AsyncMock()

    chain = NewsProviderChain([provider_a])
    result = await chain.get_news(["NVDA"], limit=5)
    assert result == []


# ── factory ──────────────────────────────────────────────────────────────────

def test_factory_returns_chain_with_available_providers(mock_config):
    """get_news_provider returns a NewsProviderChain with providers for set keys."""
    from trader.news.factory import get_news_provider
    from trader.news.chain import NewsProviderChain

    provider = get_news_provider(mock_config)
    assert isinstance(provider, NewsProviderChain)
    # marketaux + benzinga + finnhub + alphavantage + eodhd + webscrape = 6
    assert len(provider.providers) == 6


def test_factory_skips_providers_with_no_key(mock_config):
    """get_news_provider omits providers whose API key is empty."""
    from trader.news.factory import get_news_provider
    from trader.news.chain import NewsProviderChain

    mock_config.marketaux_api_key = ""
    mock_config.benzinga_api_key = "bz-key"
    mock_config.massive_api_key = ""
    mock_config.finnhub_api_key = ""
    mock_config.alphavantage_api_key = ""
    mock_config.eodhd_api_key = ""
    provider = get_news_provider(mock_config)
    assert isinstance(provider, NewsProviderChain)
    # benzinga + webscrape = 2
    assert len(provider.providers) == 2


def test_factory_always_includes_webscrape_as_last_provider(mock_config):
    """WebScrapeProvider is always appended as the last provider, no API key needed."""
    from trader.news.factory import get_news_provider
    from trader.news.webscrape import WebScrapeProvider

    provider = get_news_provider(mock_config)
    assert isinstance(provider.providers[-1], WebScrapeProvider)


def test_factory_webscrape_present_even_with_no_keys():
    """Even with zero API keys, chain has WebScrapeProvider."""
    from unittest.mock import MagicMock
    from trader.news.factory import get_news_provider
    from trader.news.webscrape import WebScrapeProvider

    empty_config = MagicMock()
    empty_config.marketaux_api_key = ""
    empty_config.benzinga_api_key = ""
    empty_config.massive_api_key = ""
    empty_config.finnhub_api_key = ""
    empty_config.alphavantage_api_key = ""
    empty_config.eodhd_api_key = ""
    provider = get_news_provider(empty_config)
    assert len(provider.providers) == 1
    assert isinstance(provider.providers[0], WebScrapeProvider)
