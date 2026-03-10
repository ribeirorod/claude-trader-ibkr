# Research: Full Codebase Overview -- Trader Platform

**Date:** 2026-03-10
**Query:** Full vibe/ module, news capabilities, Trader facade, options support, volatility/composer strategy pipeline, portfolio_run_strategy workflow, icli connection mechanism
**Scope:** `vibe/`, `volatility/composer/`, `portfolio_run_strategy.py`, `requirements.txt`, `test_ibkr_all_assets.py`

---

## 1. Request & Derived Requirements

- **Request:** Comprehensive analysis of the trader platform -- what exists, what's missing for a news-aware trading tool, and how the IBKR connection works.
- **Derived Requirements:**
  - Map every file in `vibe/` and its public API
  - Catalog news methods and IBKR news endpoints used
  - Assess options contract support
  - Trace the strategy-to-execution pipeline
  - Determine the connection mechanism (ib_insync vs icli vs something else)

## 2. Relevant File Map

### vibe/ module (core trading library)

| File | Purpose | Key Exports |
|------|---------|-------------|
| `vibe/__init__.py` | Package entry | `Trader`, `Scheduler` |
| `vibe/trader.py` | Facade over venue adapters | `Trader` class (buy, sell, bracket, positions, news, history, etc.) |
| `vibe/models.py` | Domain models | `OrderResponse`, `OrderStatus`, `Side`, `OrderType`, `TimeInForce`, `Venue` |
| `vibe/scheduler.py` | Async task scheduler | `Scheduler` (interval, at-time, cron decorators) |
| `vibe/utils.py` | Shared utilities | `env_int`, `monotonic_ms`, `with_timeout`, `retry_async`, `TTLIdempotencyMap`, `normalize_symbol_ibkr` |
| `vibe/venues/__init__.py` | Empty init | (nothing) |
| `vibe/venues/ibkr.py` | IBKR adapter (ib_insync) | `IBKRAdapter` class -- all actual IBKR interaction |

### volatility/composer/ (strategy engine)

| File | Purpose | Key Exports |
|------|---------|-------------|
| `volatility/composer/strategies/base.py` | Abstract base strategy | `BaseStrategy` (execute, backtest, sharpe, train_test_split) |
| `volatility/composer/strategies/bnf.py` | BNF strategy | `BNFStrategy` |
| `volatility/composer/strategies/macd.py` | MACD strategy | `MACDStrategy` |
| `volatility/composer/strategies/rsi.py` | RSI strategy | `RSIStrategy` |
| `volatility/composer/strategies/macross.py` | MA Crossover strategy | `MACrossStrategy` |
| `volatility/composer/strategies/stochastic.py` | Stochastic strategy | `StochasticStrategy` |
| `volatility/composer/strategies/bb.py` | Bollinger Bands strategy | (available but not registered in factory) |
| `volatility/composer/strategies/macrsi.py` | MAC + RSI combo | (available but not registered in factory) |
| `volatility/composer/tools/strategy_factory.py` | Creates strategy instances | `StrategyFactory` (maps name -> class, creates with params + data) |
| `volatility/composer/tools/strategy_executor.py` | Runs strategies in parallel | `StrategyExecutor` (ProcessPoolExecutor, backtest, report) |
| `volatility/composer/tools/vibe_adapter.py` | Bridge: signals -> orders | `VibeTraderAdapter` (execute_signal, execute_bracket_from_strategy) |
| `volatility/composer/tools/optimiser.py` | Parameter optimization | Optimiser |
| `volatility/composer/tools/screener.py` | Stock screening | Screener |
| `volatility/composer/core/ibkr_data_fetcher.py` | Fetches OHLCV from IBKR | `IBKRDataFetcher` (uses `vibe.Trader.history()`) |
| `volatility/composer/core/data_fetchers.py` | Yahoo Finance fetcher | Data fetchers (yfinance) |
| `volatility/composer/core/data_processors.py` | Indicator calculation | `IndicatorCalculator` |
| `volatility/composer/core/data_persistence.py` | Data save/load | Persistence helpers |
| `volatility/composer/core/config.py` | Settings loader | Config from YAML |
| `volatility/composer/core/models.py` | Pydantic models | Data models |
| `volatility/composer/core/plotter.py` | Chart generation | `Plotter` |

### Top-level scripts

| File | Purpose |
|------|---------|
| `portfolio_run_strategy.py` | End-to-end: load portfolio CSV -> load params -> fetch data -> run strategies -> output signals |
| `portfolio_update_data.py` | Fetch/update historical data |
| `portfolio_discover_by_sector.py` | Sector-based discovery |
| `portfolio_optimise_strategies.py` | Optimize strategy parameters |
| `test_ibkr_all_assets.py` | Scanner-based asset retrieval from IBKR |

## 3. Component Relationships

**Data Flow -- Strategy Execution Pipeline:**

