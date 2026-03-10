# Agent-First Trader CLI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rewrite the existing trading tool as a clean, agent-first CLI with pluggable broker adapters, Benzinga news, and a risk-filtered strategy engine.

**Architecture:** Pluggable Adapter ABC with `ibkr-rest` (IBKR Client Portal Gateway, headless default) and `ibkr-tws` (ib_insync, optional) implementations. Pure-function strategy engine ported from existing `volatility/` module. All CLI output is JSON. Benzinga for news with keyword sentiment scoring.

**Tech Stack:** Python 3.10+, Click (CLI), Pydantic v2 (models), httpx (async HTTP), ib_insync 0.9.86 (optional), pandas (OHLCV), pytest + pytest-asyncio + respx (tests), pyproject.toml (packaging)

**Design doc:** `docs/plans/2026-03-10-agent-first-trader-cli-design.md`

---

## Phase 1: Project Scaffolding

### Task 1: pyproject.toml

**Difficulty:** S

**Files:**
- Create: `pyproject.toml`
- Delete: `requirements.txt`

**Step 1: Write the test**
```python
# tests/test_packaging.py
import importlib
def test_package_importable():
    import trader
    assert trader is not None
```

**Step 2: Run test to verify it fails**
```bash
pytest tests/test_packaging.py -v
# Expected: ModuleNotFoundError — trader not installed
```

**Step 3: Create pyproject.toml**
```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "trader"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "click>=8.1",
    "pydantic>=2.9",
    "httpx>=0.27",
    "pandas>=2.2",
    "python-dotenv>=1.0,<2",
    "yfinance>=0.2",
    "structlog>=23,<25",
]

[project.optional-dependencies]
tws = ["ib_insync>=0.9.86"]
dev = ["pytest>=8", "pytest-asyncio>=0.23", "respx>=0.21", "pytest-mock>=3.12"]

[project.scripts]
trader = "trader.cli.__main__:cli"

[tool.setuptools.packages.find]
where = ["."]
include = ["trader*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

**Step 4: Install and run test**
```bash
pip install -e ".[dev]"
pytest tests/test_packaging.py -v
# Expected: PASS
```

**Step 5: Commit**
```bash
git add pyproject.toml tests/test_packaging.py
git rm requirements.txt
git commit -m "feat: replace requirements.txt with pyproject.toml"
```

---

### Task 2: Package structure

**Difficulty:** S

**Files:**
- Create: `trader/__init__.py`
- Create: `trader/cli/__init__.py`
- Create: `trader/adapters/__init__.py`
- Create: `trader/adapters/ibkr_rest/__init__.py`
- Create: `trader/adapters/ibkr_tws/__init__.py`
- Create: `trader/strategies/__init__.py`
- Create: `trader/news/__init__.py`
- Create: `trader/models/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/integration/__init__.py`

**Step 1: Create all `__init__.py` files** (all empty)
```bash
mkdir -p trader/cli trader/adapters/ibkr_rest trader/adapters/ibkr_tws \
         trader/strategies trader/news trader/models \
         tests/unit tests/integration
touch trader/__init__.py trader/cli/__init__.py \
      trader/adapters/__init__.py trader/adapters/ibkr_rest/__init__.py \
      trader/adapters/ibkr_tws/__init__.py trader/strategies/__init__.py \
      trader/news/__init__.py trader/models/__init__.py \
      tests/__init__.py tests/unit/__init__.py tests/integration/__init__.py
```

**Step 2: Commit**
```bash
git add trader/ tests/
git commit -m "feat: scaffold package directory structure"
```

---

### Task 3: config.py

**Difficulty:** S

**Files:**
- Create: `trader/config.py`
- Create: `tests/unit/test_config.py`

**Step 1: Write failing test**
```python
# tests/unit/test_config.py
import os, pytest
from trader.config import Config

def test_config_defaults(monkeypatch):
    monkeypatch.delenv("IB_PORT", raising=False)
    monkeypatch.delenv("DEFAULT_BROKER", raising=False)
    monkeypatch.delenv("MAX_POSITION_PCT", raising=False)
    c = Config()
    assert c.ib_port == 5000
    assert c.default_broker == "ibkr-rest"
    assert c.max_position_pct == 0.05

def test_config_from_env(monkeypatch):
    monkeypatch.setenv("IB_PORT", "7497")
    monkeypatch.setenv("BENZINGA_API_KEY", "testkey")
    c = Config()
    assert c.ib_port == 7497
    assert c.benzinga_api_key == "testkey"
```

**Step 2: Run to verify failure**
```bash
pytest tests/unit/test_config.py -v
# Expected: ImportError
```

**Step 3: Implement**
```python
# trader/config.py
from __future__ import annotations
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    ib_host: str = field(default_factory=lambda: os.getenv("IB_HOST", "127.0.0.1"))
    ib_port: int = field(default_factory=lambda: int(os.getenv("IB_PORT", "5000")))
    ib_account: str = field(default_factory=lambda: os.getenv("IB_ACCOUNT", ""))
    ibkr_username: str = field(default_factory=lambda: os.getenv("IBKR_USERNAME", ""))
    ibkr_password: str = field(default_factory=lambda: os.getenv("IBKR_PASSWORD", ""))
    benzinga_api_key: str = field(default_factory=lambda: os.getenv("BENZINGA_API_KEY", ""))
    max_position_pct: float = field(default_factory=lambda: float(os.getenv("MAX_POSITION_PCT", "0.05")))
    default_strategy: str = field(default_factory=lambda: os.getenv("DEFAULT_STRATEGY", "rsi"))
    default_broker: str = field(default_factory=lambda: os.getenv("DEFAULT_BROKER", "ibkr-rest"))

    @property
    def ibkr_rest_base_url(self) -> str:
        return f"https://{self.ib_host}:{self.ib_port}/v1/api"
```

**Step 4: Run to verify pass**
```bash
pytest tests/unit/test_config.py -v
# Expected: PASS
```

**Step 5: Commit**
```bash
git add trader/config.py tests/unit/test_config.py
git commit -m "feat: add typed Config from environment"
```

---

## Phase 2: Pydantic Models

### Task 4: Core models

**Difficulty:** M

**Files:**
- Create: `trader/models/account.py`
- Create: `trader/models/order.py`
- Create: `trader/models/position.py`
- Create: `trader/models/quote.py`
- Create: `trader/models/news.py`
- Create: `trader/models/__init__.py` (re-exports)
- Create: `tests/unit/test_models.py`

**Step 1: Write failing tests**
```python
# tests/unit/test_models.py
from trader.models import OrderRequest, Order, Position, Quote, NewsItem, SentimentResult

def test_order_request_stock():
    req = OrderRequest(ticker="AAPL", qty=10, side="buy", order_type="market")
    assert req.contract_type == "stock"
    assert req.price is None

def test_order_request_option():
    req = OrderRequest(
        ticker="AAPL", qty=1, side="buy", order_type="limit",
        price=5.50, contract_type="option",
        expiry="2026-04-17", strike=200.0, right="call"
    )
    assert req.right == "call"

def test_order_request_bracket():
    req = OrderRequest(
        ticker="AAPL", qty=10, side="buy", order_type="bracket",
        price=195.0, take_profit=210.0, stop_loss=185.0
    )
    assert req.take_profit == 210.0

def test_sentiment_result_signal():
    r = SentimentResult(ticker="AAPL", score=0.5, signal="bullish",
                        article_count=5, lookback_hours=24, top_headlines=[])
    assert r.signal == "bullish"
    data = r.model_dump()
    assert "score" in data
```

**Step 2: Run to verify failure**
```bash
pytest tests/unit/test_models.py -v
# Expected: ImportError
```

**Step 3: Implement models**

```python
# trader/models/order.py
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel

class OrderRequest(BaseModel):
    ticker: str
    qty: float
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit", "stop", "trailing_stop", "bracket"]
    price: float | None = None
    trail_percent: float | None = None
    trail_amount: float | None = None
    take_profit: float | None = None
    stop_loss: float | None = None
    contract_type: Literal["stock", "etf", "option"] = "stock"
    expiry: str | None = None
    strike: float | None = None
    right: Literal["call", "put"] | None = None

class Order(BaseModel):
    order_id: str
    ticker: str
    qty: float
    side: Literal["buy", "sell"]
    order_type: str
    status: Literal["open", "filled", "cancelled", "pending"]
    price: float | None = None
    filled_price: float | None = None
    filled_qty: float | None = None
```

```python
# trader/models/account.py
from pydantic import BaseModel

class Balance(BaseModel):
    cash: float
    net_liquidation: float
    buying_power: float
    currency: str = "USD"

class Margin(BaseModel):
    initial_margin: float
    maintenance_margin: float
    available_margin: float

class Account(BaseModel):
    account_id: str
    balance: Balance
    margin: Margin
```

```python
# trader/models/position.py
from pydantic import BaseModel

class Position(BaseModel):
    ticker: str
    qty: float
    avg_cost: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float = 0.0
    contract_type: str = "stock"

class PnL(BaseModel):
    ticker: str | None = None
    unrealized: float
    realized: float
    total: float
```

```python
# trader/models/quote.py
from __future__ import annotations
from pydantic import BaseModel

class Quote(BaseModel):
    ticker: str
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    volume: int | None = None
    contract_type: str = "stock"

class OptionContract(BaseModel):
    strike: float
    right: str
    expiry: str
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    implied_vol: float | None = None
    open_interest: int | None = None

class OptionChain(BaseModel):
    ticker: str
    expiry: str
    contracts: list[OptionContract]
```

```python
# trader/models/news.py
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel

class NewsItem(BaseModel):
    id: str
    ticker: str | None = None
    headline: str
    summary: str = ""
    published_at: str
    source: str = ""
    url: str = ""

class SentimentResult(BaseModel):
    ticker: str
    score: float
    signal: Literal["bullish", "bearish", "neutral"]
    article_count: int
    lookback_hours: int
    top_headlines: list[str]
```

```python
# trader/models/__init__.py
from .account import Account, Balance, Margin
from .order import Order, OrderRequest
from .position import Position, PnL
from .quote import Quote, OptionChain, OptionContract
from .news import NewsItem, SentimentResult

