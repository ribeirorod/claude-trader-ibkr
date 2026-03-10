# Codebase Structure

**Analysis Date:** 2026-03-10

## Directory Layout

```
trader/
├── vibe/                          # Trading execution SDK (async, venue-agnostic)
│   ├── __init__.py                # Exports: Trader, Scheduler
│   ├── trader.py                  # Facade: Trader class (buy/sell/bracket/history/news)
│   ├── models.py                  # DTOs: OrderResponse, OrderStatus, Side, OrderType, etc.
│   ├── scheduler.py               # Async task scheduler (every/at/cron decorators)
│   ├── utils.py                   # Async helpers: retry, timeout, TTLIdempotencyMap
│   ├── data_fetchers/             # Reserved directory (currently empty)
│   └── venues/
│       └── ibkr.py                # IBKRAdapter: all ib_insync integration
│
├── volatility/
│   └── composer/                  # Strategy research & portfolio management engine
│       ├── __init__.py
│       ├── main.py                # CLI entry point: --mode manage|optimise|screen
│       ├── optimise.py            # Standalone optimization runner
│       ├── test_optimiser.py      # Optimizer tests
│       ├── core/                  # Core domain models and data layer
│       │   ├── config.py          # Config loading
│       │   ├── models.py          # Pydantic models: Stock, Trade, SectorPerformance
│       │   ├── data_fetchers.py   # MarketDataFetcher ABC + YFinance/PyTickerSymbols/FMP impls
│       │   ├── ibkr_data_fetcher.py  # IBKRDataFetcher: bridges vibe.Trader → volatility
│       │   ├── data_processors.py # IndicatorCalculator (MA, RSI, MACD, BB, ATR, etc.)
│       │   ├── data_persistence.py# DataPersistence: CSV/JSON import-export
│       │   └── plotter.py         # Plotter: HTML/PNG/CSV charts
│       ├── strategies/            # Strategy implementations
│       │   ├── __init__.py        # Exports all strategy classes
│       │   ├── base.py            # BaseStrategy ABC (execute, backtest, plot, train_test_split)
│       │   ├── rsi.py             # RSIStrategy
│       │   ├── macd.py            # MACDStrategy
│       │   ├── macross.py         # MACrossStrategy (moving average crossover)
│       │   ├── bnf.py             # BNFStrategy (Bollinger + RSI + ATR composite)
│       │   ├── bb.py              # BBStrategy (Bollinger Bands)
│       │   ├── stochastic.py      # StochasticStrategy
│       │   └── macrsi.py          # MACRSIStrategy (MA + RSI combined)
│       ├── tools/                 # Orchestration and tooling
│       │   ├── __init__.py
│       │   ├── strategy_factory.py# StrategyFactory: name → class mapping
│       │   ├── strategy_executor.py # StrategyExecutor: parallel backtest runner
│       │   ├── optimiser.py       # StrategyOptimizer: grid search over param ranges
│       │   ├── screener.py        # AssetsScreener: technical + fundamental screening
│       │   ├── manager.py         # Portfolio manager utilities
│       │   ├── mailing.py         # Email report delivery
│       │   └── vibe_adapter.py    # Additional vibe integration adapter
│       ├── config/
│       │   └── settings.yaml      # Default strategy params, DB URL, logging level
│       ├── prompts/               # (Likely LLM prompt templates - not analyzed)
│       ├── resources/             # Runtime data files (committed)
│       │   ├── best_params.json   # Optimized strategy parameters by ticker+strategy
│       │   ├── watchlist.csv      # Tickers to track
│       │   ├── portfolio.csv      # Current positions snapshot (resources copy)
│       │   └── trades.csv         # Trade history
│       ├── optimized_parameters/  # Per-ticker optimization output JSONs
│       └── results/               # Strategy backtest result artifacts
│
├── outputs/                       # Runtime data outputs (gitignored)
│   ├── portfolio.csv              # Live IBKR portfolio positions snapshot
│   ├── history.csv                # Accumulated OHLCV history (Date, Ticker, OHLCV)
│   ├── indicators.csv             # Calculated technical indicators per ticker/date
│   ├── portfolio_signals_*.json   # Signal output files (timestamped)
│   ├── ibkr_assets/               # IBKR asset discovery cache
│   ├── ibkr_cache/                # Persistent per-ticker OHLCV CSV cache (keyed by date range)
│   ├── news/                      # News output artifacts
│   ├── signals/                   # Signal output directory
│   └── strategies/                # Strategy output: best_params.json (optimized copy)
│
├── examples/                      # Runnable usage examples and integration tests
│   ├── one_off.py                 # Simple buy + history fetch demo
│   ├── scheduled.py               # Breakout strategy with Scheduler loop
│   ├── bracket.py                 # Bracket order demo
│   ├── indicators_example.py      # IndicatorCalculator usage demo
│   ├── list_and_modify.py         # List orders + modify demo
│   ├── news_demo.py               # News API demo
│   └── simple_integration_test.py # End-to-end smoke test
│
├── tests/                         # Test suite
│   ├── test_imports.py            # Import smoke tests
│   └── tests_manual_mvp_smoke.py  # Manual MVP smoke tests
│
├── results/                       # Additional result artifacts directory
│
├── portfolio_update_data.py       # Workflow: refresh positions + history + indicators
├── portfolio_run_strategy.py      # Workflow: generate buy/sell/hold signals for portfolio
├── portfolio_optimise_strategies.py # Workflow: optimize strategy parameters (monthly)
├── portfolio_discover_by_sector.py  # Workflow: discover new assets by sector
├── test_ibkr_all_assets.py        # IBKR asset type integration test
├── run_test.sh                    # Shell test runner
├── requirements.txt               # Python dependencies
├── .env.example                   # Environment variable template
├── trader.code-workspace          # VS Code workspace config
└── README.md                      # Setup guide
```