1. `portfolio_run_strategy.py` loads `outputs/portfolio.csv` (ticker positions)
2. Loads `volatility/composer/resources/best_params.json` (optimized strategy parameters per ticker, with freshness check)
3. Fetches OHLCV data: first tries `outputs/history.csv`, falls back to `IBKRDataFetcher` -> `vibe.Trader.history()` -> `IBKRAdapter.history()` -> `ib_insync.IB.reqHistoricalDataAsync()`
4. `StrategyFactory` creates strategy instances (RSI, MACD, BNF, MACross) with optimized params + data
5. `StrategyExecutor.run_parallel()` runs `strategy.backtest()` in a `ProcessPoolExecutor`
6. Each strategy's `execute()` computes indicators and generates a signal series (1=buy, -1=sell, 0=hold)
7. Latest signal extracted and reported; signals saved to `outputs/portfolio_signals_*.json`

**Order Execution Flow (when used):**

1. `VibeTraderAdapter.execute_signal(ticker, signal, quantity)` receives a strategy signal
2. Calls `Trader.buy()` or `Trader.sell()` -> `IBKRAdapter.submit()` -> `ib_insync.IB.placeOrder()`
3. `VibeTraderAdapter.execute_bracket_from_strategy()` creates bracket orders using ATR-derived stops

**Connection Flow:**

1. `IBKRAdapter.__init__()` creates `ib_insync.IB()` instance
2. `IBKRAdapter.connect()` calls `IB.connectAsync(host, port, clientId)`
3. Default: `127.0.0.1:7497` (TWS paper trading port) with client ID 101
4. Environment variables: `IB_HOST`, `IB_PORT`, `IB_CLIENT_ID`, `IB_ACCOUNT`

## 4. Factual Analysis

### Connection Mechanism -- ib_insync (NOT icli)