__all__ = [
    "Account", "Balance", "Margin",
    "Order", "OrderRequest",
    "Position", "PnL",
    "Quote", "OptionChain", "OptionContract",
    "NewsItem", "SentimentResult",
]
```

**Step 4: Run to verify pass**
```bash
pytest tests/unit/test_models.py -v
# Expected: PASS (4 tests)
```

**Step 5: Commit**
```bash
git add trader/models/ tests/unit/test_models.py
git commit -m "feat: add Pydantic models for all domain objects"
```

---

## Phase 3: Adapter ABC

### Task 5: Adapter base class

**Difficulty:** S

**Files:**
- Create: `trader/adapters/base.py`
- Create: `tests/unit/test_adapter_base.py`

**Step 1: Write failing test**
```python
# tests/unit/test_adapter_base.py
from trader.adapters.base import Adapter
import inspect

def test_adapter_is_abstract():
    assert inspect.isabstract(Adapter)

def test_adapter_has_required_methods():
    required = [
        "connect", "disconnect", "get_account", "get_quotes",
        "get_option_chain", "place_order", "modify_order",
        "cancel_order", "list_orders", "list_positions",
        "close_position", "get_news",
    ]
    for method in required:
        assert hasattr(Adapter, method), f"Missing: {method}"
```

**Step 2: Run to verify failure**
```bash
pytest tests/unit/test_adapter_base.py -v
# Expected: ImportError
```

**Step 3: Implement**
```python
# trader/adapters/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from trader.models import (
    Account, Order, OrderRequest, Position, PnL,
    Quote, OptionChain, NewsItem
)

class Adapter(ABC):

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def get_account(self) -> Account: ...

    @abstractmethod
    async def get_quotes(self, tickers: list[str]) -> list[Quote]: ...

    @abstractmethod
    async def get_option_chain(self, ticker: str, expiry: str) -> OptionChain: ...

    @abstractmethod
    async def place_order(self, req: OrderRequest) -> Order: ...

    @abstractmethod
    async def modify_order(self, order_id: str, **kwargs) -> Order: ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool: ...

    @abstractmethod
    async def list_orders(self, status: str = "all") -> list[Order]: ...

    @abstractmethod
    async def list_positions(self) -> list[Position]: ...

    @abstractmethod
    async def close_position(self, ticker: str) -> Order: ...

    @abstractmethod
    async def get_news(self, tickers: list[str], limit: int = 10) -> list[NewsItem]: ...
```

**Step 4: Run to verify pass**
```bash
pytest tests/unit/test_adapter_base.py -v
# Expected: PASS
```

**Step 5: Commit**
```bash
git add trader/adapters/base.py tests/unit/test_adapter_base.py
git commit -m "feat: add Adapter ABC"
```

---

## Phase 4: IBKR REST Adapter

### Task 6: REST client (httpx wrapper)

**Difficulty:** M

**Files:**
- Create: `trader/adapters/ibkr_rest/client.py`
- Create: `tests/unit/test_ibkr_rest_client.py`

**Step 1: Write failing tests**
```python
# tests/unit/test_ibkr_rest_client.py
import pytest, respx, httpx
from trader.adapters.ibkr_rest.client import IBKRRestClient
from trader.config import Config

@pytest.fixture
def client():
    config = Config()
    config.ib_host = "localhost"
    config.ib_port = 5000
    return IBKRRestClient(config)

@pytest.mark.asyncio
async def test_get_request(client):
    with respx.mock:
        respx.get("https://localhost:5000/v1/api/test").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        result = await client.get("/test")
        assert result == {"ok": True}

@pytest.mark.asyncio
async def test_post_request(client):
    with respx.mock:
        respx.post("https://localhost:5000/v1/api/orders").mock(
            return_value=httpx.Response(200, json={"order_id": "123"})
        )
        result = await client.post("/orders", json={"ticker": "AAPL"})
        assert result["order_id"] == "123"
```

**Step 2: Run to verify failure**
```bash
pytest tests/unit/test_ibkr_rest_client.py -v
# Expected: ImportError
```

**Step 3: Implement**
```python
# trader/adapters/ibkr_rest/client.py
from __future__ import annotations
import httpx
from trader.config import Config

class IBKRRestClient:
    def __init__(self, config: Config):
        self._base = config.ibkr_rest_base_url
        # Client Portal uses self-signed cert — disable verification
        self._http = httpx.AsyncClient(verify=False, timeout=30.0)

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
```

**Step 4: Run to verify pass**
```bash
pytest tests/unit/test_ibkr_rest_client.py -v
# Expected: PASS
```

**Step 5: Commit**
```bash
git add trader/adapters/ibkr_rest/client.py tests/unit/test_ibkr_rest_client.py
git commit -m "feat: add IBKR Client Portal REST http client"
```

---

### Task 7: IBKR REST adapter implementation

**Difficulty:** L

**Files:**
- Create: `trader/adapters/ibkr_rest/adapter.py`
- Create: `tests/unit/test_ibkr_rest_adapter.py`

**Step 1: Write failing tests**
```python
# tests/unit/test_ibkr_rest_adapter.py
import pytest
from unittest.mock import AsyncMock, patch
from trader.adapters.ibkr_rest.adapter import IBKRRestAdapter
from trader.models import OrderRequest
from trader.config import Config

@pytest.fixture
def adapter():
    config = Config()
    config.ib_account = "DU123456"
    return IBKRRestAdapter(config)

@pytest.mark.asyncio
async def test_list_positions(adapter):
    mock_data = [{"conid": 265598, "ticker": "AAPL", "position": 10,
                  "avgCost": 190.0, "mktValue": 1950.0, "unrealizedPnl": 50.0}]
    with patch.object(adapter._client, "get", new=AsyncMock(return_value=mock_data)):
        positions = await adapter.list_positions()
    assert len(positions) == 1
    assert positions[0].ticker == "AAPL"
    assert positions[0].qty == 10

@pytest.mark.asyncio
async def test_place_market_order(adapter):
    mock_response = [{"order_id": "ord_001", "order_status": "PreSubmitted"}]
    with patch.object(adapter._client, "post", new=AsyncMock(return_value=mock_response)):
        req = OrderRequest(ticker="AAPL", qty=10, side="buy", order_type="market")
        order = await adapter.place_order(req)
    assert order.order_id == "ord_001"
    assert order.status == "open"
```

**Step 2: Run to verify failure**
```bash
pytest tests/unit/test_ibkr_rest_adapter.py -v
# Expected: ImportError
```

**Step 3: Implement**
```python
# trader/adapters/ibkr_rest/adapter.py
from __future__ import annotations
from trader.adapters.base import Adapter
from trader.adapters.ibkr_rest.client import IBKRRestClient
from trader.models import (
    Account, Balance, Margin, Order, OrderRequest,
    Position, PnL, Quote, OptionChain, OptionContract, NewsItem
)
from trader.config import Config

_ORDER_TYPE_MAP = {
    "market": "MKT", "limit": "LMT", "stop": "STP",
    "trailing_stop": "TRAIL", "bracket": "LMT",
}

_STATUS_MAP = {
    "PreSubmitted": "open", "Submitted": "open", "Filled": "filled",
    "Cancelled": "cancelled", "Inactive": "cancelled",
}

class IBKRRestAdapter(Adapter):
    def __init__(self, config: Config):
        self._config = config
        self._client = IBKRRestClient(config)
        self._account_id = config.ib_account

    async def connect(self) -> None:
        # Verify session is authenticated
        status = await self._client.get("/iserver/auth/status")
        if not status.get("authenticated"):
            raise RuntimeError("IBKR Client Portal Gateway not authenticated. Log in via browser first.")

    async def disconnect(self) -> None:
        await self._client.aclose()

    async def get_account(self) -> Account:
        data = await self._client.get(f"/portfolio/{self._account_id}/summary")
        return Account(
            account_id=self._account_id,
            balance=Balance(
                cash=float(data.get("totalcashvalue", {}).get("amount", 0)),
                net_liquidation=float(data.get("netliquidation", {}).get("amount", 0)),
                buying_power=float(data.get("buyingpower", {}).get("amount", 0)),
            ),
            margin=Margin(
                initial_margin=float(data.get("initmarginreq", {}).get("amount", 0)),
                maintenance_margin=float(data.get("maintmarginreq", {}).get("amount", 0)),
                available_margin=float(data.get("excessliquidity", {}).get("amount", 0)),
            ),
        )

    async def get_quotes(self, tickers: list[str]) -> list[Quote]:
        # First resolve conids for tickers
        quotes = []
        for ticker in tickers:
            try:
                search = await self._client.get(f"/iserver/secdef/search?symbol={ticker}")
                conid = search[0]["conid"] if search else None
                if not conid:
                    continue
                snap = await self._client.get(f"/iserver/marketdata/snapshot?conids={conid}&fields=31,84,86,7762")
                d = snap[0] if snap else {}
                quotes.append(Quote(
                    ticker=ticker,
                    last=float(d.get("31", 0)) or None,
                    bid=float(d.get("84", 0)) or None,
                    ask=float(d.get("86", 0)) or None,
                ))
            except Exception:
                quotes.append(Quote(ticker=ticker))
        return quotes

    async def get_option_chain(self, ticker: str, expiry: str) -> OptionChain:
        search = await self._client.get(f"/iserver/secdef/search?symbol={ticker}")
        conid = search[0]["conid"]
        month = expiry[:7].replace("-", "")  # "2026-04" → "202604"
        strikes = await self._client.get(
            f"/iserver/secdef/strike?conid={conid}&sectype=OPT&month={month}"
        )
        contracts = []
        for strike in strikes.get("call", []):
            contracts.append(OptionContract(strike=strike, right="call", expiry=expiry))
        for strike in strikes.get("put", []):
            contracts.append(OptionContract(strike=strike, right="put", expiry=expiry))
        return OptionChain(ticker=ticker, expiry=expiry, contracts=contracts)

    async def place_order(self, req: OrderRequest) -> Order:
        body = {
            "conid": await self._resolve_conid(req.ticker, req.contract_type,
                                               req.expiry, req.strike, req.right),
            "orderType": _ORDER_TYPE_MAP[req.order_type],
            "side": req.side.upper(),
            "quantity": req.qty,
            "tif": "DAY",
        }
        if req.price:
            body["price"] = req.price
        if req.trail_percent:
            body["trailingAmt"] = req.trail_percent
            body["trailingType"] = "%"
        if req.trail_amount:
            body["trailingAmt"] = req.trail_amount
            body["trailingType"] = "amt"
        if req.order_type == "bracket":
            body["isSingleGroup"] = True
            if req.take_profit:
                body["listingExchange"] = "SMART"
            body.update({"outsideRth": False})

        resp = await self._client.post(
            f"/iserver/account/{self._account_id}/orders",
            json={"orders": [body]}
        )
        r = resp[0] if isinstance(resp, list) else resp
        return Order(
            order_id=str(r.get("order_id", r.get("orderId", ""))),
            ticker=req.ticker, qty=req.qty, side=req.side,
            order_type=req.order_type, status="open", price=req.price,
        )

    async def modify_order(self, order_id: str, **kwargs) -> Order:
        resp = await self._client.post(
            f"/iserver/account/{self._account_id}/order/{order_id}",
            json=kwargs
        )
        return Order(
            order_id=order_id,
            ticker=kwargs.get("ticker", ""),
            qty=kwargs.get("quantity", 0),
            side=kwargs.get("side", "buy"),
            order_type=kwargs.get("orderType", "limit"),
            status="open",
            price=kwargs.get("price"),
        )

    async def cancel_order(self, order_id: str) -> bool:
        await self._client.delete(
            f"/iserver/account/{self._account_id}/order/{order_id}"
        )
        return True

    async def list_orders(self, status: str = "all") -> list[Order]:
        data = await self._client.get("/iserver/account/orders")
        orders_data = data.get("orders", [])
        result = []
        for o in orders_data:
            order_status = _STATUS_MAP.get(o.get("status", ""), "open")
            if status != "all" and order_status != status:
                continue
            result.append(Order(
                order_id=str(o.get("orderId", "")),
                ticker=o.get("ticker", ""),
                qty=float(o.get("remainingQuantity", 0)),
                side=o.get("side", "buy").lower(),
                order_type=o.get("orderType", "market").lower(),
                status=order_status,
                price=o.get("price"),
                filled_price=o.get("avgPrice"),
                filled_qty=o.get("filledQuantity"),
            ))
        return result

    async def list_positions(self) -> list[Position]:
        data = await self._client.get(f"/portfolio/{self._account_id}/positions/0")
        result = []
        for p in data:
            result.append(Position(
                ticker=p.get("ticker", p.get("contractDesc", "")),
                qty=float(p.get("position", 0)),
                avg_cost=float(p.get("avgCost", 0)),
                market_value=float(p.get("mktValue", 0)),
                unrealized_pnl=float(p.get("unrealizedPnl", 0)),
                realized_pnl=float(p.get("realizedPnl", 0)),
            ))
        return result

    async def close_position(self, ticker: str) -> Order:
        positions = await self.list_positions()
        pos = next((p for p in positions if p.ticker == ticker), None)
        if not pos:
            raise ValueError(f"No open position for {ticker}")
        side = "sell" if pos.qty > 0 else "buy"
        req = OrderRequest(ticker=ticker, qty=abs(pos.qty), side=side, order_type="market")
        return await self.place_order(req)

    async def get_news(self, tickers: list[str], limit: int = 10) -> list[NewsItem]:
        items = []
        for ticker in tickers:
            try:
                search = await self._client.get(f"/iserver/secdef/search?symbol={ticker}")
                conid = search[0]["conid"] if search else None
                if not conid:
                    continue
                data = await self._client.get(
                    f"/iserver/news/news?conid={conid}&limit={limit}"
                )
                for n in data.get("news", []):
                    items.append(NewsItem(
                        id=n.get("id", ""),
                        ticker=ticker,
                        headline=n.get("headline", ""),
                        published_at=n.get("date", ""),
                        source=n.get("provider", ""),
                    ))
            except Exception:
                pass
        return items

    async def _resolve_conid(
        self, ticker: str, contract_type: str = "stock",
        expiry: str | None = None, strike: float | None = None,
        right: str | None = None
    ) -> int:
        search = await self._client.get(f"/iserver/secdef/search?symbol={ticker}")
        return search[0]["conid"]
