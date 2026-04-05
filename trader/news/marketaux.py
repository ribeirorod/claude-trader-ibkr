# trader/news/marketaux.py
from __future__ import annotations
import asyncio
import logging
import httpx
from trader.models import NewsItem
from trader.news.base import NewsProvider

logger = logging.getLogger(__name__)

# Free tier: 3 articles/request, 100 requests/day.
# Batch tickers in groups of 3 so each batch gets ~1 article per ticker.
_BATCH_SIZE = 3
_ARTICLES_PER_REQUEST = 3


class MarketauxProvider(NewsProvider):
    """
    Marketaux news API — free tier: 100 req/day, 3 articles/req.
    https://www.marketaux.com/documentation

    Batches tickers in groups of 3 to maximize coverage
    (1 request per batch × 3 articles = ~1 article per ticker).
    """
    _BASE = "https://api.marketaux.com/v1/news/all"

    def __init__(self, api_key: str) -> None:
        self._key = api_key
        self._http = httpx.AsyncClient(timeout=15.0)

    async def _fetch_batch(self, tickers: list[str]) -> list[NewsItem]:
        """Fetch news for a small batch of tickers (1 API request)."""
        params = {
            "api_token": self._key,
            "symbols": ",".join(tickers),
            "limit": _ARTICLES_PER_REQUEST,
            "language": "en",
            "must_have_entities": "true",
        }
        try:
            r = await self._http.get(self._BASE, params=params)
            r.raise_for_status()
        except Exception as exc:
            logger.debug("Marketaux batch %s failed: %s", tickers, exc)
            return []

        seen_ids: set[str] = set()
        items: list[NewsItem] = []
        requested = {t.upper() for t in tickers}

        for article in r.json().get("data", []):
            article_id = article.get("uuid", "")
            if article_id in seen_ids:
                continue
            seen_ids.add(article_id)

            # Emit one NewsItem per matched ticker in entities
            entities = article.get("entities", [])
            matched_tickers = [
                e.get("symbol", "")
                for e in entities
                if e.get("symbol", "").upper() in requested
            ]
            if not matched_tickers:
                matched_tickers = [tickers[0]]

            for ticker in matched_tickers:
                items.append(NewsItem(
                    id=article_id,
                    ticker=ticker,
                    headline=article.get("title", ""),
                    summary=article.get("description", ""),
                    published_at=article.get("published_at", ""),
                    source=article.get("source", "marketaux"),
                    url=article.get("url", ""),
                ))
        return items

    async def get_news(self, tickers: list[str], limit: int = 10) -> list[NewsItem]:
        if not tickers:
            return []

        # Split into small batches for better coverage
        batches = [
            tickers[i:i + _BATCH_SIZE]
            for i in range(0, len(tickers), _BATCH_SIZE)
        ]

        # Run batches concurrently (respects rate limits via small batch count)
        results = await asyncio.gather(
            *(self._fetch_batch(batch) for batch in batches),
            return_exceptions=True,
        )

        all_items: list[NewsItem] = []
        for result in results:
            if isinstance(result, list):
                all_items.extend(result)

        logger.info(
            "Marketaux: %d batches, %d articles for %d tickers",
            len(batches), len(all_items), len(tickers),
        )
        return all_items

    async def aclose(self) -> None:
        await self._http.aclose()
