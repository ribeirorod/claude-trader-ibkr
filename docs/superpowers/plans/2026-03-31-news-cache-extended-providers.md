# News Cache + Extended Provider Chain — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple news fetching from pipeline execution via a cached, background news fetcher with an extended provider chain (Marketaux → Benzinga → Finnhub → Alpha Vantage → EODHD).

**Architecture:** A new cron job (`news-fetcher`) runs every 2 hours on weekdays, fetching news per-ticker for all watchlist + held positions. Results are cached in `.trader/pipeline/news-cache.json` with a 4-hour TTL. Pipeline discover reads from cache first, falling back to live API only on cache miss. Three new news providers (Finnhub, Alpha Vantage, EODHD) extend the existing fallback chain.

**Tech Stack:** Python 3.12, httpx, Pydantic, APScheduler, pytest + pytest-asyncio

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `trader/news/finnhub.py` | Create | Finnhub news provider |
| `trader/news/alphavantage.py` | Create | Alpha Vantage NEWS_SENTIMENT provider |
| `trader/news/eodhd.py` | Create | EODHD news provider |
| `trader/news/cache.py` | Create | Read/write news cache with TTL |
| `trader/news/factory.py` | Modify | Add new providers to chain |
| `trader/config.py` | Modify | Add 3 new API key env vars |
| `trader/pipeline/discover.py` | Modify | Read from cache in `_enrich_with_news` |
| `scripts/news-fetcher.py` | Create | Background per-ticker news fetcher script |
| `.claude/crons.json` | Modify | Add `news-fetcher` cron entry |
| `.env.example` | Modify | Document new env vars |
| `tests/unit/test_news_finnhub.py` | Create | Finnhub provider tests |
| `tests/unit/test_news_alphavantage.py` | Create | Alpha Vantage provider tests |
| `tests/unit/test_news_eodhd.py` | Create | EODHD provider tests |
| `tests/unit/test_news_cache.py` | Create | Cache read/write/TTL tests |
| `tests/unit/test_news_chain.py` | Modify | Update factory test for new provider count |

---

### Task 1: Add API key config fields

**Files:**
- Modify: `trader/config.py:19-21`
- Modify: `.env.example`

- [ ] **Step 1: Add env vars to Config**

Add after line 21 (`massive_api_key`):

```python
finnhub_api_key: str = field(default_factory=lambda: os.getenv("FINNHUB_API_KEY", ""))
alphavantage_api_key: str = field(default_factory=lambda: os.getenv("ALPHAVANTAGE_API_KEY", ""))
eodhd_api_key: str = field(default_factory=lambda: os.getenv("EODHD_API_KEY", ""))
```

- [ ] **Step 2: Update .env.example**

Add after the Benzinga section:

```bash
# =============================================================================
# News — Marketaux  https://www.marketaux.com (primary, free tier: 100 req/day)
# =============================================================================
MARKETAUX_API_KEY=

# =============================================================================
# News — Finnhub  https://finnhub.io (free tier: 60 calls/min)
# =============================================================================
FINNHUB_API_KEY=

# =============================================================================
# News — Alpha Vantage  https://www.alphavantage.co (free tier: 25 calls/day)
# =============================================================================
ALPHAVANTAGE_API_KEY=

# =============================================================================
# News — EODHD  https://eodhd.com (free tier: 20 calls/day, built-in sentiment)
# =============================================================================
EODHD_API_KEY=
```

- [ ] **Step 3: Verify imports still work**

Run: `uv run python -c "from trader.config import Config; c = Config(); print(c.finnhub_api_key, c.alphavantage_api_key, c.eodhd_api_key)"`
Expected: three empty strings

- [ ] **Step 4: Commit**

```bash
git add trader/config.py .env.example
git commit -m "feat: add Finnhub, Alpha Vantage, EODHD API key config"
```

---

### Task 2: Finnhub news provider

**Files:**
- Create: `trader/news/finnhub.py`
- Create: `tests/unit/test_news_finnhub.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_news_finnhub.py`:

