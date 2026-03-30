from __future__ import annotations
import json
from pathlib import Path
import httpx
from trader.config import Config

_COOKIES_FILE = Path(__file__).resolve().parent.parent.parent / ".trader" / "ibkr-cookies.json"


def _load_cookies() -> httpx.Cookies:
    """Load session cookies saved by ibkr-reauth.py."""
    jar = httpx.Cookies()
    try:
        if _COOKIES_FILE.exists():
            for c in json.loads(_COOKIES_FILE.read_text()):
                jar.set(c["name"], c["value"], domain=c.get("domain", ""))
    except Exception:
        pass
    return jar


class IBKRRestClient:
    def __init__(self, config: Config):
        self._base = config.ibkr_rest_base_url
        # Client Portal Gateway always uses a self-signed cert — disable
        # verification for all hosts (localhost, Docker service names, etc.)
        cookies = _load_cookies()
        self._http = httpx.AsyncClient(verify=False, timeout=30.0, cookies=cookies)

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
