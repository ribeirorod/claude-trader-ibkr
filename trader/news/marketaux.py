# trader/news/marketaux.py
from __future__ import annotations
import httpx
from trader.models import NewsItem
from trader.news.base import NewsProvider


class MarketauxProvider(NewsProvider):
    """
    Marketaux news API — free tier: 100 req/day, 3 articles/req.
    https://www.marketaux.com/documentation
    """
    _BASE = "https://api.marketaux.com/v1/news/all"

    def __init__(self, api_key: str) -> None:
        self._key = api_key
        self._http = httpx.AsyncClient(timeout=15.0)

    async def get_news(self, tickers: list[str], limit: int = 10) -> list[NewsItem]:
        params = {
            "api_token": self._key,
            "symbols": ",".join(tickers),
            "limit": min(limit, 3),   # free tier max
            "language": "en",
            "must_have_entities": "true",
        }
        try:
            r = await self._http.get(self._BASE, params=params)
            r.raise_for_status()
        except Exception:
            return []

        items = []
        for article in r.json().get("data", []):
            # Determine primary ticker from entities
            entities = article.get("entities", [])
            ticker = entities[0].get("symbol", tickers[0]) if entities else tickers[0]
            items.append(NewsItem(
                id=article.get("uuid", ""),
                ticker=ticker,
                headline=article.get("title", ""),
                summary=article.get("description", ""),
                published_at=article.get("published_at", ""),
                source=article.get("source", "marketaux"),
                url=article.get("url", ""),
            ))
        return items

    async def aclose(self) -> None:
        await self._http.aclose()
