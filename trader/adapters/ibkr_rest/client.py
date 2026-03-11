from __future__ import annotations
import httpx
from trader.config import Config

class IBKRRestClient:
    def __init__(self, config: Config):
        self._base = config.ibkr_rest_base_url
        # Client Portal Gateway uses a self-signed cert on localhost — disable
        # verification only when connecting to a loopback address.
        _local = config.ib_host in ("127.0.0.1", "localhost", "::1")
        self._http = httpx.AsyncClient(verify=not _local, timeout=30.0)

    async def get(self, path: str, **kwargs) -> dict:
        r = await self._http.get(f"{self._base}{path}", **kwargs)
        r.raise_for_status()
        return r.json()

    async def post(self, path: str, **kwargs) -> dict:
        r = await self._http.post(f"{self._base}{path}", **kwargs)
        r.raise_for_status()
        return r.json()

    async def delete(self, path: str, **kwargs) -> dict:
        r = await self._http.delete(f"{self._base}{path}", **kwargs)
        r.raise_for_status()
        return r.json()

    async def aclose(self) -> None:
        await self._http.aclose()