```

**Step 4: Run to verify pass**
```bash
pytest tests/unit/test_ibkr_rest_adapter.py -v
# Expected: PASS
```

**Step 5: Commit**
```bash
git add trader/adapters/ibkr_rest/ tests/unit/test_ibkr_rest_adapter.py
git commit -m "feat: add IBKR Client Portal REST adapter"
```

---

### Task 8: IBKR TWS adapter (optional)

**Difficulty:** M

**Files:**
- Create: `trader/adapters/ibkr_tws/adapter.py`
- Create: `tests/unit/test_ibkr_tws_adapter.py`

**Step 1: Write failing test**
```python
# tests/unit/test_ibkr_tws_adapter.py
def test_tws_adapter_importable_without_ib_insync():
    """The tws adapter must not crash on import even if ib_insync is not installed."""
    try:
        from trader.adapters.ibkr_tws.adapter import IBKRTWSAdapter
        assert IBKRTWSAdapter is not None
    except ImportError as e:
        if "ib_insync" in str(e):
            pytest.skip("ib_insync not installed — expected in CI")
        raise
```

**Step 2: Run to verify failure**
```bash
pytest tests/unit/test_ibkr_tws_adapter.py -v
# Expected: ImportError
```

**Step 3: Implement (lazy import pattern)**
```python
# trader/adapters/ibkr_tws/adapter.py
from __future__ import annotations
from trader.adapters.base import Adapter
from trader.models import (
    Account, Balance, Margin, Order, OrderRequest,
    Position, PnL, Quote, OptionChain, OptionContract, NewsItem
)
from trader.config import Config

class IBKRTWSAdapter(Adapter):
    """ib_insync adapter — requires pip install trader[tws] and TWS/Gateway running."""

    def __init__(self, config: Config):
        self._config = config
        self._ib = None  # lazy import

    def _get_ib(self):
        if self._ib is None:
            try:
                from ib_insync import IB
            except ImportError:
                raise ImportError(
                    "ib_insync not installed. Run: pip install 'trader[tws]'"
                )
            self._ib = IB()
        return self._ib

    async def connect(self) -> None:
        ib = self._get_ib()
        await ib.connectAsync(
            self._config.ib_host,
            self._config.ib_port,
            clientId=101,
        )

    async def disconnect(self) -> None:
        if self._ib:
            self._ib.disconnect()

    async def get_account(self) -> Account:
        ib = self._get_ib()
        vals = {v.tag: v.value for v in ib.accountValues()}
        return Account(
            account_id=self._config.ib_account,
            balance=Balance(
                cash=float(vals.get("TotalCashValue", 0)),
                net_liquidation=float(vals.get("NetLiquidation", 0)),
                buying_power=float(vals.get("BuyingPower", 0)),
            ),
            margin=Margin(
                initial_margin=float(vals.get("InitMarginReq", 0)),
                maintenance_margin=float(vals.get("MaintMarginReq", 0)),
                available_margin=float(vals.get("ExcessLiquidity", 0)),
            ),
        )

    async def get_quotes(self, tickers: list[str]) -> list[Quote]:
        from ib_insync import Stock, util
        ib = self._get_ib()
        contracts = [Stock(t, "SMART", "USD") for t in tickers]
        await ib.qualifyContractsAsync(*contracts)
        tickers_data = [ib.reqMktData(c, "", False, False) for c in contracts]
        await ib.sleep(1)
        return [
            Quote(ticker=t, bid=td.bid, ask=td.ask, last=td.last)
            for t, td in zip(tickers, tickers_data)
        ]

    async def get_option_chain(self, ticker: str, expiry: str) -> OptionChain:
        from ib_insync import Stock
        ib = self._get_ib()
        stock = Stock(ticker, "SMART", "USD")
        await ib.qualifyContractsAsync(stock)
        chains = await ib.reqSecDefOptParamsAsync(ticker, "", "STK", stock.conId)
        chain = next((c for c in chains if c.exchange == "SMART"), chains[0])
        contracts = []
        for strike in chain.strikes:
            for right in ["C", "P"]:
                contracts.append(OptionContract(
                    strike=strike,
                    right="call" if right == "C" else "put",
                    expiry=expiry,
                ))
        return OptionChain(ticker=ticker, expiry=expiry, contracts=contracts)

    async def place_order(self, req: OrderRequest) -> Order:
        from ib_insync import Stock, Option, LimitOrder, MarketOrder, StopOrder
        ib = self._get_ib()
        if req.contract_type == "option":
            contract = Option(req.ticker, req.expiry.replace("-", ""),
                              req.strike, req.right[0].upper(), "SMART")
        else:
            contract = Stock(req.ticker, "SMART", "USD")
        await ib.qualifyContractsAsync(contract)
        if req.order_type == "market":
            ibkr_order = MarketOrder(req.side.upper(), req.qty)
        elif req.order_type == "limit":
            ibkr_order = LimitOrder(req.side.upper(), req.qty, req.price)
        elif req.order_type == "stop":
            ibkr_order = StopOrder(req.side.upper(), req.qty, req.price)
        else:
            ibkr_order = MarketOrder(req.side.upper(), req.qty)
        trade = ib.placeOrder(contract, ibkr_order)
        return Order(
            order_id=str(trade.order.orderId),
            ticker=req.ticker, qty=req.qty, side=req.side,
            order_type=req.order_type, status="open", price=req.price,
        )

    async def modify_order(self, order_id: str, **kwargs) -> Order:
        raise NotImplementedError("Use cancel + replace for TWS order modification")

    async def cancel_order(self, order_id: str) -> bool:
        ib = self._get_ib()
        trades = ib.openTrades()
        trade = next((t for t in trades if str(t.order.orderId) == order_id), None)
        if trade:
            ib.cancelOrder(trade.order)
        return True

    async def list_orders(self, status: str = "all") -> list[Order]:
        ib = self._get_ib()
        trades = ib.trades()
        result = []
        for t in trades:
            s = t.orderStatus.status
            mapped = "filled" if s == "Filled" else "cancelled" if s in ("Cancelled", "Inactive") else "open"
            if status != "all" and mapped != status:
                continue
            result.append(Order(
                order_id=str(t.order.orderId),
                ticker=t.contract.symbol,
                qty=t.order.totalQuantity,
                side=t.order.action.lower(),
                order_type=t.order.orderType.lower(),
                status=mapped,
                price=t.order.lmtPrice or None,
                filled_price=t.orderStatus.avgFillPrice or None,
                filled_qty=t.orderStatus.filled or None,
            ))
        return result

    async def list_positions(self) -> list[Position]:
        ib = self._get_ib()
        return [
            Position(
                ticker=p.contract.symbol,
                qty=p.position,
                avg_cost=p.avgCost,
                market_value=p.position * p.avgCost,
                unrealized_pnl=p.unrealizedPNL or 0,
                realized_pnl=p.realizedPNL or 0,
            )
            for p in ib.portfolio()
        ]

    async def close_position(self, ticker: str) -> Order:
        positions = await self.list_positions()
        pos = next((p for p in positions if p.ticker == ticker), None)
        if not pos:
            raise ValueError(f"No open position for {ticker}")
        side = "sell" if pos.qty > 0 else "buy"
        req = OrderRequest(ticker=ticker, qty=abs(pos.qty), side=side, order_type="market")
        return await self.place_order(req)

    async def get_news(self, tickers: list[str], limit: int = 10) -> list[NewsItem]:
        from ib_insync import Stock
        ib = self._get_ib()
        items = []
        for ticker in tickers:
            contract = Stock(ticker, "SMART", "USD")
            await ib.qualifyContractsAsync(contract)
            headlines = await ib.reqNewsProvidersAsync()
            news = await ib.reqHistoricalNewsAsync(
                contract.conId, providers="BRFG+DJNL",
                startDateTime="", endDateTime="", totalResults=limit
            )
            for n in news:
                items.append(NewsItem(
                    id=n.articleId,
                    ticker=ticker,
                    headline=n.headline,
                    published_at=str(n.time),
                    source=n.providerCode,
                ))
        return items