```python
# tests/unit/test_news_finnhub.py
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
import httpx


def _finnhub_response():
    """Simulate Finnhub /company-news response."""
    return [
        {
            "category": "company",
            "datetime": 1711900000,
            "headline": "NVDA GTC: Blackwell GPU unveiled",
            "id": 12345,
            "image": "",
            "related": "NVDA",
            "source": "Reuters",
            "summary": "NVIDIA announces next-gen Blackwell architecture at GTC conference.",
            "url": "https://example.com/nvda",
        },
        {
            "category": "company",
            "datetime": 1711890000,
            "headline": "NVDA partners with Microsoft on AI",
            "id": 12346,
            "image": "",
            "related": "NVDA",
            "source": "Bloomberg",
            "summary": "New cloud AI partnership announced.",
            "url": "https://example.com/nvda2",
        },
    ]


@pytest.mark.asyncio
async def test_finnhub_returns_news_items():
    from trader.news.finnhub import FinnhubProvider

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = _finnhub_response()
    mock_response.raise_for_status = MagicMock()

    with patch("trader.news.finnhub.httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value
        instance.get = AsyncMock(return_value=mock_response)
        instance.aclose = AsyncMock()

        provider = FinnhubProvider("test-key")
        items = await provider.get_news(["NVDA"], limit=5)

    assert len(items) == 2
    assert items[0].ticker == "NVDA"
    assert items[0].headline == "NVDA GTC: Blackwell GPU unveiled"
    assert items[0].source == "Reuters"


@pytest.mark.asyncio
async def test_finnhub_returns_empty_on_error():
    from trader.news.finnhub import FinnhubProvider

    with patch("trader.news.finnhub.httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value
        instance.get = AsyncMock(side_effect=httpx.HTTPError("timeout"))
        instance.aclose = AsyncMock()

        provider = FinnhubProvider("test-key")
        items = await provider.get_news(["NVDA"], limit=5)

    assert items == []


@pytest.mark.asyncio
async def test_finnhub_queries_per_ticker():
    """Finnhub API is per-ticker, so multiple tickers = multiple calls."""
    from trader.news.finnhub import FinnhubProvider

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = _finnhub_response()
    mock_response.raise_for_status = MagicMock()

    with patch("trader.news.finnhub.httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value
        instance.get = AsyncMock(return_value=mock_response)
        instance.aclose = AsyncMock()

        provider = FinnhubProvider("test-key")
        items = await provider.get_news(["NVDA", "AAPL"], limit=3)

    # Should have called get twice (once per ticker)
    assert instance.get.await_count == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_news_finnhub.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Write implementation**

Create `trader/news/finnhub.py`:

```python
# trader/news/finnhub.py
"""Finnhub news provider — free tier: 60 calls/min.
https://finnhub.io/docs/api/company-news
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from trader.models import NewsItem
from trader.news.base import NewsProvider


class FinnhubProvider(NewsProvider):
    _BASE = "https://finnhub.io/api/v1/company-news"

    def __init__(self, api_key: str) -> None:
        self._key = api_key
        self._http = httpx.AsyncClient(timeout=15.0)

    async def get_news(self, tickers: list[str], limit: int = 10) -> list[NewsItem]:
        now = datetime.now(timezone.utc)
        date_from = (now - timedelta(days=3)).strftime("%Y-%m-%d")
        date_to = now.strftime("%Y-%m-%d")

        all_items: list[NewsItem] = []
        for ticker in tickers:
            try:
                r = await self._http.get(
                    self._BASE,
                    params={
                        "symbol": ticker,
                        "from": date_from,
                        "to": date_to,
                        "token": self._key,
                    },
                )
                r.raise_for_status()
            except Exception:
                continue

            for article in r.json()[:limit]:
                ts = article.get("datetime", 0)
                published = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                all_items.append(
                    NewsItem(
                        id=str(article.get("id", "")),
                        ticker=ticker,
                        headline=article.get("headline", ""),
                        summary=article.get("summary", ""),
                        published_at=published,
                        source=article.get("source", "finnhub"),
                        url=article.get("url", ""),
                    )
                )
        return all_items

    async def aclose(self) -> None:
        await self._http.aclose()
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_news_finnhub.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add trader/news/finnhub.py tests/unit/test_news_finnhub.py
git commit -m "feat: add Finnhub news provider"
```

---

### Task 3: Alpha Vantage news provider

**Files:**
- Create: `trader/news/alphavantage.py`
- Create: `tests/unit/test_news_alphavantage.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_news_alphavantage.py`:

```python
# tests/unit/test_news_alphavantage.py
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx


def _av_response():
    """Simulate Alpha Vantage NEWS_SENTIMENT response."""
    return {
        "feed": [
            {
                "title": "AAPL reports record Q1 earnings",
                "url": "https://example.com/aapl",
                "time_published": "20260331T120000",
                "summary": "Apple beats analyst expectations with record revenue.",
                "source": "MarketWatch",
                "ticker_sentiment": [
                    {"ticker": "AAPL", "relevance_score": "0.95", "ticker_sentiment_score": "0.35"}
                ],
            },
            {
                "title": "Tech sector rallies on AI optimism",
                "url": "https://example.com/tech",
                "time_published": "20260331T100000",
                "summary": "Broad tech rally driven by AI earnings beats.",
                "source": "CNBC",
                "ticker_sentiment": [
                    {"ticker": "AAPL", "relevance_score": "0.60", "ticker_sentiment_score": "0.20"}
                ],
            },
        ]
    }


@pytest.mark.asyncio
async def test_alphavantage_returns_news_items():
    from trader.news.alphavantage import AlphaVantageProvider

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = _av_response()
    mock_response.raise_for_status = MagicMock()

    with patch("trader.news.alphavantage.httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value
        instance.get = AsyncMock(return_value=mock_response)
        instance.aclose = AsyncMock()

        provider = AlphaVantageProvider("test-key")
        items = await provider.get_news(["AAPL"], limit=5)

    assert len(items) == 2
    assert items[0].ticker == "AAPL"
    assert items[0].headline == "AAPL reports record Q1 earnings"
    assert items[0].source == "MarketWatch"


@pytest.mark.asyncio
async def test_alphavantage_returns_empty_on_error():
    from trader.news.alphavantage import AlphaVantageProvider

    with patch("trader.news.alphavantage.httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value
        instance.get = AsyncMock(side_effect=httpx.HTTPError("rate limited"))
        instance.aclose = AsyncMock()

        provider = AlphaVantageProvider("test-key")
        items = await provider.get_news(["AAPL"], limit=5)

    assert items == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_news_alphavantage.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

Create `trader/news/alphavantage.py`:

```python
# trader/news/alphavantage.py
"""Alpha Vantage NEWS_SENTIMENT provider — free tier: 25 calls/day.
https://www.alphavantage.co/documentation/#news-sentiment
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from trader.models import NewsItem
from trader.news.base import NewsProvider


