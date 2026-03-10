# Agent-First Trader CLI — Design Document

**Date:** 2026-03-10
**Status:** Approved

---

## Overview

A clean-slate rewrite of the existing trading tool as an **agent-first CLI**. The primary consumer is an AI agent (Claude), not a human. The CLI exposes all trading operations as subcommands with JSON output and comprehensive `--help` documentation so the agent can discover and operate the tool autonomously.

**Deployment target:** Headless server/VPS — no GUI, no TWS required.

---

## Architecture

### Approach: Pluggable Adapter CLI (Approach B)

```
trader/
  cli/
    __main__.py          # Entry point: `trader` or `python -m trader`
    orders.py            # buy, sell, cancel, modify, stop, trailing-stop, take-profit, bracket
    positions.py         # list, close, pnl
    quotes.py            # quote, chain (options chain)
    news.py              # latest, sentiment
    strategies.py        # run, signals, backtest, optimize
    account.py           # summary, balance, margin
  adapters/
    base.py              # Adapter ABC
    ibkr_rest/           # IBKR Client Portal Gateway (default, headless, REST)
      client.py
      adapter.py
    ibkr_tws/            # ib_insync (local dev, TWS required)
      adapter.py
  strategies/            # Pure functions, ported from volatility/
    base.py
    rsi.py
    macd.py
    ma_cross.py
    bnf.py
    optimizer.py
    risk_filter.py
  news/
    benzinga.py          # Benzinga REST client
    sentiment.py         # Keyword-weighted scorer → [-1.0, 1.0]
  models/                # Pydantic models, all JSON-serializable
    order.py
    position.py
    quote.py
    news.py
    signal.py
    account.py
  config.py              # Loads .env, validates required vars
pyproject.toml
```

---

## CLI Command Surface

```bash
trader --broker [ibkr-rest|ibkr-tws] --output [json|table] <command>

# Account
trader account summary
trader account balance
trader account margin

# Quotes
trader quote get AAPL MSFT TSLA
trader quote chain AAPL --expiry 2026-04-17
trader quote chain AAPL --expiry 2026-04-17 --strike 200 --right call

# Orders
trader orders buy AAPL 10 --type limit --price 195.00
trader orders buy AAPL --contract-type option --expiry 2026-04-17 --strike 200 --right call --qty 1
trader orders sell AAPL 10 --type market
trader orders cancel <order-id>
trader orders modify <order-id> --price 196.00
trader orders list --status [open|filled|cancelled|all]
trader orders bracket AAPL 10 --entry 195 --take-profit 205 --stop-loss 190
trader orders stop AAPL --price 190.00
trader orders trailing-stop AAPL --trail-percent 2.5
trader orders trailing-stop AAPL --trail-amount 5.00
trader orders take-profit AAPL --price 210.00

# Positions
trader positions list
trader positions close AAPL
trader positions pnl

# News
trader news latest --tickers AAPL MSFT --limit 10
trader news sentiment AAPL --lookback 24h

# Strategies
trader strategies run AAPL --strategy rsi --interval 1d --lookback 90d
trader strategies signals --tickers AAPL MSFT TSLA --strategy macd
trader strategies backtest AAPL --strategy rsi --from 2025-01-01
trader strategies optimize AAPL --strategy rsi
```

All commands output JSON. Errors return `{"error": "...", "code": "..."}` with non-zero exit code.

---

## Adapter ABC

```python
class Adapter(ABC):
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def get_account(self) -> Account: ...
    async def get_quotes(self, tickers: list[str]) -> list[Quote]: ...
    async def get_option_chain(self, ticker: str, expiry: str) -> OptionChain: ...
    async def place_order(self, req: OrderRequest) -> Order: ...
    async def modify_order(self, order_id: str, **kwargs) -> Order: ...
    async def cancel_order(self, order_id: str) -> bool: ...
    async def list_orders(self, status: str = "all") -> list[Order]: ...
    async def list_positions(self) -> list[Position]: ...
    async def close_position(self, ticker: str) -> Order: ...
    async def get_news(self, tickers: list[str], limit: int) -> list[NewsItem]: ...
```

`ibkr-rest` connects to IBKR Client Portal Gateway (default port 5000, REST/JSON, headless).
`ibkr-tws` connects via ib_insync socket to TWS/Gateway (port 7497, local dev only).
`ibkr-tws` is an optional install: `pip install trader[tws]`.

---

## OrderRequest Model

```python
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
```

---

## News & Sentiment

**Source:** Benzinga REST API (`BENZINGA_API_KEY`)

```python
class SentimentResult(BaseModel):
    ticker: str
    score: float           # -1.0 (bearish) to 1.0 (bullish)
    signal: Literal["bullish", "bearish", "neutral"]
    article_count: int
    lookback_hours: int
    top_headlines: list[str]
```

Scoring: keyword-weighted on headline + summary. Stateless, deterministic, no external model.
Upgrade path: swap scorer for Claude API call.

---

## Strategy Engine

Strategies are pure functions — no broker dependency, no file I/O.

```python
class BaseStrategy(ABC):
    def signals(self, ohlcv: pd.DataFrame) -> pd.Series: ...  # 1, -1, 0
    def default_params(self) -> dict: ...

class RiskFilter:
    def filter(
        self, signal, quote, position, sentiment,
        max_position_pct=0.05,
        min_sentiment=-0.2
    ) -> int: ...
```

Ported strategies: RSI, MACD, MACross, BNF.
Optimizer: grid-search on sharpe/returns/win_rate.

Signal output includes `filtered` + `filter_reason` for agent observability.

---

## Configuration

```
# Broker
IB_HOST=127.0.0.1
IB_PORT=5000
IB_ACCOUNT=
IBKR_USERNAME=
IBKR_PASSWORD=

# News
BENZINGA_API_KEY=

# Strategy defaults
MAX_POSITION_PCT=0.05
DEFAULT_STRATEGY=rsi
DEFAULT_BROKER=ibkr-rest
```

---

## What Gets Deleted

- `portfolio_*.py` scripts
- `volatility/` module (strategies ported, rest discarded)
- `vibe/` module (adapter ported to `adapters/ibkr_tws/`, rest discarded)
- `requirements.txt` → replaced by `pyproject.toml`

---

## Packaging

```toml
[project]
name = "trader"
version = "0.1.0"
requires-python = ">=3.10"

[project.scripts]
trader = "trader.cli.__main__:app"

[project.optional-dependencies]
tws = ["ib_insync>=0.9.86"]
```

---

## Out of Scope (extend later)

- Multi-leg options spreads (iron condor, straddle, vertical)
- Conditional orders
- Portfolio-level risk management
- Claude API sentiment scoring
- Persistent database (currently stateless)