```

**Step 4: Run to verify pass**
```bash
pytest tests/unit/test_ibkr_tws_adapter.py -v
# Expected: PASS
```

**Step 5: Commit**
```bash
git add trader/adapters/ibkr_tws/ tests/unit/test_ibkr_tws_adapter.py
git commit -m "feat: add IBKR TWS adapter (optional, requires ib_insync)"
```

---

## Phase 5: News & Sentiment

### Task 9: Benzinga client

**Difficulty:** M

**Files:**
- Create: `trader/news/benzinga.py`
- Create: `tests/unit/test_benzinga.py`

**Step 1: Write failing tests**
```python
# tests/unit/test_benzinga.py
import pytest, respx, httpx
from trader.news.benzinga import BenzingaClient
from trader.config import Config

@pytest.fixture
def client():
    config = Config()
    config.benzinga_api_key = "test_key"
    return BenzingaClient(config)

@pytest.mark.asyncio
async def test_get_news_returns_items(client):
    mock_response = [
        {"id": "1", "title": "Apple beats earnings", "teaser": "AAPL up 5%",
         "created": "2026-03-10T10:00:00Z", "author": "Benzinga", "url": "http://example.com"}
    ]
    with respx.mock:
        respx.get("https://api.benzinga.com/api/v2/news").mock(
            return_value=httpx.Response(200, json=mock_response)
        )
        items = await client.get_news(["AAPL"], limit=5)
    assert len(items) == 1
    assert items[0].headline == "Apple beats earnings"
    assert items[0].ticker == "AAPL"

@pytest.mark.asyncio
async def test_get_news_empty_response(client):
    with respx.mock:
        respx.get("https://api.benzinga.com/api/v2/news").mock(
            return_value=httpx.Response(200, json=[])
        )
        items = await client.get_news(["AAPL"])
    assert items == []
```

**Step 2: Run to verify failure**
```bash
pytest tests/unit/test_benzinga.py -v
# Expected: ImportError
```

**Step 3: Implement**
```python
# trader/news/benzinga.py
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
            # Benzinga may return items for any of the requested tickers
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
```

**Step 4: Run to verify pass**
```bash
pytest tests/unit/test_benzinga.py -v
# Expected: PASS
```

**Step 5: Commit**
```bash
git add trader/news/benzinga.py tests/unit/test_benzinga.py
git commit -m "feat: add Benzinga news client"
```

---

### Task 10: Sentiment scorer

**Difficulty:** M

**Files:**
- Create: `trader/news/sentiment.py`
- Create: `tests/unit/test_sentiment.py`

**Step 1: Write failing tests**
```python
# tests/unit/test_sentiment.py
from trader.news.sentiment import SentimentScorer
from trader.models import NewsItem, SentimentResult
import datetime

def make_item(headline: str, summary: str = "") -> NewsItem:
    return NewsItem(id="1", ticker="AAPL", headline=headline,
                    summary=summary, published_at="2026-03-10T10:00:00Z")

def test_bullish_signal():
    scorer = SentimentScorer()
    items = [make_item("Apple surges after record earnings beat analyst estimates")]
    result = scorer.score("AAPL", items, lookback_hours=24)
    assert result.signal == "bullish"
    assert result.score > 0

def test_bearish_signal():
    scorer = SentimentScorer()
    items = [make_item("Apple misses earnings, stock declines on weak guidance cut")]
    result = scorer.score("AAPL", items, lookback_hours=24)
    assert result.signal == "bearish"
    assert result.score < 0

def test_neutral_signal():
    scorer = SentimentScorer()
    items = [make_item("Apple announces quarterly results in line with expectations")]
    result = scorer.score("AAPL", items, lookback_hours=24)
    assert result.signal == "neutral"

def test_empty_returns_neutral():
    scorer = SentimentScorer()
    result = scorer.score("AAPL", [], lookback_hours=24)
    assert result.signal == "neutral"
    assert result.score == 0.0
    assert result.article_count == 0

def test_top_headlines_capped_at_3():
    scorer = SentimentScorer()
    items = [make_item(f"Apple beats estimate {i}") for i in range(10)]
    result = scorer.score("AAPL", items, lookback_hours=24)
    assert len(result.top_headlines) <= 3
```

**Step 2: Run to verify failure**
```bash
pytest tests/unit/test_sentiment.py -v
# Expected: ImportError
```

**Step 3: Implement**
```python
# trader/news/sentiment.py
from __future__ import annotations
import re
from trader.models import NewsItem, SentimentResult

_BULLISH = {
    "beat", "beats", "surge", "surges", "surging", "rally", "rallies",
    "upgrade", "upgraded", "strong", "growth", "record", "positive",
    "outperform", "raise", "raised", "exceed", "exceeds", "profit",
    "buy", "bullish", "gain", "gains", "high", "higher", "rise", "rises",
}
_BEARISH = {
    "miss", "misses", "missed", "decline", "declines", "declining",
    "downgrade", "downgraded", "weak", "loss", "losses", "cut", "cuts",
    "risk", "negative", "recall", "lawsuit", "sell", "bearish", "low",
    "lower", "fall", "falls", "drop", "drops", "concern", "warning",
}

def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z]+", text.lower())

def _score_item(item: NewsItem) -> float:
    tokens = _tokenize(item.headline + " " + item.summary)
    if not tokens:
        return 0.0
    bull = sum(1 for t in tokens if t in _BULLISH)
    bear = sum(1 for t in tokens if t in _BEARISH)
    return (bull - bear) / len(tokens)

class SentimentScorer:
    def score(
        self,
        ticker: str,
        items: list[NewsItem],
        lookback_hours: int = 24,
    ) -> SentimentResult:
        if not items:
            return SentimentResult(
                ticker=ticker, score=0.0, signal="neutral",
                article_count=0, lookback_hours=lookback_hours, top_headlines=[]
            )

        scored = sorted(
            [(item, _score_item(item)) for item in items],
            key=lambda x: abs(x[1]),
            reverse=True,
        )
        avg_score = sum(s for _, s in scored) / len(scored)
        clamped = max(-1.0, min(1.0, avg_score * 10))  # scale and clamp

        if clamped > 0.1:
            signal = "bullish"
        elif clamped < -0.1:
            signal = "bearish"
        else:
            signal = "neutral"

        return SentimentResult(
            ticker=ticker,
            score=round(clamped, 3),
            signal=signal,
            article_count=len(items),
            lookback_hours=lookback_hours,
            top_headlines=[item.headline for item, _ in scored[:3]],
        )
```

**Step 4: Run to verify pass**
```bash
pytest tests/unit/test_sentiment.py -v
# Expected: PASS (5 tests)
```

**Step 5: Commit**
```bash
git add trader/news/sentiment.py tests/unit/test_sentiment.py
git commit -m "feat: add keyword-weighted sentiment scorer"
```

---

## Phase 6: Strategy Engine

### Task 11: BaseStrategy + RSI

**Difficulty:** M

**Files:**
- Create: `trader/strategies/base.py`
- Create: `trader/strategies/rsi.py`
- Create: `tests/unit/test_strategies.py`

**Step 1: Write failing tests**
```python
# tests/unit/test_strategies.py
import pandas as pd
import numpy as np
import pytest
from trader.strategies.rsi import RSIStrategy

def make_ohlcv(n=100) -> pd.DataFrame:
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    return pd.DataFrame({
        "open": close * 0.99, "high": close * 1.01,
        "low": close * 0.98, "close": close, "volume": 1000000,
    })

def test_rsi_signals_shape():
    strat = RSIStrategy({"period": 14, "oversold": 30, "overbought": 70})
    df = make_ohlcv()
    signals = strat.signals(df)
    assert len(signals) == len(df)
    assert set(signals.unique()).issubset({-1, 0, 1})

def test_rsi_default_params():
    strat = RSIStrategy()
    params = strat.default_params()
    assert "period" in params
    assert "oversold" in params
    assert "overbought" in params

def test_rsi_signals_not_all_zero():
    strat = RSIStrategy()
    df = make_ohlcv(200)
    signals = strat.signals(df)
    assert signals.abs().sum() > 0  # at least some non-zero signals
```

**Step 2: Run to verify failure**
```bash
pytest tests/unit/test_strategies.py -v
# Expected: ImportError
```

**Step 3: Implement**
```python
# trader/strategies/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
import pandas as pd

class BaseStrategy(ABC):
    def __init__(self, params: dict | None = None):
        self._params = {**self.default_params(), **(params or {})}

    @abstractmethod
    def signals(self, ohlcv: pd.DataFrame) -> pd.Series: ...

    @abstractmethod
    def default_params(self) -> dict: ...

    @property
    def params(self) -> dict:
        return self._params
```

```python
# trader/strategies/rsi.py
from __future__ import annotations
import pandas as pd
from trader.strategies.base import BaseStrategy

class RSIStrategy(BaseStrategy):
    def default_params(self) -> dict:
        return {"period": 14, "oversold": 30, "overbought": 70}

    def signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        close = ohlcv["close"]
        period = self._params["period"]
        oversold = self._params["oversold"]
        overbought = self._params["overbought"]

        delta = close.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / loss.replace(0, float("nan"))
        rsi = 100 - (100 / (1 + rs))

        signals = pd.Series(0, index=ohlcv.index)
        signals[rsi < oversold] = 1    # oversold → buy
        signals[rsi > overbought] = -1  # overbought → sell
        return signals.fillna(0).astype(int)