class AlphaVantageProvider(NewsProvider):
    _BASE = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str) -> None:
        self._key = api_key
        self._http = httpx.AsyncClient(timeout=15.0)

    async def get_news(self, tickers: list[str], limit: int = 10) -> list[NewsItem]:
        params = {
            "function": "NEWS_SENTIMENT",
            "tickers": ",".join(tickers),
            "limit": limit,
            "apikey": self._key,
        }
        try:
            r = await self._http.get(self._BASE, params=params)
            r.raise_for_status()
        except Exception:
            return []

        items: list[NewsItem] = []
        for article in r.json().get("feed", [])[:limit]:
            # Find the most relevant ticker from ticker_sentiment
            ticker = tickers[0]
            for ts in article.get("ticker_sentiment", []):
                if ts.get("ticker") in tickers:
                    ticker = ts["ticker"]
                    break

            # Parse time_published: "20260331T120000"
            raw_time = article.get("time_published", "")
            try:
                dt = datetime.strptime(raw_time, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
                published = dt.isoformat()
            except (ValueError, AttributeError):
                published = raw_time

            items.append(
                NewsItem(
                    id=article.get("url", ""),
                    ticker=ticker,
                    headline=article.get("title", ""),
                    summary=article.get("summary", ""),
                    published_at=published,
                    source=article.get("source", "alphavantage"),
                    url=article.get("url", ""),
                )
            )
        return items

    async def aclose(self) -> None:
        await self._http.aclose()
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_news_alphavantage.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add trader/news/alphavantage.py tests/unit/test_news_alphavantage.py
git commit -m "feat: add Alpha Vantage news provider"
```

---

### Task 4: EODHD news provider

**Files:**
- Create: `trader/news/eodhd.py`
- Create: `tests/unit/test_news_eodhd.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_news_eodhd.py`:

```python
# tests/unit/test_news_eodhd.py
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx


def _eodhd_response():
    """Simulate EODHD /api/news response."""
    return [
        {
            "date": "2026-03-31T12:00:00+00:00",
            "title": "MSFT Azure revenue surges 40%",
            "content": "Microsoft reports strong Azure growth driven by AI workloads.",
            "link": "https://example.com/msft",
            "symbols": ["MSFT.US"],
            "tags": ["technology", "cloud"],
            "sentiment": {"polarity": 0.35, "neg": 0.05, "neu": 0.60, "pos": 0.35},
        },
    ]


@pytest.mark.asyncio
async def test_eodhd_returns_news_items():
    from trader.news.eodhd import EODHDProvider

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = _eodhd_response()
    mock_response.raise_for_status = MagicMock()

    with patch("trader.news.eodhd.httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value
        instance.get = AsyncMock(return_value=mock_response)
        instance.aclose = AsyncMock()

        provider = EODHDProvider("test-key")
        items = await provider.get_news(["MSFT"], limit=5)

    assert len(items) == 1
    assert items[0].ticker == "MSFT"
    assert items[0].headline == "MSFT Azure revenue surges 40%"


@pytest.mark.asyncio
async def test_eodhd_returns_empty_on_error():
    from trader.news.eodhd import EODHDProvider

    with patch("trader.news.eodhd.httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value
        instance.get = AsyncMock(side_effect=httpx.HTTPError("forbidden"))
        instance.aclose = AsyncMock()

        provider = EODHDProvider("test-key")
        items = await provider.get_news(["MSFT"], limit=5)

    assert items == []


@pytest.mark.asyncio
async def test_eodhd_strips_exchange_suffix_from_symbols():
    """EODHD returns symbols as 'MSFT.US' — we strip to 'MSFT'."""
    from trader.news.eodhd import EODHDProvider

    resp = _eodhd_response()
    resp[0]["symbols"] = ["MSFT.US", "AAPL.US"]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = resp
    mock_response.raise_for_status = MagicMock()

    with patch("trader.news.eodhd.httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value
        instance.get = AsyncMock(return_value=mock_response)
        instance.aclose = AsyncMock()

        provider = EODHDProvider("test-key")
        items = await provider.get_news(["MSFT"], limit=5)

    assert items[0].ticker == "MSFT"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_news_eodhd.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

Create `trader/news/eodhd.py`:

```python
# trader/news/eodhd.py
"""EODHD news provider — free tier: 20 calls/day, built-in sentiment.
https://eodhd.com/financial-apis/stock-market-financial-news-api
"""
from __future__ import annotations

import httpx

from trader.models import NewsItem
from trader.news.base import NewsProvider


class EODHDProvider(NewsProvider):
    _BASE = "https://eodhd.com/api/news"

    def __init__(self, api_key: str) -> None:
        self._key = api_key
        self._http = httpx.AsyncClient(timeout=15.0)

    async def get_news(self, tickers: list[str], limit: int = 10) -> list[NewsItem]:
        all_items: list[NewsItem] = []
        for ticker in tickers:
            try:
                r = await self._http.get(
                    self._BASE,
                    params={
                        "s": f"{ticker}.US",
                        "offset": 0,
                        "limit": limit,
                        "api_token": self._key,
                        "fmt": "json",
                    },
                )
                r.raise_for_status()
            except Exception:
                continue

            for article in r.json()[:limit]:
                # Find matching ticker from symbols list (format: "MSFT.US")
                symbols = article.get("symbols", [])
                matched = ticker
                for sym in symbols:
                    base = sym.split(".")[0]
                    if base.upper() == ticker.upper():
                        matched = base.upper()
                        break

                all_items.append(
                    NewsItem(
                        id=article.get("link", ""),
                        ticker=matched,
                        headline=article.get("title", ""),
                        summary=article.get("content", "")[:500],
                        published_at=article.get("date", ""),
                        source="eodhd",
                        url=article.get("link", ""),
                    )
                )
        return all_items

    async def aclose(self) -> None:
        await self._http.aclose()
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_news_eodhd.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add trader/news/eodhd.py tests/unit/test_news_eodhd.py
git commit -m "feat: add EODHD news provider"
```

---

### Task 5: Wire new providers into factory + chain

**Files:**
- Modify: `trader/news/factory.py`
- Modify: `tests/unit/test_news_chain.py`

- [ ] **Step 1: Update factory test**

In `tests/unit/test_news_chain.py`, update `mock_config` fixture and add new test:

```python
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
```

Update `test_factory_returns_chain_with_available_providers`:

```python
def test_factory_returns_chain_with_available_providers(mock_config):
    from trader.news.factory import get_news_provider
    from trader.news.chain import NewsProviderChain

    provider = get_news_provider(mock_config)
    assert isinstance(provider, NewsProviderChain)
    # marketaux + benzinga + finnhub + alphavantage + eodhd = 5
    assert len(provider.providers) == 5
```

Update `test_factory_skips_providers_with_no_key`:

```python
def test_factory_skips_providers_with_no_key(mock_config):
    from trader.news.factory import get_news_provider

    mock_config.marketaux_api_key = ""
    mock_config.benzinga_api_key = "bz-key"
    mock_config.massive_api_key = ""
    mock_config.finnhub_api_key = ""
    mock_config.alphavantage_api_key = ""
    mock_config.eodhd_api_key = ""
    provider = get_news_provider(mock_config)
    assert len(provider.providers) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_news_chain.py::test_factory_returns_chain_with_available_providers -v`
Expected: FAIL (still returns 2 providers)

- [ ] **Step 3: Update factory**

Replace `trader/news/factory.py` contents:

```python
# trader/news/factory.py
from __future__ import annotations
from trader.news.chain import NewsProviderChain
from trader.news.base import NewsProvider


def get_news_provider(config) -> NewsProviderChain:
    """
    Build the news provider chain from config.
    Order: Marketaux → Benzinga → Finnhub → Alpha Vantage → EODHD
    Providers with empty API keys are skipped.
    """
    providers: list[NewsProvider] = []

    if getattr(config, "marketaux_api_key", ""):
        from trader.news.marketaux import MarketauxProvider
        providers.append(MarketauxProvider(config.marketaux_api_key))

    if getattr(config, "benzinga_api_key", ""):
        from trader.news.benzinga import BenzingaClient
        providers.append(BenzingaClient(config))

    if getattr(config, "finnhub_api_key", ""):
        from trader.news.finnhub import FinnhubProvider
        providers.append(FinnhubProvider(config.finnhub_api_key))

    if getattr(config, "alphavantage_api_key", ""):
        from trader.news.alphavantage import AlphaVantageProvider
        providers.append(AlphaVantageProvider(config.alphavantage_api_key))

    if getattr(config, "eodhd_api_key", ""):
        from trader.news.eodhd import EODHDProvider
        providers.append(EODHDProvider(config.eodhd_api_key))

    return NewsProviderChain(providers)
```

- [ ] **Step 4: Run all chain tests**

Run: `uv run pytest tests/unit/test_news_chain.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add trader/news/factory.py tests/unit/test_news_chain.py
git commit -m "feat: wire Finnhub, Alpha Vantage, EODHD into news provider chain"
```

---

### Task 6: News cache module

**Files:**
- Create: `trader/news/cache.py`
- Create: `tests/unit/test_news_cache.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_news_cache.py`:

```python
# tests/unit/test_news_cache.py
from __future__ import annotations
import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from trader.models import NewsItem


def _make_item(ticker: str, headline: str) -> NewsItem:
    return NewsItem(
        id="1", ticker=ticker, headline=headline, summary="",
        published_at="2026-03-31T10:00:00Z", source="test",
    )


def test_write_and_read_cache(tmp_path: Path):
    from trader.news.cache import write_cache, read_cache

    items = [_make_item("NVDA", "NVDA beats earnings")]
    cache_path = tmp_path / "news-cache.json"

    write_cache(cache_path, "NVDA", items)
    result = read_cache(cache_path, "NVDA", ttl_hours=4)

    assert len(result) == 1
    assert result[0].headline == "NVDA beats earnings"


def test_read_cache_returns_empty_when_expired(tmp_path: Path):
    from trader.news.cache import write_cache, read_cache, _load_cache

    items = [_make_item("NVDA", "old news")]
    cache_path = tmp_path / "news-cache.json"

    write_cache(cache_path, "NVDA", items)

    # Manually backdate the timestamp
    data = _load_cache(cache_path)
    old_time = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
    data["NVDA"]["fetched_at"] = old_time
    cache_path.write_text(json.dumps(data))

    result = read_cache(cache_path, "NVDA", ttl_hours=4)
    assert result == []


def test_read_cache_returns_empty_for_missing_ticker(tmp_path: Path):
    from trader.news.cache import read_cache

    cache_path = tmp_path / "news-cache.json"
    result = read_cache(cache_path, "AAPL", ttl_hours=4)
    assert result == []


def test_write_cache_preserves_other_tickers(tmp_path: Path):
    from trader.news.cache import write_cache, read_cache

    cache_path = tmp_path / "news-cache.json"

    write_cache(cache_path, "NVDA", [_make_item("NVDA", "nvda news")])
    write_cache(cache_path, "AAPL", [_make_item("AAPL", "aapl news")])

    nvda = read_cache(cache_path, "NVDA", ttl_hours=4)
    aapl = read_cache(cache_path, "AAPL", ttl_hours=4)

    assert len(nvda) == 1
    assert len(aapl) == 1


def test_fresh_tickers_lists_non_expired(tmp_path: Path):
    from trader.news.cache import write_cache, fresh_tickers

    cache_path = tmp_path / "news-cache.json"
    write_cache(cache_path, "NVDA", [_make_item("NVDA", "news")])
    write_cache(cache_path, "AAPL", [_make_item("AAPL", "news")])

    fresh = fresh_tickers(cache_path, ttl_hours=4)
    assert "NVDA" in fresh
    assert "AAPL" in fresh
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_news_cache.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

Create `trader/news/cache.py`:

```python
# trader/news/cache.py
"""TTL-based news cache — stores per-ticker news items as JSON."""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from trader.models import NewsItem


def _load_cache(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def write_cache(path: Path, ticker: str, items: list[NewsItem]) -> None:
    """Write news items for a single ticker to the cache."""
    data = _load_cache(path)
    data[ticker] = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "items": [item.model_dump() for item in items],
    }
    _save_cache(path, data)


def read_cache(
    path: Path, ticker: str, ttl_hours: float = 4.0
) -> list[NewsItem]:
    """Read cached news for a ticker. Returns [] if expired or missing."""
    data = _load_cache(path)
    entry = data.get(ticker)
    if not entry:
        return []

    try:
        fetched = datetime.fromisoformat(entry["fetched_at"])
    except (ValueError, KeyError):
        return []

    if datetime.now(timezone.utc) - fetched > timedelta(hours=ttl_hours):
        return []

    return [NewsItem(**item) for item in entry.get("items", [])]


def fresh_tickers(path: Path, ttl_hours: float = 4.0) -> set[str]:
    """Return set of tickers whose cache is still fresh."""
    data = _load_cache(path)
    now = datetime.now(timezone.utc)
    fresh: set[str] = set()
    for ticker, entry in data.items():
        try:
            fetched = datetime.fromisoformat(entry["fetched_at"])
            if now - fetched <= timedelta(hours=ttl_hours):
                fresh.add(ticker)
        except (ValueError, KeyError):
            continue
    return fresh
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_news_cache.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add trader/news/cache.py tests/unit/test_news_cache.py
git commit -m "feat: add TTL-based news cache module"
```

---

### Task 7: News fetcher script

**Files:**
- Create: `scripts/news-fetcher.py`

- [ ] **Step 1: Write the fetcher script**

Create `scripts/news-fetcher.py`:

```python
#!/usr/bin/env python3
"""Background news fetcher — runs via cron every 2 hours.

Fetches news per-ticker for all watchlist + held positions.
Writes to .trader/pipeline/news-cache.json with timestamps.
Skips tickers with fresh cache (< TTL_HOURS).
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from trader.config import Config
from trader.news.cache import write_cache, fresh_tickers
from trader.news.factory import get_news_provider
from trader.notify import send_telegram

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TTL_HOURS = 4.0
CACHE_PATH = ROOT / ".trader" / "pipeline" / "news-cache.json"
WATCHLIST_PATH = ROOT / "outputs" / "watchlists.json"
PER_TICKER_LIMIT = 5
DELAY_BETWEEN_TICKERS = 1.0  # seconds — respect rate limits


def _load_tickers() -> list[str]:
    """Load tickers from watchlists.json."""
    tickers: set[str] = set()
    if WATCHLIST_PATH.exists():
        data = json.loads(WATCHLIST_PATH.read_text())
        for _name, wl in data.items():
            for t in wl.get("tickers", []):
                tickers.add(t)
    return sorted(tickers)


async def main() -> None:
    config = Config()
    provider = get_news_provider(config)

    all_tickers = _load_tickers()
    if not all_tickers:
        logger.warning("No tickers found in watchlists")
        return

    # Skip tickers with fresh cache
    fresh = fresh_tickers(CACHE_PATH, ttl_hours=TTL_HOURS)
    stale = [t for t in all_tickers if t not in fresh]

    if not stale:
        logger.info("All %d tickers have fresh cache, nothing to fetch", len(all_tickers))
        return

    logger.info("Fetching news for %d/%d tickers (%d fresh, skipped)",
                len(stale), len(all_tickers), len(fresh))

    fetched = 0
    failed = 0
    for ticker in stale:
        try:
            items = await provider.get_news([ticker], limit=PER_TICKER_LIMIT)
            write_cache(CACHE_PATH, ticker, items)
            fetched += 1
            if items:
                logger.info("  %s: %d articles", ticker, len(items))
            else:
                logger.info("  %s: no articles found", ticker)
        except Exception as exc:
            logger.warning("  %s: failed (%s)", ticker, exc)
            failed += 1

        # Respect rate limits
        await asyncio.sleep(DELAY_BETWEEN_TICKERS)

    await provider.aclose()

    msg = f"News fetcher: {fetched} tickers updated, {failed} failed, {len(fresh)} skipped (fresh)"
    logger.info(msg)
    send_telegram(msg)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Verify it runs (dry)**

Run: `uv run python scripts/news-fetcher.py`
Expected: runs, logs tickers, writes to `.trader/pipeline/news-cache.json`

- [ ] **Step 3: Commit**

```bash
git add scripts/news-fetcher.py
git commit -m "feat: add background news fetcher script"
```

---

### Task 8: Update pipeline discover to use cache

**Files:**
- Modify: `trader/pipeline/discover.py:174-228`
- Modify: `trader/cli/pipeline.py`

- [ ] **Step 1: Update `_enrich_with_news` to read cache first**

In `trader/pipeline/discover.py`, update the function signature and body of `_enrich_with_news`:

```python
async def _enrich_with_news(
    sectors: dict[str, list[Candidate]],
    news_fn: Callable,
    top_n: int = 20,
    cache_path: Path | None = None,
    cache_ttl_hours: float = 4.0,
) -> tuple[dict[str, list[Candidate]], dict[str, float]]:
    """Enrich top candidates with news. Reads cache first, falls back to live API."""
    from trader.news.cache import read_cache

    all_candidates = [c for cands in sectors.values() for c in cands]
    all_candidates.sort(
        key=lambda c: (0 if c.priority == "high" else 1, -c.scan_score)
    )
    top_tickers = [c.ticker for c in all_candidates[:top_n]]

    if not top_tickers:
        return sectors, {}

    # Try cache first, then live API for misses
    all_news_items: list = []
    cache_misses: list[str] = []

    if cache_path:
        for ticker in top_tickers:
            cached = read_cache(cache_path, ticker, ttl_hours=cache_ttl_hours)
            if cached:
                all_news_items.extend(cached)
            else:
                cache_misses.append(ticker)
    else:
        cache_misses = top_tickers

    # Fetch remaining from live API
    if cache_misses:
        try:
            live_items = await news_fn(tickers=cache_misses, limit=5 * len(cache_misses))
            all_news_items.extend(live_items)
        except Exception:
            pass

    news_items = all_news_items

    # Group raw NewsItems by ticker for SentimentScorer
    from trader.models import NewsItem
    raw_by_ticker: dict[str, list[NewsItem]] = {}
    for item in news_items:
        ticker = getattr(item, "ticker", None)
        if ticker:
            raw_by_ticker.setdefault(ticker, []).append(item)

    # Compute per-ticker aggregate sentiment
    scorer = SentimentScorer()
    ticker_sentiment: dict[str, float] = {}
    for ticker, items in raw_by_ticker.items():
        result = scorer.score(ticker=ticker, items=items)
        ticker_sentiment[ticker] = result.score

    # Build per-headline CandidateNews with real sentiment scores
    news_by_ticker: dict[str, list[CandidateNews]] = {}
    for ticker, items in raw_by_ticker.items():
        for item in items:
            raw_score = _score_item(item)
            clamped = max(-1.0, min(1.0, raw_score * 10))
            news_by_ticker.setdefault(ticker, []).append(
                CandidateNews(headline=item.headline, sentiment=clamped)
            )

    # Apply news to candidates
    for sector_candidates in sectors.values():
        for i, c in enumerate(sector_candidates):
            if c.ticker in news_by_ticker:
                sector_candidates[i] = c.model_copy(update={
                    "news": news_by_ticker[c.ticker],
                })

    return sectors, ticker_sentiment
```

- [ ] **Step 2: Update `run_discover` to pass cache_path**

In `trader/pipeline/discover.py`, update the `run_discover` function signature and the `_enrich_with_news` call:

```python
async def run_discover(
    regime: str,
    watchlist_path: Path,
    pipeline_dir: Path,
    scan_fn: Callable,
    news_fn: Callable,
) -> CandidateSet:
    # ... (keep existing code until line 353)
    sectors = _merge_candidates(watchlist_candidates, scan_candidates)

    cache_path = pipeline_dir / "news-cache.json"
    sectors, ticker_sentiment = await _enrich_with_news(
        sectors, news_fn, cache_path=cache_path,
    )
    # ... (rest unchanged)
```

- [ ] **Step 3: Run existing tests**

Run: `uv run pytest tests/unit/test_cli_pipeline.py tests/unit/test_news_chain.py -v`
Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add trader/pipeline/discover.py
git commit -m "feat: pipeline discover reads from news cache, falls back to live API"
```

---

### Task 9: Add news-fetcher cron job

**Files:**
- Modify: `.claude/crons.json`

- [ ] **Step 1: Add cron entry**

Add to `.claude/crons.json` array (before the closing `]`):

```json
{
  "id": "news-fetcher",
  "cron": "10 7,9,11,13,15,17 * * 1-5",
  "label": "Weekdays every 2h (7:10am–5:10pm CET) — background news fetcher",
  "agent": "system",
  "cmd": "uv run python scripts/news-fetcher.py",
  "prompt": "Fetch news for all watchlist tickers. Caches results in .trader/pipeline/news-cache.json with 4-hour TTL. Skips tickers with fresh cache."
}
```

- [ ] **Step 2: Verify crons.json is valid JSON**

Run: `uv run python -c "import json; json.load(open('.claude/crons.json')); print('OK')"`
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add .claude/crons.json
git commit -m "feat: add news-fetcher cron job (every 2h weekdays)"
```

---

### Task 10: Integration verification

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/unit/ -v --ignore=tests/unit/server/test_agent.py`
Expected: all pass (test_agent.py has pre-existing failure unrelated to this work)

- [ ] **Step 2: Smoke test the fetcher locally**

Run: `uv run python scripts/news-fetcher.py`
Expected: fetches news, writes cache, logs summary

- [ ] **Step 3: Verify cache file**

Run: `uv run python -c "import json; d = json.load(open('.trader/pipeline/news-cache.json')); print(f'{len(d)} tickers cached'); print(list(d.keys())[:10])"`
Expected: shows cached tickers

- [ ] **Step 4: Final commit with all changes**

If any uncommitted work remains:
```bash
git add -A && git commit -m "chore: integration verification cleanup"
```
