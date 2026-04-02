# trader/news/eodhd.py
from __future__ import annotations

import httpx

from trader.models import NewsItem
from trader.news.base import NewsProvider


class EODHDProvider(NewsProvider):
    """
    EODHD company-news API -- free tier: 20 calls/day.
    https://eodhd.com/api/news
    Per-ticker API (one HTTP call per ticker, not batched).
    """

    _BASE = "https://eodhd.com/api/news"

    def __init__(self, api_key: str) -> None:
        self._key = api_key
        self._http = httpx.AsyncClient(timeout=15.0)

    async def get_news(self, tickers: list[str], limit: int = 10) -> list[NewsItem]:
        items: list[NewsItem] = []
        for ticker in tickers:
            params = {
                "s": f"{ticker}.US",
                "offset": 0,
                "limit": limit,
                "api_token": self._key,
                "fmt": "json",
            }
            try:
                r = await self._http.get(self._BASE, params=params)
                r.raise_for_status()
            except Exception:
                return []

            for article in r.json()[:limit]:
                # Strip ".US" (or any ".XX") suffix from symbols
                raw_symbols = article.get("symbols", [])
                symbols = [s.split(".")[0] for s in raw_symbols]

                # Use first matching symbol or the requested ticker
                matched_ticker = ticker
                for sym in symbols:
                    if sym.upper() == ticker.upper():
                        matched_ticker = sym.upper()
                        break

                content = article.get("content", "")
                summary = content[:500] if content else ""

                items.append(
                    NewsItem(
                        id=str(article.get("link", "")),
                        ticker=matched_ticker,
                        headline=article.get("title", ""),
                        summary=summary,
                        published_at=article.get("date", ""),
                        source="eodhd",
                        url=article.get("link", ""),
                    )
                )
        return items

    async def aclose(self) -> None:
        await self._http.aclose()