```

**Step 4: Run to verify pass**
```bash
pytest tests/unit/test_strategies.py -v
# Expected: PASS
```

**Step 5: Commit**
```bash
git add trader/strategies/base.py trader/strategies/rsi.py tests/unit/test_strategies.py
git commit -m "feat: add BaseStrategy ABC and RSI strategy"
```

---

### Task 12: MACD + MACross + BNF strategies

**Difficulty:** M

**Files:**
- Create: `trader/strategies/macd.py`
- Create: `trader/strategies/ma_cross.py`
- Create: `trader/strategies/bnf.py`
- Modify: `tests/unit/test_strategies.py` (add tests)

**Step 1: Add tests**
```python
# append to tests/unit/test_strategies.py
from trader.strategies.macd import MACDStrategy
from trader.strategies.ma_cross import MACrossStrategy

def test_macd_signals_shape():
    strat = MACDStrategy()
    df = make_ohlcv(200)
    signals = strat.signals(df)
    assert len(signals) == len(df)
    assert set(signals.unique()).issubset({-1, 0, 1})

def test_ma_cross_signals_shape():
    strat = MACrossStrategy()
    df = make_ohlcv(200)
    signals = strat.signals(df)
    assert len(signals) == len(df)
    assert set(signals.unique()).issubset({-1, 0, 1})
```

**Step 2: Run to verify failure**
```bash
pytest tests/unit/test_strategies.py -v -k "macd or ma_cross"
# Expected: ImportError
```

**Step 3: Implement**
```python
# trader/strategies/macd.py
import pandas as pd
from trader.strategies.base import BaseStrategy

class MACDStrategy(BaseStrategy):
    def default_params(self) -> dict:
        return {"fast": 12, "slow": 26, "signal": 9}

    def signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        close = ohlcv["close"]
        fast = self._params["fast"]
        slow = self._params["slow"]
        sig = self._params["signal"]

        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=sig, adjust=False).mean()

        prev_macd = macd_line.shift(1)
        prev_signal = signal_line.shift(1)

        signals = pd.Series(0, index=ohlcv.index)
        signals[(macd_line > signal_line) & (prev_macd <= prev_signal)] = 1
        signals[(macd_line < signal_line) & (prev_macd >= prev_signal)] = -1
        return signals.fillna(0).astype(int)
```

```python
# trader/strategies/ma_cross.py
import pandas as pd
from trader.strategies.base import BaseStrategy

class MACrossStrategy(BaseStrategy):
    def default_params(self) -> dict:
        return {"fast_window": 20, "slow_window": 50}

    def signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        close = ohlcv["close"]
        fast = close.rolling(self._params["fast_window"]).mean()
        slow = close.rolling(self._params["slow_window"]).mean()

        prev_fast = fast.shift(1)
        prev_slow = slow.shift(1)

        signals = pd.Series(0, index=ohlcv.index)
        signals[(fast > slow) & (prev_fast <= prev_slow)] = 1
        signals[(fast < slow) & (prev_fast >= prev_slow)] = -1
        return signals.fillna(0).astype(int)
```

```python
# trader/strategies/bnf.py
"""BNF (price-action breakout) strategy."""
import pandas as pd
from trader.strategies.base import BaseStrategy

class BNFStrategy(BaseStrategy):
    def default_params(self) -> dict:
        return {"lookback": 20, "breakout_pct": 0.02}

    def signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        close = ohlcv["close"]
        high = ohlcv["high"]
        low = ohlcv["low"]
        lookback = self._params["lookback"]
        pct = self._params["breakout_pct"]

        rolling_high = high.rolling(lookback).max().shift(1)
        rolling_low = low.rolling(lookback).min().shift(1)

        signals = pd.Series(0, index=ohlcv.index)
        signals[close > rolling_high * (1 + pct)] = 1
        signals[close < rolling_low * (1 - pct)] = -1
        return signals.fillna(0).astype(int)
```

**Step 4: Run to verify pass**
```bash
pytest tests/unit/test_strategies.py -v
# Expected: PASS (all strategy tests)
```

**Step 5: Commit**
```bash
git add trader/strategies/ tests/unit/test_strategies.py
git commit -m "feat: add MACD, MACross, BNF strategies"
```

---

### Task 13: Optimizer + RiskFilter + Factory

**Difficulty:** M

**Files:**
- Create: `trader/strategies/optimizer.py`
- Create: `trader/strategies/risk_filter.py`
- Create: `trader/strategies/factory.py`
- Create: `tests/unit/test_optimizer.py`
- Create: `tests/unit/test_risk_filter.py`

**Step 1: Write failing tests**
```python
# tests/unit/test_optimizer.py
import numpy as np
import pandas as pd
from trader.strategies.optimizer import Optimizer
from trader.strategies.rsi import RSIStrategy

def make_ohlcv(n=200):
    np.random.seed(0)
    c = 100 + np.cumsum(np.random.randn(n) * 0.5)
    return pd.DataFrame({"open": c, "high": c*1.01, "low": c*0.99, "close": c, "volume": 1000000})

def test_optimizer_returns_best_params():
    opt = Optimizer()
    df = make_ohlcv()
    best = opt.grid_search(RSIStrategy, df, {"period": [7, 14], "oversold": [25, 30], "overbought": [70, 75]})
    assert "period" in best
    assert best["period"] in [7, 14]
```

```python
# tests/unit/test_risk_filter.py
from trader.strategies.risk_filter import RiskFilter
from trader.models import Quote, SentimentResult

def make_quote(last=100.0):
    return Quote(ticker="AAPL", last=last, bid=99.9, ask=100.1)

def make_sentiment(score=0.0):
    sig = "bullish" if score > 0.1 else "bearish" if score < -0.1 else "neutral"
    return SentimentResult(ticker="AAPL", score=score, signal=sig,
                           article_count=5, lookback_hours=24, top_headlines=[])

def test_buy_suppressed_on_bearish_news():
    rf = RiskFilter()
    result = rf.filter(signal=1, quote=make_quote(), position=None,
                       sentiment=make_sentiment(-0.5))
    assert result["signal"] == 0
    assert result["filtered"] is True
    assert "sentiment" in result["filter_reason"]

def test_buy_passes_on_neutral_news():
    rf = RiskFilter()
    result = rf.filter(signal=1, quote=make_quote(), position=None,
                       sentiment=make_sentiment(0.0))
    assert result["signal"] == 1
    assert result["filtered"] is False

def test_sell_never_suppressed():
    rf = RiskFilter()
    result = rf.filter(signal=-1, quote=make_quote(), position=None,
                       sentiment=make_sentiment(-0.9))
    assert result["signal"] == -1
    assert result["filtered"] is False
```

**Step 2: Run to verify failure**
```bash
pytest tests/unit/test_optimizer.py tests/unit/test_risk_filter.py -v
# Expected: ImportError
```

**Step 3: Implement**
```python
# trader/strategies/optimizer.py
from __future__ import annotations
import itertools
import pandas as pd
import numpy as np
from typing import Literal

class Optimizer:
    def grid_search(
        self,
        strategy_cls,
        ohlcv: pd.DataFrame,
        param_grid: dict,
        metric: Literal["sharpe", "returns", "win_rate"] = "sharpe",
    ) -> dict:
        keys = list(param_grid.keys())
        best_score = float("-inf")
        best_params = {}
        for combo in itertools.product(*param_grid.values()):
            params = dict(zip(keys, combo))
            try:
                strat = strategy_cls(params)
                signals = strat.signals(ohlcv)
                score = self._score(ohlcv["close"], signals, metric)
                if score > best_score:
                    best_score = score
                    best_params = params
            except Exception:
                continue
        return best_params

    def _score(self, close: pd.Series, signals: pd.Series, metric: str) -> float:
        returns = close.pct_change().shift(-1)
        strategy_returns = returns * signals
        if metric == "returns":
            return float(strategy_returns.sum())
        elif metric == "win_rate":
            trades = strategy_returns[signals != 0]
            return float((trades > 0).mean()) if len(trades) > 0 else 0.0
        else:  # sharpe
            if strategy_returns.std() == 0:
                return 0.0
            return float(strategy_returns.mean() / strategy_returns.std() * np.sqrt(252))
```

```python
# trader/strategies/risk_filter.py
from __future__ import annotations
from trader.models import Quote, Position, SentimentResult

class RiskFilter:
    def filter(
        self,
        signal: int,
        quote: Quote,
        position: Position | None,
        sentiment: SentimentResult | None,
        max_position_pct: float = 0.05,
        min_sentiment: float = -0.2,
        account_value: float | None = None,
    ) -> dict:
        # Sells are never suppressed
        if signal != 1:
            return {"signal": signal, "filtered": False, "filter_reason": None}

        # Suppress buy on bearish news
        if sentiment and sentiment.score < min_sentiment:
            return {"signal": 0, "filtered": True, "filter_reason": "sentiment_bearish"}

        # Suppress buy if position too large
        if position and account_value and quote.last:
            position_value = abs(position.qty) * quote.last
            if position_value / account_value >= max_position_pct:
                return {"signal": 0, "filtered": True, "filter_reason": "position_limit"}

        return {"signal": signal, "filtered": False, "filter_reason": None}
```

```python
# trader/strategies/factory.py
from trader.strategies.rsi import RSIStrategy
from trader.strategies.macd import MACDStrategy
from trader.strategies.ma_cross import MACrossStrategy
from trader.strategies.bnf import BNFStrategy
from trader.strategies.base import BaseStrategy

_REGISTRY = {
    "rsi": RSIStrategy,
    "macd": MACDStrategy,
    "ma_cross": MACrossStrategy,
    "bnf": BNFStrategy,
}

def get_strategy(name: str, params: dict | None = None) -> BaseStrategy:
    cls = _REGISTRY.get(name.lower())
    if not cls:
        raise ValueError(f"Unknown strategy '{name}'. Available: {list(_REGISTRY)}")
    return cls(params)

def list_strategies() -> list[str]:
    return list(_REGISTRY)
```

**Step 4: Run to verify pass**
```bash
pytest tests/unit/test_optimizer.py tests/unit/test_risk_filter.py -v
# Expected: PASS
```

**Step 5: Commit**
```bash
git add trader/strategies/ tests/unit/test_optimizer.py tests/unit/test_risk_filter.py
git commit -m "feat: add optimizer, risk filter, and strategy factory"
```

---

## Phase 7: CLI

### Task 14: Root CLI + adapter factory

**Difficulty:** M

**Files:**
- Create: `trader/cli/__main__.py`
- Create: `trader/adapters/factory.py`
- Create: `tests/unit/test_cli_root.py`

**Step 1: Write failing tests**
```python
# tests/unit/test_cli_root.py
from click.testing import CliRunner
from trader.cli.__main__ import cli

def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "broker" in result.output.lower()

