# trader/news/finnhub.py
from __future__ import annotations

import datetime as dt

import httpx

from trader.models import NewsItem
from trader.news.base import NewsProvider


class FinnhubProvider(NewsProvider):
    """
    Finnhub company-news API — free tier: 60 calls/min.
    https://finnhub.io/docs/api/company-news
    Per-ticker API (one HTTP call per ticker, not batched).
    """

    _BASE = "https://finnhub.io/api/v1/company-news"

    def __init__(self, api_key: str) -> None:
        self._key = api_key
        self._http = httpx.AsyncClient(timeout=15.0)

    async def get_news(self, tickers: list[str], limit: int = 10) -> list[NewsItem]:
        today = dt.date.today()
        date_from = (today - dt.timedelta(days=3)).isoformat()
        date_to = today.isoformat()

        items: list[NewsItem] = []
        for ticker in tickers:
            params = {
                "symbol": ticker,
                "from": date_from,
                "to": date_to,
                "token": self._key,
            }
            try:
                r = await self._http.get(self._BASE, params=params)
                r.raise_for_status()
            except Exception:
                return []

            for article in r.json()[:limit]:
                ts = article.get("datetime", 0)
                published_at = dt.datetime.fromtimestamp(
                    ts, tz=dt.timezone.utc
                ).isoformat()
                items.append(
                    NewsItem(
                        id=str(article.get("id", "")),
                        ticker=ticker,
                        headline=article.get("headline", ""),
                        summary=article.get("summary", ""),
                        published_at=published_at,
                        source=article.get("source", "finnhub"),
                        url=article.get("url", ""),
                    )
                )
        return items

    async def aclose(self) -> None:
        await self._http.aclose()
