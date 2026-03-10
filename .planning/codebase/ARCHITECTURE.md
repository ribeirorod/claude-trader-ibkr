# Architecture

**Analysis Date:** 2026-03-10

## Pattern Overview
- **Overall:** Two-subsystem monorepo — a thin async trading execution SDK (`vibe/`) and a strategy research/analysis engine (`volatility/composer/`), connected by the root-level portfolio scripts and the `IBKRDataFetcher` bridge.
- **Key characteristics:**
  - Adapter pattern isolating the IBKR venue behind a uniform `Trader` facade
  - Abstract base class pattern for strategies (`BaseStrategy`) enabling polymorphic execution and optimization
  - All order I/O is async (`asyncio` / `ib_insync`); strategy compute is CPU-bound and runs in `ProcessPoolExecutor`
  - No web server or API layer; entry points are standalone Python scripts and a `Scheduler` loop

---

## Layers

**Venue Adapter:**
- Purpose: Normalizes all IBKR TWS/Gateway communication into a single interface
- Location: `vibe/venues/ibkr.py`
- Contains: `IBKRAdapter` — connection management, contract qualification with in-memory cache, order building (market/limit/stop/trailing/bracket), status mapping, history, news
- Depends on: `ib_insync`, `vibe/utils.py`
- Used by: `vibe/trader.py`

**Trader Facade:**
- Purpose: Public API that calling code and scripts import; hides the venue
- Location: `vibe/trader.py`
- Contains: `Trader` class — delegates every method to `self._venue` (`IBKRAdapter`)
- Depends on: `vibe/venues/ibkr.py`, `vibe/models.py`
- Used by: `portfolio_update_data.py`, `portfolio_run_strategy.py`, `portfolio_optimise_strategies.py`, `volatility/composer/core/ibkr_data_fetcher.py`, `examples/`

**Domain Models:**
- Purpose: Shared data contracts for order state and venue metadata
- Location: `vibe/models.py`
- Contains: `OrderResponse` (dataclass), `OrderStatus`, `OrderType`, `Side`, `TimeInForce`, `Venue` enums
- Depends on: stdlib only
- Used by: `vibe/venues/ibkr.py`, `vibe/trader.py`

**Scheduler:**
- Purpose: Lightweight async cron/interval task runner for strategy loops
- Location: `vibe/scheduler.py`
- Contains: `Scheduler` class with `.every()`, `.at()`, `.cron()` decorators and `async run()`
- Depends on: stdlib `asyncio`, `datetime`
- Used by: `examples/scheduled.py`

**Utilities:**
- Purpose: Shared async helpers and IBKR-specific utilities
- Location: `vibe/utils.py`
- Contains: `with_timeout`, `retry_async`, `TTLIdempotencyMap`, `normalize_symbol_ibkr`, `env_int`
- Depends on: stdlib only
- Used by: `vibe/venues/ibkr.py`

**IBKR Bridge (Data Layer):**
- Purpose: Adapts the `Trader` history API to the DataFrame format expected by the strategy engine
- Location: `volatility/composer/core/ibkr_data_fetcher.py`
- Contains: `IBKRDataFetcher` — wraps `Trader.history()`, in-memory cache, `fetch_multiple_async` for parallel fetches, format conversion from IBKR OHLCV to Volatility's `Date`-indexed format
- Depends on: `vibe.Trader`, `pandas`
- Used by: `portfolio_update_data.py`, `portfolio_run_strategy.py`, `portfolio_optimise_strategies.py`, `volatility/composer/tools/screener.py`

**Market Data Fetchers:**
- Purpose: Retrieve historical price data and ticker universe from external sources
- Location: `volatility/composer/core/data_fetchers.py`
- Contains: `MarketDataFetcher` (ABC), `YFinanceDataFetcher`, `PyTickerSymbolsFetcher`, `FMPDataFetcher`
- Depends on: `yfinance`, `pytickersymbols`, `requests` (for FMP REST calls), `dotenv`
- Used by: `volatility/composer/tools/screener.py`, `volatility/composer/main.py`

**Strategy Engine:**
- Purpose: Technical strategy logic with backtesting and Sharpe ratio scoring
- Location: `volatility/composer/strategies/`
- Contains: `BaseStrategy` (ABC with `execute`, `backtest`, `plot`, `train_test_split`), concrete strategies: `RSIStrategy` (`rsi.py`), `MACDStrategy` (`macd.py`), `MACrossStrategy` (`macross.py`), `BNFStrategy` (`bnf.py`), `BBStrategy` (`bb.py`), `StochasticStrategy` (`stochastic.py`), `MACRSIStrategy` (`macrsi.py`)
- Depends on: `volatility/composer/core/data_processors.py` (`IndicatorCalculator`)
- Used by: `StrategyFactory`, `StrategyOptimizer`, `StrategyExecutor`