def test_cli_unknown_command():
    runner = CliRunner()
    result = runner.invoke(cli, ["nonexistent"])
    assert result.exit_code != 0
```

**Step 2: Run to verify failure**
```bash
pytest tests/unit/test_cli_root.py -v
# Expected: ImportError
```

**Step 3: Implement**
```python
# trader/adapters/factory.py
from trader.adapters.base import Adapter
from trader.config import Config

def get_adapter(broker: str, config: Config) -> Adapter:
    if broker == "ibkr-rest":
        from trader.adapters.ibkr_rest.adapter import IBKRRestAdapter
        return IBKRRestAdapter(config)
    elif broker == "ibkr-tws":
        from trader.adapters.ibkr_tws.adapter import IBKRTWSAdapter
        return IBKRTWSAdapter(config)
    else:
        raise ValueError(f"Unknown broker '{broker}'. Choose: ibkr-rest, ibkr-tws")
```

```python
# trader/cli/__main__.py
from __future__ import annotations
import asyncio, json, sys
import click
from trader.config import Config
from trader.adapters.factory import get_adapter

config = Config()

def output_json(data) -> None:
    """Serialize Pydantic models or dicts to stdout as JSON."""
    if hasattr(data, "model_dump"):
        click.echo(json.dumps(data.model_dump(), indent=2))
    elif isinstance(data, list):
        click.echo(json.dumps(
            [d.model_dump() if hasattr(d, "model_dump") else d for d in data],
            indent=2
        ))
    else:
        click.echo(json.dumps(data, indent=2))

def run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)

@click.group()
@click.option("--broker", default=config.default_broker,
              type=click.Choice(["ibkr-rest", "ibkr-tws"]),
              help="Broker adapter to use. ibkr-rest (default): IBKR Client Portal Gateway. ibkr-tws: ib_insync (requires TWS).")
@click.option("--output", default="json", type=click.Choice(["json", "table"]),
              help="Output format. Agents should use json (default).")
@click.pass_context
def cli(ctx, broker, output):
    """
    Trader CLI — agent-first trading tool for stocks, ETFs, and options.

    All commands output JSON by default. Run any subcommand with --help
    to see available options and parameters.

    Broker selection:
      --broker ibkr-rest   IBKR Client Portal Gateway (headless, default)
      --broker ibkr-tws    ib_insync + local TWS/Gateway (optional install)

    Environment: configure via .env file. See .env.example for all variables.
    """
    ctx.ensure_object(dict)
    ctx.obj["broker"] = broker
    ctx.obj["output"] = output
    ctx.obj["config"] = config

from trader.cli import account, quotes, orders, positions, news, strategies

cli.add_command(account.account)
cli.add_command(quotes.quotes)
cli.add_command(orders.orders)
cli.add_command(positions.positions)
cli.add_command(news.news)
cli.add_command(strategies.strategies)

if __name__ == "__main__":
    cli()
```

**Step 4: Create stub command modules** (so imports don't fail — fill in Task 15+):
```python
# trader/cli/account.py — stub
import click
@click.group()
def account(): """Account information commands."""

# trader/cli/quotes.py — stub
import click
@click.group()
def quotes(): """Market data and options chain commands."""

# trader/cli/orders.py — stub
import click
@click.group()
def orders(): """Order management commands."""

# trader/cli/positions.py — stub
import click
@click.group()
def positions(): """Position management commands."""

# trader/cli/news.py — stub
import click
@click.group()
def news(): """News and sentiment commands."""

# trader/cli/strategies.py — stub
import click
@click.group()
def strategies(): """Strategy signals, backtesting, and optimization."""
```

**Step 5: Run to verify pass**
```bash
pytest tests/unit/test_cli_root.py -v
# Expected: PASS
# Also verify manually:
trader --help
```

**Step 6: Commit**
```bash
git add trader/cli/ trader/adapters/factory.py tests/unit/test_cli_root.py
git commit -m "feat: add root CLI with broker selection and adapter factory"
```

---

### Task 15: Account + Quotes CLI commands

**Difficulty:** M

**Files:**
- Modify: `trader/cli/account.py`
- Modify: `trader/cli/quotes.py`
- Create: `tests/unit/test_cli_account.py`
- Create: `tests/unit/test_cli_quotes.py`

**Step 1: Write failing tests**
```python
# tests/unit/test_cli_account.py
import json
from unittest.mock import AsyncMock, patch, MagicMock
from click.testing import CliRunner
from trader.cli.__main__ import cli
from trader.models import Account, Balance, Margin

def mock_account():
    return Account(
        account_id="DU123",
        balance=Balance(cash=10000, net_liquidation=12000, buying_power=20000),
        margin=Margin(initial_margin=500, maintenance_margin=400, available_margin=9500),
    )

