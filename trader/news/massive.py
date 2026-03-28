# trader/news/massive.py
from __future__ import annotations
import httpx
from trader.models import NewsItem
from trader.news.base import NewsProvider


class MassiveProvider(NewsProvider):
    """
    Massive financial data API — https://massive.com/docs/rest/stocks/news
    Paid tier. Stub implementation — activate by setting MASSIVE_API_KEY.
    """
    _BASE = "https://api.massive.com/v2/reference/news"

    def __init__(self, api_key: str) -> None:
        self._key = api_key
        self._http = httpx.AsyncClient(
            timeout=15.0,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    async def get_news(self, tickers: list[str], limit: int = 10) -> list[NewsItem]:
        items = []
        for ticker in tickers:
            try:
                r = await self._http.get(
                    self._BASE,
                    params={"ticker": ticker, "limit": limit},
                )
                r.raise_for_status()
            except Exception:
                continue

            for article in r.json().get("results", []):
                items.append(NewsItem(
                    id=article.get("id", ""),
                    ticker=ticker,
                    headline=article.get("title", ""),
                    summary=article.get("description", ""),
                    published_at=article.get("published_utc", ""),
                    source=article.get("publisher", {}).get("name", "massive"),
                    url=article.get("article_url", ""),
                ))
        return items

    async def aclose(self) -> None:
        await self._http.aclose()
