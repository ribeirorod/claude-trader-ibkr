# Technology Stack

**Analysis Date:** 2026-03-10

## Languages
- **Primary:** Python 3.10 — All application code (trading engine, strategy analysis, data fetching)

## Runtime & Package Manager
- Python 3.10.17 (managed via `.venv` at `.venv/`, using Homebrew `python@3.10`)
- pip — Lockfile: not present (flat `requirements.txt`, no `poetry.lock` or `pip-tools` pins for most packages)

## Frameworks
| Framework | Version | Purpose |
|-----------|---------|---------|
| asyncio (stdlib) | 3.10 built-in | Core async I/O for all IBKR communication and scheduling |
| pydantic | 2.9.1 | Data validation and model definitions in `volatility/composer/core/models.py` |

## Key Dependencies
| Package | Version | Why Critical |
|---------|---------|--------------|
| ib_insync | 0.9.86 | IBKR TWS/Gateway async Python client — entire broker integration depends on this |
| pandas | 2.2.2 | OHLCV DataFrames throughout; returned by all history/portfolio methods |
| yfinance | 0.2.43 | Market data fetching in `volatility/composer/core/data_fetchers.py` (YFinanceDataFetcher) |
| pydantic | 2.9.1 | Models and validation in `volatility/composer/core/models.py` |
| python-dotenv | >=1.0,<2 | Loads `.env` for IB_HOST, IB_PORT, IB_CLIENT_ID, IB_ACCOUNT, FM_API_KEY |
| structlog | >=23,<25 | Structured logging (declared; `vibe/` uses stdlib logging, volatility uses stdlib logging too) |
| requests | >=2.31,<3 | HTTP client for FMP REST API in `volatility/composer/core/data_fetchers.py` |
| aiohttp | >=3.9,<4 | Async HTTP (declared dependency, available for async REST calls) |
| pytickersymbols | 1.13.0 | Index/country/industry ticker lookups in `PyTickerSymbolsFetcher` |
| matplotlib | 3.9.2 | Charting/plotting in `volatility/composer/core/plotter.py` |
| plotly | 5.24.1 | Interactive charts in volatility module |
| tqdm | 4.66.5 | Progress bars during batch data fetching |
| google-auth | 2.35.0 | OAuth2 for Gmail API in `volatility/composer/tools/mailing.py` |
| google-api-python-client | 2.149.0 | Gmail send API in `volatility/composer/tools/mailing.py` |
| PyYAML | (implied) | YAML config loading in `volatility/composer/core/config.py` (not pinned in requirements.txt) |

## Configuration
- **Environment:** `.env` file loaded via `python-dotenv`. Key variables:
  - `IB_HOST` (default: `127.0.0.1`) — TWS/Gateway host
  - `IB_PORT` (default: `7497`) — TWS paper port; live is `7496`
  - `IB_CLIENT_ID` (default: `101`) — IBKR connection client ID
  - `IB_ACCOUNT` — IBKR account ID (optional, used for filtering)
  - `ORDER_TIMEOUT` (default: `5000`) — ms timeout for order placement
  - `HISTORY_TIMEOUT` (default: `10000`) — ms timeout for historical data requests
  - `MAX_CONCURRENT_ORDERS` (default: `10`) — concurrency cap
  - `FM_API_KEY` — Financial Modeling Prep API key
  - `LOG_CFG` — Optional path to override `config/logging.yaml`
- **Build:** No build system. Scripts run directly with `python <script>.py`. Virtual environment at `.venv/`.
- **YAML config:** `volatility/composer/core/config.py` reads `config/settings.yaml` and `config/logging.yaml` (paths relative to CWD at invocation)

## Platform Requirements
- **Development:** macOS (darwin), Python 3.10, IBKR TWS or IB Gateway running locally on port 7497 (paper) or 7496 (live)
- **Production:** Single-machine execution; no containerisation or deployment manifests detected. IBKR Gateway must be co-located or network-accessible.

## Project Modules
| Module | Entry Points | Purpose |
|--------|-------------|---------|
| `vibe/` | `vibe.Trader`, `vibe.Scheduler` | Core async trading engine — order management, positions, history, news |
| `volatility/composer/` | `volatility/composer/main.py`, `volatility/composer/cli.py` | Strategy backtesting, optimisation, screening |
| `portfolio_run_strategy.py` | CLI script | Load portfolio, run strategies with optimised params, generate signals |
| `portfolio_optimise_strategies.py` | CLI script | Optimise strategy parameters for held positions |
| `portfolio_update_data.py` | CLI script | Refresh market data cache for portfolio tickers |
| `test_ibkr_all_assets.py` | CLI script | IBKR asset discovery / connectivity test |
| `examples/` | Individual scripts | Usage examples for bracket orders, scheduling, news, indicators |
