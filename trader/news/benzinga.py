from __future__ import annotations
import httpx
from trader.config import Config
from trader.models import NewsItem

class BenzingaClient:
    BASE = "https://api.benzinga.com/api/v2"

    def __init__(self, config: Config):
        self._token = config.benzinga_api_key
        self._http = httpx.AsyncClient(timeout=15.0)

    async def get_news(self, tickers: list[str], limit: int = 10) -> list[NewsItem]:
        params = {
            "token": self._token,
            "tickers": ",".join(tickers),
            "pageSize": limit,
            "displayOutput": "abstract",
        }
        r = await self._http.get(f"{self.BASE}/news", params=params)
        r.raise_for_status()
        items = []
        for n in r.json():
            stocks = n.get("stocks", [{}])
            ticker = stocks[0].get("name", tickers[0]) if stocks else tickers[0]
            items.append(NewsItem(
                id=str(n.get("id", "")),
                ticker=ticker,
                headline=n.get("title", ""),
                summary=n.get("teaser", ""),
                published_at=n.get("created", ""),
                source="benzinga",
                url=n.get("url", ""),
            ))
        return items

    async def aclose(self) -> None:
        await self._http.aclose()
