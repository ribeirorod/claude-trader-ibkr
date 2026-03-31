# trader/news/alphavantage.py
from __future__ import annotations

import hashlib

import httpx

from trader.models import NewsItem
from trader.news.base import NewsProvider


class AlphaVantageProvider(NewsProvider):
    """
    Alpha Vantage NEWS_SENTIMENT API — free tier: 25 calls/day.
    https://www.alphavantage.co/documentation/#news-sentiment
    """

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
        tickers_upper = {t.upper() for t in tickers}

        for article in r.json().get("feed", []):
            # Find matching ticker from ticker_sentiment array
            ticker: str | None = None
            for ts in article.get("ticker_sentiment", []):
                if ts.get("ticker", "").upper() in tickers_upper:
                    ticker = ts["ticker"].upper()
                    break

            # Parse time_published "YYYYMMDDTHHmmSS" -> ISO format
            published_at = _parse_av_time(article.get("time_published", ""))

            item_id = hashlib.md5(
                article.get("url", "").encode()
            ).hexdigest()[:12]

            items.append(
                NewsItem(
                    id=item_id,
                    ticker=ticker,
                    headline=article.get("title", ""),
                    summary=article.get("summary", ""),
                    published_at=published_at,
                    source=article.get("source", "alphavantage"),
                    url=article.get("url", ""),
                )
            )
        return items

    async def aclose(self) -> None:
        await self._http.aclose()


def _parse_av_time(raw: str) -> str:
    """Convert Alpha Vantage time format 'YYYYMMDDTHHmmSS' to ISO 8601."""
    if not raw or len(raw) < 15:
        return raw
    # "20260331T120000" -> "2026-03-31T12:00:00"
    return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}T{raw[9:11]}:{raw[11:13]}:{raw[13:15]}"