---

## Directory Purposes

| Directory | Purpose | Contains | Key Files |
|-----------|---------|----------|-----------|
| `vibe/` | Async trading SDK — the execution layer | Trader facade, models, scheduler, utils, venue adapters | `trader.py`, `models.py`, `venues/ibkr.py` |
| `vibe/venues/` | Venue-specific adapters | Currently IBKR only | `ibkr.py` |
| `volatility/composer/` | Strategy research & portfolio engine | Core, strategies, tools, config | `main.py` |
| `volatility/composer/core/` | Domain models + data layer | Pydantic models, fetchers, indicators, persistence, plotting | `models.py`, `data_fetchers.py`, `ibkr_data_fetcher.py`, `data_processors.py` |
| `volatility/composer/strategies/` | Technical strategy implementations | BaseStrategy ABC + 7 concrete strategies | `base.py`, `macd.py`, `rsi.py`, `bnf.py` |
| `volatility/composer/tools/` | Orchestration tooling | Factory, executor, optimizer, screener, mailer | `strategy_factory.py`, `optimiser.py`, `screener.py` |
| `volatility/composer/resources/` | Committed runtime data | Watchlist, best params, portfolio snapshot | `best_params.json`, `watchlist.csv` |
| `volatility/composer/config/` | Configuration files | YAML settings | `settings.yaml` |
| `outputs/` | Generated runtime data | CSVs and JSONs produced by workflow scripts | `portfolio.csv`, `history.csv`, `indicators.csv` |
| `outputs/ibkr_cache/` | Persistent IBKR OHLCV cache | Per-ticker-date CSVs to avoid redundant IBKR calls | `{TICKER}_{start}_{end}_1d.csv` |
| `examples/` | Runnable demonstrations | One-off scripts, integration tests, usage examples | `scheduled.py`, `bracket.py` |
| `tests/` | Automated tests | Import checks, manual smoke tests | `test_imports.py` |

---

## Where to Add New Code

| What | Location | Notes |
|------|----------|-------|
| New trading venue (e.g. crypto exchange) | `vibe/venues/{exchange}.py` | Implement same interface as `IBKRAdapter`; wire into `vibe/trader.py` |
| New strategy | `volatility/composer/strategies/{name}.py` | Subclass `BaseStrategy`, implement `execute()` and `plot()`; register in `strategies/__init__.py` and `StrategyFactory.strategies` dict |
| New technical indicator | `volatility/composer/core/data_processors.py` | Add method to `IndicatorCalculator` |
| New data source | `volatility/composer/core/data_fetchers.py` | Subclass `MarketDataFetcher`, implement `fetch_stock_data()` |
| New portfolio workflow script | project root (`portfolio_*.py`) | Import `from vibe import Trader` and/or `volatility/composer` modules |
| New screening criterion | `volatility/composer/tools/screener.py` | Add to `_process_screening_criteria()` |
| New optimization strategy | `portfolio_optimise_strategies.py` | Add entry to `STRATEGY_PARAM_RANGES` and `STRATEGY_CLASSES` dicts |
| Example/demo | `examples/` | Standalone async script importing `from vibe import Trader` |
| Test | `tests/` | `test_*.py` naming convention |

---

## Naming Conventions

- **Files:** `snake_case.py` — Example: `ibkr_data_fetcher.py`, `strategy_executor.py`
- **Directories:** `snake_case` — Example: `data_fetchers/`, `optimized_parameters/`
- **Classes:** `PascalCase` — Example: `IBKRAdapter`, `BaseStrategy`, `StrategyOptimizer`
- **Functions/methods:** `snake_case` — Example: `fetch_stock_data`, `calculate_sharpe_ratio`
- **Constants/config dicts:** `UPPER_SNAKE_CASE` — Example: `STRATEGY_PARAM_RANGES`, `STRATEGY_CLASSES`
- **Output files:** `{name}_{YYYYMMDD_HHMMSS}.json` for timestamped signals; `{ticker}_{start}_{end}_{interval}.csv` for cache files

---

## Special Directories

| Directory | Purpose | Generated | Committed |
|-----------|---------|-----------|-----------|
| `outputs/` | Runtime workflow outputs (portfolio, history, signals) | Yes | No (gitignored) |
| `outputs/ibkr_cache/` | Persistent OHLCV cache to avoid redundant IBKR calls | Yes | No |
| `volatility/composer/resources/` | Runtime config and parameter data shared across runs | Partially | Yes (`best_params.json`, `watchlist.csv`) |
| `volatility/composer/optimized_parameters/` | Per-ticker optimization JSON outputs | Yes | No |
| `volatility/composer/results/` | Backtest result artifacts | Yes | No |
| `.venv/` | Python virtual environment | Yes | No |
| `__pycache__/` | Python bytecode cache | Yes | No |
