# External Integrations

**Analysis Date:** 2026-03-10

## APIs & Services
| Service | Purpose | SDK/Client | Auth (env var) |
|---------|---------|------------|----------------|
| Interactive Brokers TWS/Gateway | Order execution, positions, historical data, news | `ib_insync==0.9.86` | `IB_HOST`, `IB_PORT`, `IB_CLIENT_ID`, `IB_ACCOUNT` (socket, no API key) |
| Yahoo Finance | Historical OHLCV data, fundamentals, dividends | `yfinance==0.2.43` | None (public) |
| Financial Modeling Prep (FMP) | Historical prices, company profiles, key metrics, stock screener | `requests` (direct REST) | `FM_API_KEY` |
| Google Gmail API | Send daily trading signal email reports | `google-api-python-client==2.149.0`, `google-auth==2.35.0` | OAuth2 credentials JSON file (path hardcoded in `volatility/composer/tools/mailing.py`) |

## Data Storage
- **Database:** None detected — no ORM, no SQL client, no managed database.
- **File Storage:** Local filesystem only.
  - `outputs/` — Runtime outputs: portfolio CSVs, IBKR cache, news, signals, strategy results.
  - `outputs/ibkr_cache/` — Cached IBKR asset lists.
  - `results/` — Strategy backtest results.
  - `volatility/optimized_parameters/` — JSON files with per-ticker optimised strategy parameters.
  - Pickle files (`.pkl`) used for intermediate data persistence via `volatility/composer/core/data_persistence.py` (`DataPersistence.save_data` / `load_data`).
  - CSV and JSON exports via `DataPersistence.export_csv` / `export_json`.
- **Caching:** In-process only.
  - `IBKRAdapter._qualified_cache` — Dict cache for qualified IBKR contracts (in-memory, per session).
  - `TTLIdempotencyMap` in `vibe/utils.py` — TTL-based in-memory order deduplication (1 hour TTL, 5000 entry cap).
  - `IBKRDataFetcher._cache` in `volatility/composer/core/ibkr_data_fetcher.py` — In-memory OHLCV cache keyed by `ticker_start_end_interval`.

## Auth Provider
- No user-facing auth. The system authenticates to external services as follows:
  - **IBKR:** Socket connection to local TWS/Gateway process (no token/key — TWS must already be authenticated by the operator).
  - **Gmail:** OAuth2 `InstalledAppFlow` using a local service account JSON file (`credentials_path` parameter in `Mailer.__init__`). The path is currently hardcoded as `/Users/rribeiro/private/volatility/composer/config/gcp_volatility_iam.json` in `volatility/composer/tools/mailing.py` — not parameterised via env var.
  - **FMP:** API key passed via `FM_API_KEY` env var, injected as `apikey` query parameter in all REST calls.
  - **Yahoo Finance:** No auth required.

## Observability
- **Error Tracking:** None (no Sentry, Rollbar, etc.).
- **Logging:**
  - `vibe/` module: stdlib `logging` directly.
  - `volatility/` module: stdlib `logging` with optional YAML config (`config/logging.yaml`) loaded in `volatility/composer/core/config.py`.
  - `structlog>=23,<25` is declared in `requirements.txt` but not observed in use within source files.
  - Log level defaults to `INFO`; overridable via `LOG_CFG` env var pointing to a YAML config path.

## CI/CD & Deployment
- **Hosting:** Not detected — no Dockerfile, docker-compose, Procfile, or cloud provider config found.
- **CI:** Not detected — no `.github/workflows/`, `.circleci/`, or similar.
- **Execution:** Scripts are run manually or via shell (`run_test.sh` at project root).

## Required Environment Variables
| Variable | Service | Required |
|----------|---------|----------|
| `IB_HOST` | IBKR TWS/Gateway host | No (defaults to `127.0.0.1`) |
| `IB_PORT` | IBKR TWS/Gateway port | No (defaults to `7497`) |
| `IB_CLIENT_ID` | IBKR connection client ID | No (defaults to `101`) |
| `IB_ACCOUNT` | IBKR account filter | No |
| `ORDER_TIMEOUT` | IBKR order placement timeout (ms) | No (defaults to `5000`) |
| `HISTORY_TIMEOUT` | IBKR historical data timeout (ms) | No (defaults to `10000`) |
| `MAX_CONCURRENT_ORDERS` | Order concurrency cap | No (defaults to `10`) |
| `FM_API_KEY` | Financial Modeling Prep REST API | Yes (if using `FMPDataFetcher`) |
| `LOG_CFG` | Path to logging YAML config | No |

## Webhooks
- **Incoming:** None.
- **Outgoing:** None (email is push via Gmail API, not a webhook).

## IBKR Connection Details
The `IBKRAdapter` in `vibe/venues/ibkr.py` connects via `ib_insync.IB.connectAsync()` to a locally-running TWS or IB Gateway process. The connection uses:
- Auto-retry on `asyncio.TimeoutError` (3 retries, exponential backoff starting at 100ms).
- Client IDs are managed manually: `vibe/` defaults to `IB_CLIENT_ID=101`; `volatility/composer/core/ibkr_data_fetcher.py` uses a global counter starting at `300` to avoid collision when multiple `IBKRDataFetcher` instances are created in the same process.
- IBKR only allows one connection per `clientId`, so running multiple scripts simultaneously requires distinct `IB_CLIENT_ID` values.

## FMP Integration Details
`FMPDataFetcher` in `volatility/composer/core/data_fetchers.py` calls three FMP endpoint families:
- `GET /api/v3/stock-screener` — ticker discovery by industry
- `GET /api/v4/historical-price/{ticker}` — OHLCV history
- `GET /api/v3/profile/{ticker}` — company profile
- `GET /api/v3/key-metrics-ttm/{ticker}` — key financial metrics
- `GET /api/v3/ratios-ttm/{ticker}` — financial ratios

All calls use `requests` with a 10-second timeout. Errors are logged and silently skipped per ticker.

## Gmail Integration Details
`Mailer` in `volatility/composer/tools/mailing.py` uses `google-auth-oauthlib.flow.InstalledAppFlow` to authenticate interactively via a local browser. The credentials JSON path and recipient address (`eurodribeiro@gmail.com`) are hardcoded — this is a development-stage implementation. The module-level code at the bottom of `mailing.py` executes on import (instantiating `Mailer` and calling `send_daily_update`), which is a side-effect risk.