**Strategy Tools:**
- Purpose: Orchestration — factory creation, parallel execution, parameter optimization, asset screening
- Location: `volatility/composer/tools/`
- Contains:
  - `StrategyFactory` — maps strategy name strings to classes, falls back to MACD on unknown
  - `StrategyExecutor` — runs strategies in `ProcessPoolExecutor`, generates text reports
  - `StrategyOptimizer` — exhaustive grid search over parameter ranges using `ProcessPoolExecutor`, Sharpe-ranked
  - `AssetsScreener` — multi-source screener (yfinance / FMP / IBKR), technical + fundamental criteria, composite score
  - `manager.py` — not analyzed in detail
  - `mailing.py` — email delivery of reports
  - `vibe_adapter.py` — additional adapter bridge

**Data Processors:**
- Purpose: Technical indicator calculations used by strategies and screener
- Location: `volatility/composer/core/data_processors.py`
- Contains: `IndicatorCalculator` (MA, RSI, MACD, Bollinger Bands, ATR, Stochastic, volume ratio, etc.), `SummaryGenerator`
- Depends on: `pandas`, `numpy` (implied)
- Used by: strategies, `AssetsScreener`, `IBKRDataFetcher`

**Data Persistence:**
- Purpose: CSV/JSON import-export helpers
- Location: `volatility/composer/core/data_persistence.py`
- Contains: `DataPersistence` — `export_csv`, `export_json`, `load_json`
- Used by: `volatility/composer/main.py`, optimization scripts

**Plotter:**
- Purpose: Visualization of strategy results
- Location: `volatility/composer/core/plotter.py`
- Contains: `Plotter` class — HTML/PNG/CSV output formats
- Used by: `StrategyFactory`, portfolio scripts

---

## Data Flow

**Portfolio Update (daily workflow):**
1. `portfolio_update_data.py` → `Trader.portfolio_dataframe()` → `IBKRAdapter.portfolio_dataframe()` → IBKR TWS
2. Positions written to `outputs/portfolio.csv`
3. `IBKRDataFetcher.fetch_multiple_async()` → `Trader.history()` per ticker → IBKR historical data
4. OHLCV rows appended to `outputs/history.csv`
5. `IndicatorCalculator.calculate_all_indicators()` → results appended to `outputs/indicators.csv`

**Strategy Signal Generation (run_strategy workflow):**
1. `portfolio_run_strategy.py` reads `outputs/portfolio.csv` → extract ticker list
2. Loads `volatility/composer/resources/best_params.json` → checks parameter freshness (max 30 days)
3. Loads `outputs/history.csv` (CSV-first); missing tickers fetched from IBKR via `IBKRDataFetcher`
4. `StrategyFactory.create_strategy()` → instantiates concrete `BaseStrategy` subclass per ticker
5. `StrategyExecutor.run_parallel()` → `ProcessPoolExecutor` → each strategy calls `.backtest()` → `execute()` → signal series
6. Latest signal extracted (`+1=BUY`, `-1=SELL`, `0=HOLD`) → saved to `outputs/signals/portfolio_signals_*.json`

**Strategy Optimization (monthly workflow):**
1. `portfolio_optimise_strategies.py` loads `outputs/history.csv` (or fetches fresh from IBKR)
2. For each ticker × strategy: `StrategyOptimizer.optimize()` → `generate_parameter_combinations()` → shuffled grid
3. `ProcessPoolExecutor` runs `evaluate_parameters()` on each combo → `BaseStrategy.backtest()` → Sharpe ratio
4. Top 10 params ranked, early-exit if Sharpe > 1.8
5. Best params written to `volatility/composer/resources/best_params.json` (merged, keyed by ticker+strategy)

**Asset Discovery (screening workflow):**
1. `AssetsScreener.screen_assets()` fetches price data via configured source (yfinance / FMP / IBKR)
2. `_calculate_technical_indicators()` → SMA, RSI, MACD, volume ratio, distance from SMA
3. Optionally fetches fundamentals (fault-tolerant) → composite score weighting
4. `_process_screening_criteria()` applies thresholds → returns `List[Stock]`