- **requirements.txt** declares `ib_insync==0.9.86` as the connection library
- `vibe/venues/ibkr.py` imports `from ib_insync import IB, Stock, MarketOrder, LimitOrder, StopOrder, Order`
- **ib_insync** is a Python wrapper around the TWS API (Interactive Brokers' native API)
- It connects to either **TWS (Trader Workstation)** or **IB Gateway** via socket on port 7497 (paper) or 7496 (live)
- **YES, a running TWS or IB Gateway instance is required** -- ib_insync cannot operate standalone; it must connect to TWS/Gateway which in turn connects to IBKR servers
- There is NO icli dependency in requirements.txt or any import in the codebase. The only match for "icli" is in `volatility/composer/tools/mailing.py` which is unrelated.

### Trader Facade -- Public API

The `Trader` class exposes these async methods:

**Order Management:**
- `buy(symbol, quantity, order_type, limit_price, stop_price, tif, client_order_id, trail_amount, trail_percent, limit_offset)` -> `OrderResponse`
- `sell(...)` -> `OrderResponse` (same params as buy)
- `bracket(symbol, side, quantity, entry_price, stop_loss, take_profit, tif, outside_rth)` -> `Dict[str, OrderResponse]` (parent/tp/sl)
- `modify_order(order_id, limit_price, stop_price, quantity, tif, outside_rth, trail_amount, trail_percent, limit_offset)` -> `OrderResponse`
- `cancel(order_id)` -> `None`
- `get_order(order_id)` -> `OrderResponse`
- `list_open_orders()` -> `List[OrderResponse]`

**Portfolio:**
- `positions()` -> `List[Dict]` (symbol, position, avg_cost, market_price, unrealized/realized PnL)
- `portfolio_dataframe()` -> `pd.DataFrame` (comprehensive: positions + open orders + P&L metrics)

**Market Data:**
- `history(symbol, start, end, interval)` -> `pd.DataFrame` (OHLCV)

**News:**
- `news_providers()` -> `List[Dict[str, str]]` (code, name) -- wraps `IB.reqNewsProvidersAsync()`
- `news_history(symbol, start, end, limit, provider_codes)` -> `List[Dict]` (headline, article_id, time, provider) -- wraps `IB.reqHistoricalNewsAsync(conId, providers, start, end, limit)`
- `news_article(provider_code, article_id)` -> `Dict` (article_type, text) -- wraps `IB.reqNewsArticleAsync(provider, articleId)`
- `subscribe_news_bulletins(all_messages, on_bulletin)` -> `None` -- wraps `IB.reqNewsBulletins()`; callback receives {msg_id, msg_type, message, exchange}
- `unsubscribe_news_bulletins()` -> `None`

**Lifecycle:**
- `close()` -> `None`

### News Capabilities -- Detailed

The news implementation wraps four IBKR TWS API endpoints:

1. **reqNewsProviders** -- Lists subscribed news providers (e.g., Benzinga, Briefing.com, Dow Jones). Returns provider code + name.
2. **reqHistoricalNews(conId, providerCodes, start, end, totalResults)** -- Historical headlines for a specific contract. Returns: time, providerCode, articleId, headline. Provider codes are "+"-delimited (e.g., "BZ+BRFG+DJ").
3. **reqNewsArticle(providerCode, articleId)** -- Full article body text by ID. Returns articleType and articleText (HTML or text).
4. **reqNewsBulletins(allMessages)** -- Real-time streaming of IB system bulletins (exchange alerts, halts, etc.). NOT per-symbol news -- these are system-wide operational bulletins.

**Important limitation:** `reqNewsBulletins` provides IB system bulletins (trading halts, exchange status), NOT real-time per-symbol news. For real-time per-symbol news, the TWS API offers `reqMktData` with generic tick type 292 (news), which is NOT currently implemented.

### Options Support

**Current state: NONE.** The codebase is equity-only:
- `_qualify_stock()` creates only `Stock(symbol, "SMART", "USD")` contracts
- `normalize_symbol_ibkr()` has a TODO comment: "Extend later for options/futures OCC format"
- No `Option`, `FuturesOption`, or `Contract(secType='OPT')` anywhere in the code
- No strike, expiry, right (PUT/CALL), or multiplier handling
- Order types support trailing stops and brackets but no options-specific logic (combo orders, spreads, etc.)

### Strategy Pipeline Details

- **BaseStrategy** takes `(name, parameters, data)` where data is a pandas DataFrame with OHLCV columns
- `execute()` is abstract -- each strategy computes indicators (via `IndicatorCalculator`) and returns `{'signals': pd.Series}`
- `backtest()` wraps `execute()` and computes cumulative returns + Sharpe ratio
- Signals: `1` = buy, `-1` = sell, `0` = hold (position-based: cumsum tracks whether in-market)
- **Registered strategies in factory:** RSIStrategy, MACDStrategy, MACrossStrategy, BNFStrategy
- **Available but NOT registered:** BollingerBands (`bb.py`), MACRSI combo (`macrsi.py`)
- Strategies consume ONLY price data (OHLCV). No volume profile, no order book, no news, no fundamentals.

### Scheduler

- Supports three scheduling modes: `every(seconds/minutes)`, `at(time)`, `cron(expr)`
- MVP cron: only `*/N * * * *` (minute step)
- Runs tasks via asyncio with semaphore-based concurrency control
- Silently swallows exceptions (comment says "real impl should log")

## 5. Conceptual Suggestions

### Gaps for a News-Aware Trading Tool

1. **No real-time per-symbol news streaming.** The existing `subscribe_news_bulletins` is for IB system bulletins only. Need to implement `reqMktData` with tick type 292 for real-time news ticks per contract, or use `reqNewsArticle` polling.

2. **No news sentiment analysis.** Headlines and articles are fetched raw. No NLP, no sentiment scoring, no keyword extraction. A news-aware tool would need a sentiment pipeline (LLM-based or traditional NLP).

3. **No news-to-signal integration.** The strategy pipeline (`BaseStrategy.execute()`) only receives OHLCV data. There is no mechanism to pass news data, sentiment scores, or event flags into strategy execution.

4. **No event-driven architecture.** The scheduler supports time-based triggers only. A news-reactive tool needs event-driven triggers (e.g., "when a headline scores > 0.8 sentiment for a held position, evaluate stop adjustment").

5. **No options contracts.** The `_qualify_stock` method only handles equities. Options would need: OCC symbol parsing, Option contract creation (symbol, expiry, strike, right), Greeks data, spread order types.

6. **Missing real-time data streaming.** No `reqMktData` or `reqRealTimeBars` implementation for live price feeds. History endpoint only provides bar data, not ticks.

7. **No risk management layer.** Position sizing, portfolio-level risk limits, correlation-aware allocation are all absent. The VibeTraderAdapter tracks positions but has no risk engine.

### Architectural Strengths

- Clean venue abstraction (`Trader` -> `IBKRAdapter`) makes adding venues straightforward
- Idempotency map prevents duplicate order submission
- Async-first design with proper timeout and retry handling
- Strategy pipeline is well-factored (BaseStrategy -> Factory -> Executor)
- The VibeTraderAdapter bridge pattern is the right architecture for signal-to-order translation

### Pain Points

- `normalize_symbol_ibkr()` is a pass-through -- no real normalization, no multi-asset support
- Multiple `sys.path.insert(0, ...)` hacks for imports between vibe/ and volatility/ -- suggests the project needs proper packaging
- `IBKRDataFetcher` and `VibeTraderAdapter` both manipulate `os.environ['IB_CLIENT_ID']` globally, which is fragile for concurrent use
- ProcessPoolExecutor in StrategyExecutor may fail with non-picklable strategy objects
- Scheduler silently swallows all exceptions

## 6. Related Research

- No prior research exists.

---

*Generated by code-researcher*