def test_account_summary():
    runner = CliRunner()
    with patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.connect", new=AsyncMock()), \
         patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.get_account",
               new=AsyncMock(return_value=mock_account())), \
         patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.disconnect", new=AsyncMock()):
        result = runner.invoke(cli, ["account", "summary"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["account_id"] == "DU123"
    assert "balance" in data
```

**Step 2: Run to verify failure**
```bash
pytest tests/unit/test_cli_account.py -v
# Expected: FAIL (stub has no subcommands)
```

**Step 3: Implement**
```python
# trader/cli/account.py
from __future__ import annotations
import asyncio, click
from trader.adapters.factory import get_adapter
from trader.cli.__main__ import output_json

@click.group()
def account():
    """Account information. Returns balance, margin, and account summary."""

@account.command()
@click.pass_context
def summary(ctx):
    """Full account summary including balance and margin."""
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    async def run():
        await adapter.connect()
        try:
            data = await adapter.get_account()
        finally:
            await adapter.disconnect()
        return data
    output_json(asyncio.get_event_loop().run_until_complete(run()))

@account.command()
@click.pass_context
def balance(ctx):
    """Cash balance, net liquidation, and buying power."""
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    async def run():
        await adapter.connect()
        try:
            acct = await adapter.get_account()
        finally:
            await adapter.disconnect()
        return acct.balance
    output_json(asyncio.get_event_loop().run_until_complete(run()))

@account.command()
@click.pass_context
def margin(ctx):
    """Initial margin, maintenance margin, and available margin."""
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    async def run():
        await adapter.connect()
        try:
            acct = await adapter.get_account()
        finally:
            await adapter.disconnect()
        return acct.margin
    output_json(asyncio.get_event_loop().run_until_complete(run()))
```

```python
# trader/cli/quotes.py
from __future__ import annotations
import asyncio, click
from trader.adapters.factory import get_adapter
from trader.cli.__main__ import output_json

@click.group()
def quotes():
    """Market data commands for stocks, ETFs, and options."""

@quotes.command("get")
@click.argument("tickers", nargs=-1, required=True)
@click.pass_context
def get_quotes(ctx, tickers):
    """
    Get live quotes for one or more tickers.

    TICKERS: Space-separated list e.g. AAPL MSFT TSLA
    """
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    async def run():
        await adapter.connect()
        try:
            return await adapter.get_quotes(list(tickers))
        finally:
            await adapter.disconnect()
    output_json(asyncio.get_event_loop().run_until_complete(run()))

@quotes.command("chain")
@click.argument("ticker")
@click.option("--expiry", required=True, help="Expiry date in YYYY-MM-DD format e.g. 2026-04-17")
@click.option("--strike", type=float, default=None, help="Filter by specific strike price")
@click.option("--right", type=click.Choice(["call", "put"]), default=None, help="Filter calls or puts")
@click.pass_context
def option_chain(ctx, ticker, expiry, strike, right):
    """
    Get options chain for a ticker.

    Returns all strikes for the given expiry. Use --strike and --right to filter.
    """
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    async def run():
        await adapter.connect()
        try:
            chain = await adapter.get_option_chain(ticker, expiry)
        finally:
            await adapter.disconnect()
        if strike:
            chain.contracts = [c for c in chain.contracts if c.strike == strike]
        if right:
            chain.contracts = [c for c in chain.contracts if c.right == right]
        return chain
    output_json(asyncio.get_event_loop().run_until_complete(run()))
```

**Step 4: Run to verify pass**
```bash
pytest tests/unit/test_cli_account.py -v
trader account --help
trader quotes --help
```

**Step 5: Commit**
```bash
git add trader/cli/account.py trader/cli/quotes.py tests/unit/test_cli_account.py tests/unit/test_cli_quotes.py
git commit -m "feat: add account and quotes CLI commands"
```

---

### Task 16: Orders CLI commands

**Difficulty:** L

**Files:**
- Modify: `trader/cli/orders.py`
- Create: `tests/unit/test_cli_orders.py`

**Step 1: Write failing tests**
```python
# tests/unit/test_cli_orders.py
import json
from unittest.mock import AsyncMock, patch
from click.testing import CliRunner
from trader.cli.__main__ import cli
from trader.models import Order

def mock_order(**kwargs):
    return Order(order_id="ord_1", ticker="AAPL", qty=10, side="buy",
                 order_type="market", status="open", **kwargs)

def test_buy_market_order():
    runner = CliRunner()
    with patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.connect", new=AsyncMock()), \
         patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.place_order",
               new=AsyncMock(return_value=mock_order())), \
         patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.disconnect", new=AsyncMock()):
        result = runner.invoke(cli, ["orders", "buy", "AAPL", "10"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["order_id"] == "ord_1"

def test_orders_list():
    runner = CliRunner()
    with patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.connect", new=AsyncMock()), \
         patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.list_orders",
               new=AsyncMock(return_value=[mock_order()])), \
         patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.disconnect", new=AsyncMock()):
        result = runner.invoke(cli, ["orders", "list"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
```

**Step 2: Run to verify failure**
```bash
pytest tests/unit/test_cli_orders.py -v
# Expected: FAIL
```

**Step 3: Implement**
```python
# trader/cli/orders.py
from __future__ import annotations
import asyncio, json, click
from trader.adapters.factory import get_adapter
from trader.models import OrderRequest
from trader.cli.__main__ import output_json

@click.group()
def orders():
    """Order management: buy, sell, cancel, modify, stop, trailing-stop, take-profit, bracket."""

def _run_order(ctx, req: OrderRequest):
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    async def run():
        await adapter.connect()
        try:
            return await adapter.place_order(req)
        finally:
            await adapter.disconnect()
    output_json(asyncio.get_event_loop().run_until_complete(run()))

@orders.command()
@click.argument("ticker")
@click.argument("qty", type=float)
@click.option("--type", "order_type", default="market",
              type=click.Choice(["market", "limit", "stop", "bracket"]),
              help="Order type. bracket requires --take-profit and --stop-loss.")
@click.option("--price", type=float, default=None, help="Limit or stop price.")
@click.option("--take-profit", type=float, default=None, help="Take profit price (bracket orders).")
@click.option("--stop-loss", type=float, default=None, help="Stop loss price (bracket orders).")
@click.option("--contract-type", default="stock",
              type=click.Choice(["stock", "etf", "option"]))
@click.option("--expiry", default=None, help="Option expiry YYYY-MM-DD.")
@click.option("--strike", type=float, default=None, help="Option strike price.")
@click.option("--right", type=click.Choice(["call", "put"]), default=None)
@click.pass_context
def buy(ctx, ticker, qty, order_type, price, take_profit, stop_loss,
        contract_type, expiry, strike, right):
    """Buy TICKER QTY shares/contracts. Use --type bracket for bracket orders with auto stop/TP."""
    _run_order(ctx, OrderRequest(
        ticker=ticker, qty=qty, side="buy", order_type=order_type,
        price=price, take_profit=take_profit, stop_loss=stop_loss,
        contract_type=contract_type, expiry=expiry, strike=strike, right=right,
    ))

@orders.command()
@click.argument("ticker")
@click.argument("qty", type=float)
@click.option("--type", "order_type", default="market",
              type=click.Choice(["market", "limit", "stop"]))
@click.option("--price", type=float, default=None)
@click.option("--contract-type", default="stock",
              type=click.Choice(["stock", "etf", "option"]))
@click.option("--expiry", default=None)
@click.option("--strike", type=float, default=None)
@click.option("--right", type=click.Choice(["call", "put"]), default=None)
@click.pass_context
def sell(ctx, ticker, qty, order_type, price, contract_type, expiry, strike, right):
    """Sell TICKER QTY shares/contracts."""
    _run_order(ctx, OrderRequest(
        ticker=ticker, qty=qty, side="sell", order_type=order_type, price=price,
        contract_type=contract_type, expiry=expiry, strike=strike, right=right,
    ))

@orders.command()
@click.argument("ticker")
@click.argument("qty", type=float)
@click.option("--entry", type=float, required=True, help="Entry limit price.")
@click.option("--take-profit", type=float, required=True)
@click.option("--stop-loss", type=float, required=True)
@click.pass_context
def bracket(ctx, ticker, qty, entry, take_profit, stop_loss):
    """Place a bracket order: entry limit + automatic take-profit + stop-loss."""
    _run_order(ctx, OrderRequest(
        ticker=ticker, qty=qty, side="buy", order_type="bracket",
        price=entry, take_profit=take_profit, stop_loss=stop_loss,
    ))

@orders.command()
@click.argument("ticker")
@click.option("--price", type=float, required=True, help="Stop loss trigger price.")
@click.pass_context
def stop(ctx, ticker, price):
    """Set a stop-loss order on an existing position."""
    _run_order(ctx, OrderRequest(ticker=ticker, qty=0, side="sell",
                                  order_type="stop", price=price))

@orders.command("trailing-stop")
@click.argument("ticker")
@click.option("--trail-percent", type=float, default=None,
              help="Trail amount as percentage e.g. 2.5 for 2.5%%.")
@click.option("--trail-amount", type=float, default=None,
              help="Trail amount in dollars e.g. 5.00.")
@click.pass_context
def trailing_stop(ctx, ticker, trail_percent, trail_amount):
    """Set a trailing stop on an existing position. Use either --trail-percent or --trail-amount."""
    if not trail_percent and not trail_amount:
        raise click.UsageError("Provide --trail-percent or --trail-amount")
    _run_order(ctx, OrderRequest(
        ticker=ticker, qty=0, side="sell", order_type="trailing_stop",
        trail_percent=trail_percent, trail_amount=trail_amount,
    ))

@orders.command("take-profit")
@click.argument("ticker")
@click.option("--price", type=float, required=True, help="Take profit target price.")
@click.pass_context
def take_profit(ctx, ticker, price):
    """Set a take-profit limit order on an existing position."""
    _run_order(ctx, OrderRequest(ticker=ticker, qty=0, side="sell",
                                  order_type="limit", price=price))

@orders.command()
@click.argument("order_id")
@click.option("--price", type=float, default=None, help="New limit price.")
@click.option("--qty", type=float, default=None, help="New quantity.")
@click.pass_context
def modify(ctx, order_id, price, qty):
    """Modify a pending order's price or quantity."""
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    kwargs = {}
    if price:
        kwargs["price"] = price
    if qty:
        kwargs["quantity"] = qty
    async def run():
        await adapter.connect()
        try:
            return await adapter.modify_order(order_id, **kwargs)
        finally:
            await adapter.disconnect()
    output_json(asyncio.get_event_loop().run_until_complete(run()))

@orders.command()
@click.argument("order_id")
@click.pass_context
def cancel(ctx, order_id):
    """Cancel a pending order by ORDER_ID."""
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    async def run():
        await adapter.connect()
        try:
            ok = await adapter.cancel_order(order_id)
        finally:
            await adapter.disconnect()
        return {"cancelled": ok, "order_id": order_id}
    output_json(asyncio.get_event_loop().run_until_complete(run()))

@orders.command("list")
@click.option("--status", default="all",
              type=click.Choice(["open", "filled", "cancelled", "all"]),
              help="Filter by order status.")
@click.pass_context
def list_orders(ctx, status):
    """List orders. Filter by --status open|filled|cancelled|all."""
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    async def run():
        await adapter.connect()
        try:
            return await adapter.list_orders(status)
        finally:
            await adapter.disconnect()
    output_json(asyncio.get_event_loop().run_until_complete(run()))
```

**Step 4: Run to verify pass**
```bash
pytest tests/unit/test_cli_orders.py -v
trader orders --help
```

**Step 5: Commit**
```bash
git add trader/cli/orders.py tests/unit/test_cli_orders.py
git commit -m "feat: add orders CLI (buy, sell, bracket, stop, trailing-stop, take-profit, modify, cancel, list)"
```

---

### Task 17: Positions + News + Strategies CLI

**Difficulty:** M

**Files:**
- Modify: `trader/cli/positions.py`
- Modify: `trader/cli/news.py`
- Modify: `trader/cli/strategies.py`
- Create: `tests/unit/test_cli_strategies.py`

**Step 1: Write failing tests**
```python
# tests/unit/test_cli_strategies.py
import json
from unittest.mock import patch, AsyncMock
from click.testing import CliRunner
from trader.cli.__main__ import cli
import pandas as pd, numpy as np

def make_ohlcv(n=100):
    np.random.seed(0)
    c = 100 + np.cumsum(np.random.randn(n))
    return pd.DataFrame({"open":c,"high":c*1.01,"low":c*0.99,"close":c,"volume":100000})

def test_strategies_signals():
    runner = CliRunner()
    with patch("yfinance.download", return_value=make_ohlcv()):
        result = runner.invoke(cli, ["strategies", "signals", "--tickers", "AAPL", "--strategy", "rsi"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert data[0]["ticker"] == "AAPL"
    assert "signal" in data[0]
    assert "filtered" in data[0]
```

**Step 2: Run to verify failure**
```bash
pytest tests/unit/test_cli_strategies.py -v
# Expected: FAIL
```

**Step 3: Implement**

```python
# trader/cli/positions.py
from __future__ import annotations
import asyncio, click
from trader.adapters.factory import get_adapter
from trader.cli.__main__ import output_json

@click.group()
def positions():
    """Position management: list open positions, close, and P&L."""

@positions.command("list")
@click.pass_context
def list_positions(ctx):
    """List all open positions with market value and unrealized P&L."""
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    async def run():
        await adapter.connect()
        try:
            return await adapter.list_positions()
        finally:
            await adapter.disconnect()
    output_json(asyncio.get_event_loop().run_until_complete(run()))

@positions.command()
@click.argument("ticker")
@click.pass_context
def close(ctx, ticker):
    """Close the entire position for TICKER with a market order."""
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    async def run():
        await adapter.connect()
        try:
            return await adapter.close_position(ticker)
        finally:
            await adapter.disconnect()
    output_json(asyncio.get_event_loop().run_until_complete(run()))

@positions.command()
@click.pass_context
def pnl(ctx):
    """Unrealized and realized P&L across all positions."""
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    async def run():
        await adapter.connect()
        try:
            poss = await adapter.list_positions()
        finally:
            await adapter.disconnect()
        return {
            "unrealized": sum(p.unrealized_pnl for p in poss),
            "realized": sum(p.realized_pnl for p in poss),
            "total": sum(p.unrealized_pnl + p.realized_pnl for p in poss),
            "positions": len(poss),
        }
    output_json(asyncio.get_event_loop().run_until_complete(run()))
```

```python
# trader/cli/news.py
from __future__ import annotations
import asyncio, click
from trader.adapters.factory import get_adapter
from trader.news.benzinga import BenzingaClient
from trader.news.sentiment import SentimentScorer
from trader.cli.__main__ import output_json

@click.group()
def news():
    """News and sentiment analysis via Benzinga."""

@news.command()
@click.option("--tickers", required=True, help="Comma or space-separated tickers e.g. AAPL,MSFT")
@click.option("--limit", default=10, type=int, help="Max articles per ticker.")
@click.pass_context
def latest(ctx, tickers, limit):
    """Get latest news articles for one or more tickers."""
    ticker_list = [t.strip() for t in tickers.replace(",", " ").split()]
    client = BenzingaClient(ctx.obj["config"])
    async def run():
        try:
            return await client.get_news(ticker_list, limit=limit)
        finally:
            await client.aclose()
    output_json(asyncio.get_event_loop().run_until_complete(run()))

@news.command()
@click.argument("ticker")
@click.option("--lookback", default="24h", help="Lookback window e.g. 24h, 48h, 7d.")
@click.pass_context
def sentiment(ctx, ticker, lookback):
    """
    Score news sentiment for TICKER as a float from -1.0 (bearish) to 1.0 (bullish).

    LOOKBACK: Time window e.g. 24h (default), 48h, 7d.
    """
    hours = _parse_lookback(lookback)
    client = BenzingaClient(ctx.obj["config"])
    scorer = SentimentScorer()
    async def run():
        try:
            items = await client.get_news([ticker], limit=50)
        finally:
            await client.aclose()
        return scorer.score(ticker, items, lookback_hours=hours)
    output_json(asyncio.get_event_loop().run_until_complete(run()))

def _parse_lookback(s: str) -> int:
    s = s.lower().strip()
    if s.endswith("d"):
        return int(s[:-1]) * 24
    if s.endswith("h"):
        return int(s[:-1])
    return 24
```

```python
# trader/cli/strategies.py
from __future__ import annotations
import asyncio, json, click
import pandas as pd
import yfinance as yf
from trader.strategies.factory import get_strategy, list_strategies
from trader.strategies.optimizer import Optimizer
from trader.strategies.risk_filter import RiskFilter
from trader.news.benzinga import BenzingaClient
from trader.news.sentiment import SentimentScorer
from trader.cli.__main__ import output_json

@click.group()
def strategies():
    """Strategy signals, backtesting, and parameter optimization."""

def _fetch_ohlcv(ticker: str, interval: str, lookback: str) -> pd.DataFrame:
    df = yf.download(ticker, period=lookback, interval=interval, progress=False)
    df.columns = [c.lower() for c in df.columns]
    return df.rename(columns={"adj close": "close"})

@strategies.command("run")
@click.argument("ticker")
@click.option("--strategy", default="rsi",
              type=click.Choice(list_strategies()), help="Strategy name.")
@click.option("--interval", default="1d", help="Bar interval: 1m, 5m, 1h, 1d.")
@click.option("--lookback", default="90d", help="History window e.g. 30d, 90d, 1y.")
@click.option("--params", default=None, help='JSON strategy params e.g. \'{"period":14}\'')
@click.pass_context
def run_strategy(ctx, ticker, strategy, interval, lookback, params):
    """Run a strategy on TICKER and output signal series."""
    p = json.loads(params) if params else None
    strat = get_strategy(strategy, p)
    df = _fetch_ohlcv(ticker, interval, lookback)
    signals = strat.signals(df)
    output_json({
        "ticker": ticker, "strategy": strategy,
        "signals": signals.tolist(),
        "dates": [str(d) for d in signals.index],
        "latest_signal": int(signals.iloc[-1]),
    })

@strategies.command()
@click.option("--tickers", required=True, help="Comma or space-separated tickers.")
@click.option("--strategy", default="rsi", type=click.Choice(list_strategies()))
@click.option("--interval", default="1d")
@click.option("--lookback", default="90d")
@click.option("--with-news", is_flag=True, default=False,
              help="Apply Benzinga sentiment as a signal filter.")
@click.option("--params", default=None, help='JSON strategy params e.g. \'{"period":14}\'')
@click.pass_context
def signals(ctx, tickers, strategy, interval, lookback, with_news, params):
    """
    Generate trading signals for one or more tickers.

    Returns 1 (buy), -1 (sell), 0 (hold) per ticker, with risk filter metadata.
    Use --with-news to suppress buys on bearish sentiment.
    """
    ticker_list = [t.strip() for t in tickers.replace(",", " ").split()]
    p = json.loads(params) if params else None
    strat = get_strategy(strategy, p)
    rf = RiskFilter()
    results = []

    async def get_sentiments():
        if not with_news:
            return {}
        client = BenzingaClient(ctx.obj["config"])
        scorer = SentimentScorer()
        try:
            items = await client.get_news(ticker_list, limit=20)
        finally:
            await client.aclose()
        sents = {}
        for ticker in ticker_list:
            ticker_items = [i for i in items if i.ticker == ticker]
            sents[ticker] = scorer.score(ticker, ticker_items)
        return sents

    sentiments = asyncio.get_event_loop().run_until_complete(get_sentiments())

    for ticker in ticker_list:
        try:
            df = _fetch_ohlcv(ticker, interval, lookback)
            sig_series = strat.signals(df)
            raw_signal = int(sig_series.iloc[-1])
            sentiment = sentiments.get(ticker)
            filtered = rf.filter(signal=raw_signal, quote=None,
                                  position=None, sentiment=sentiment)
            results.append({
                "ticker": ticker,
                "signal": filtered["signal"],
                "signal_label": {1: "buy", -1: "sell", 0: "hold"}[filtered["signal"]],
                "strategy": strategy,
                "filtered": filtered["filtered"],
                "filter_reason": filtered["filter_reason"],
                "sentiment_score": sentiment.score if sentiment else None,
            })
        except Exception as e:
            results.append({"ticker": ticker, "error": str(e)})

    output_json(results)

@strategies.command()
@click.argument("ticker")
@click.option("--strategy", default="rsi", type=click.Choice(list_strategies()))
@click.option("--from", "from_date", default="2025-01-01", help="Backtest start date YYYY-MM-DD.")
@click.option("--params", default=None)
@click.pass_context
def backtest(ctx, ticker, strategy, from_date, params):
    """Backtest STRATEGY on TICKER from FROM date. Returns total return and sharpe ratio."""
    import numpy as np
    p = json.loads(params) if params else None
    strat = get_strategy(strategy, p)
    df = yf.download(ticker, start=from_date, progress=False)
    df.columns = [c.lower() for c in df.columns]
    signals = strat.signals(df)
    returns = df["close"].pct_change() * signals.shift(1)
    sharpe = float(returns.mean() / returns.std() * np.sqrt(252)) if returns.std() else 0.0
    output_json({
        "ticker": ticker, "strategy": strategy,
        "from": from_date,
        "total_return_pct": round(float(returns.sum() * 100), 2),
        "sharpe": round(sharpe, 3),
        "win_rate": round(float((returns[signals.shift(1) != 0] > 0).mean()), 3),
        "num_trades": int((signals.diff().abs() > 0).sum()),
    })

@strategies.command()
@click.argument("ticker")
@click.option("--strategy", default="rsi", type=click.Choice(list_strategies()))
@click.option("--metric", default="sharpe",
              type=click.Choice(["sharpe", "returns", "win_rate"]))
@click.pass_context
def optimize(ctx, ticker, strategy, metric):
    """Grid-search best parameters for STRATEGY on TICKER."""
    from trader.strategies.rsi import RSIStrategy
    from trader.strategies.macd import MACDStrategy
    from trader.strategies.ma_cross import MACrossStrategy

    _grids = {
        "rsi": {"period": [7, 14, 21], "oversold": [25, 30], "overbought": [70, 75]},
        "macd": {"fast": [8, 12], "slow": [21, 26], "signal": [7, 9]},
        "ma_cross": {"fast_window": [10, 20], "slow_window": [40, 50]},
        "bnf": {"lookback": [10, 20], "breakout_pct": [0.01, 0.02]},
    }
    strat_cls = get_strategy(strategy).__class__
    opt = Optimizer()
    df = _fetch_ohlcv(ticker, "1d", "1y")
    best = opt.grid_search(strat_cls, df, _grids.get(strategy, {}), metric=metric)
    output_json({"ticker": ticker, "strategy": strategy, "metric": metric, "best_params": best})
```

**Step 4: Run to verify pass**
```bash
pytest tests/unit/test_cli_strategies.py -v
trader strategies --help
trader positions --help
trader news --help
```

**Step 5: Commit**
```bash
git add trader/cli/positions.py trader/cli/news.py trader/cli/strategies.py \
        tests/unit/test_cli_strategies.py
git commit -m "feat: add positions, news, and strategies CLI commands"
```

---

## Phase 8: Cleanup & Configuration

### Task 18: Update .env.example and .gitignore

**Difficulty:** S

**Files:**
- Modify: `.env.example`
- Modify: `.gitignore`

**Step 1: Update .env.example**
```bash
# .env.example

# =============================================================================
# IBKR Client Portal Gateway (default broker — headless, no TWS required)
# Start gateway: https://interactivebrokers.github.io/cpwebapi/
# =============================================================================
IB_HOST=127.0.0.1
IB_PORT=5000
IB_ACCOUNT=

# =============================================================================
# IBKR TWS / Gateway (optional — only for --broker ibkr-tws)
# Requires: pip install 'trader[tws]' and TWS/Gateway running locally
# =============================================================================
# IB_PORT=7497  # paper trading
# IB_PORT=7496  # live trading

# =============================================================================
# News (Benzinga)
# Get key at: https://www.benzinga.com/apis
# =============================================================================
BENZINGA_API_KEY=

# =============================================================================
# Strategy defaults
# =============================================================================
MAX_POSITION_PCT=0.05
DEFAULT_STRATEGY=rsi
DEFAULT_BROKER=ibkr-rest
```

**Step 2: Update .gitignore**
```
.env
.venv/
__pycache__/
*.pyc
*.pyo
*.egg-info/
dist/
build/
.pytest_cache/
outputs/
results/
volatility/optimized_parameters/
```

**Step 3: Commit**
```bash
git add .env.example .gitignore
git commit -m "chore: update .env.example and .gitignore for new structure"
```

---

### Task 19: Delete old code

**Difficulty:** S

**Step 1: Remove old files**
```bash
git rm portfolio_discover_by_sector.py portfolio_optimise_strategies.py \
       portfolio_run_strategy.py portfolio_update_data.py \
       run_test.sh test_ibkr_all_assets.py
git rm -r vibe/ volatility/
```

**Step 2: Verify package still works**
```bash
trader --help
pytest tests/ -v
```

**Step 3: Commit**
```bash
git commit -m "chore: remove old vibe/ and volatility/ modules, replaced by trader package"
```

---

### Task 20: Full test run + smoke test

**Difficulty:** S

**Step 1: Run all tests**
```bash
pytest tests/ -v --tb=short
# Expected: All tests pass. No import errors.
```

**Step 2: Smoke test CLI help tree**
```bash
trader --help
trader account --help
trader quotes --help
trader orders --help
trader positions --help
trader news --help
trader strategies --help
```

**Step 3: Verify JSON output shape**
```bash
# These will fail to connect (no broker running) but should return JSON errors, not stack traces
trader account summary 2>&1 | python -c "import sys,json; json.load(sys.stdin)" && echo "valid JSON"
```

**Step 4: Final commit**
```bash
git add .
git commit -m "feat: agent-first trader CLI v0.1.0 complete"
```

---

## Summary

| Phase | Tasks | What's built |
|---|---|---|
| 1 | 1–3 | pyproject.toml, package structure, Config |
| 2 | 4 | All Pydantic models |
| 3 | 5 | Adapter ABC |
| 4 | 6–8 | IBKR REST adapter + TWS adapter |
| 5 | 9–10 | Benzinga client + sentiment scorer |
| 6 | 11–13 | RSI, MACD, MACross, BNF, Optimizer, RiskFilter, Factory |
| 7 | 14–17 | Full CLI (account, quotes, orders, positions, news, strategies) |
| 8 | 18–20 | Cleanup, .env, delete old code |

**20 tasks. All output JSON. Agent-operated via `trader --help`.**