**Order Execution (live/paper trading):**
1. Caller (example script or strategy) calls `Trader.buy/sell/bracket()`
2. `IBKRAdapter.connect()` (lazy, retried 3×) → `_qualify_stock()` (cached contract lookup)
3. `_build_order()` → constructs `ib_insync` order object
4. `placeOrderAsync()` (with async/sync fallback) → IBKR TWS
5. `OrderResponse` dataclass returned with normalized status

**State Management:**
- No central state store; each script is stateless on startup
- `IBKRAdapter` holds: `_qualified_cache` (in-memory contract cache), `_idemp` (`TTLIdempotencyMap` for order deduplication, TTL=1h)
- `IBKRDataFetcher` holds an in-memory `_cache` dict per instance
- Persistent state lives in `outputs/` CSV/JSON files

---

## Key Abstractions

| Abstraction | Purpose | Location | Pattern |
|-------------|---------|----------|---------|
| `Trader` | Venue-agnostic trading API | `vibe/trader.py` | Facade / Adapter |
| `IBKRAdapter` | IBKR-specific implementation | `vibe/venues/ibkr.py` | Adapter |
| `OrderResponse` | Normalized order state | `vibe/models.py` | Dataclass DTO |
| `Scheduler` | Async task scheduling | `vibe/scheduler.py` | Decorator-based scheduler |
| `TTLIdempotencyMap` | Order dedup with TTL eviction | `vibe/utils.py` | LRU + TTL cache |
| `BaseStrategy` | Strategy contract | `volatility/composer/strategies/base.py` | Abstract Base Class |
| `MarketDataFetcher` | Data source contract | `volatility/composer/core/data_fetchers.py` | Abstract Base Class |
| `StrategyFactory` | Strategy instantiation | `volatility/composer/tools/strategy_factory.py` | Factory |
| `StrategyOptimizer` | Grid search optimization | `volatility/composer/tools/optimiser.py` | Grid search + process pool |
| `IBKRDataFetcher` | Bridge between vibe and volatility | `volatility/composer/core/ibkr_data_fetcher.py` | Adapter bridge |
| `AssetsScreener` | Multi-source screening | `volatility/composer/tools/screener.py` | Strategy + composite score |

---

## Entry Points

| Entry Point | Location | Triggers |
|-------------|----------|----------|
| Portfolio data refresh | `portfolio_update_data.py` | Manual / scheduled cron |
| Strategy signal generation | `portfolio_run_strategy.py` | Manual / scheduled cron |
| Strategy optimization | `portfolio_optimise_strategies.py` | Manual / monthly cron |
| Asset discovery | `portfolio_discover_by_sector.py` | Manual |
| Volatility CLI | `volatility/composer/main.py` | `python main.py --mode [manage|optimise|screen]` |
| Examples | `examples/one_off.py`, `examples/scheduled.py`, `examples/bracket.py` | Manual / demo |

---

## Error Handling

- **Strategy:** `BaseStrategy.backtest()` and `execute()` failures are caught in `StrategyExecutor`; errors returned in result dict under `'error'` key
- **Optimization:** Per-parameter-combo exceptions are logged and skipped; optimization continues
- **IBKR connection:** `retry_async` with 3 retries and exponential backoff for `TimeoutError`; `with_timeout` wraps all IBKR async calls
- **Order submission:** Idempotency via `TTLIdempotencyMap` prevents duplicate orders on retry
- **Data fetching:** `IBKRDataFetcher.fetch_multiple_async` uses `asyncio.gather(return_exceptions=True)`; screener has explicit retry with rate-limit delays
- **Scheduler:** Task exceptions are swallowed to prevent scheduler crash (logged comment, no actual logger call — see CONCERNS)

---

## Cross-Cutting Concerns

- **Logging:** `logging.getLogger(__name__)` used throughout; root logger configured via `basicConfig(level=INFO)` in portfolio scripts; no structured logging
- **Validation:** Minimal; order parameter validation in `_build_order()` (raises `ValueError` for missing prices); no input validation on strategy parameters
- **Authentication:** IBKR connection credentials via environment variables (`IB_HOST`, `IB_PORT`, `IB_CLIENT_ID`, `IB_ACCOUNT`); loaded from `.env` via `dotenv` in fetcher module
- **Concurrency:** Order/history I/O is async (`asyncio`); CPU-bound strategy/optimization workloads use `ProcessPoolExecutor`
