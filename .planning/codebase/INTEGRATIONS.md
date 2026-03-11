# External Integrations

**Analysis Date:** 2026-03-11

## APIs & Services
| Service | Purpose | SDK/Client | Auth (env var) |
|---------|---------|------------|----------------|
| IBKR Client Portal Gateway | Order execution, positions, quotes, alerts, market scanner, news | `httpx.AsyncClient` (direct REST via `IBKRRestClient`) | `IB_HOST`, `IB_PORT`, `IB_ACCOUNT` (session cookie after browser login) |
| IBKR TWS/Gateway (optional) | Same as above, alternate connection mode | `ib_insync>=0.9.86` (optional extra) | Socket connection — TWS must already be authenticated |
| Benzinga | Financial news and sentiment | `httpx.AsyncClient` (direct REST via `BenzingaClient`) | `BENZINGA_API_KEY` (sent as `token` query param, NOT Authorization header) |
| Yahoo Finance | Historical OHLCV data for strategy signals | `yfinance>=0.2` | None (public) |
| Financial Modeling Prep (FMP) | Fundamental screening — earnings, company profiles | `httpx` or `requests` (direct REST) | `FM_API_KEY` (optional) |
| ibeam | IBKR Client Portal Gateway session keepalive | `ibeam>=0.5.10` (Python package) | `IBEAM_ACCOUNT`, `IBEAM_PASSWORD`, optionally `IBEAM_KEY` (TOTP) |

## Data Storage
- **Database:** None — no ORM, no SQL client, no managed database.
- **File Storage:** Local filesystem only.
  - `outputs/` — JSON outputs from CLI commands, organized as `outputs/{group}/{YYYY-MM-DD}/{HH-MM-SS}_{sub}.json`
  - `outputs/news/`, `outputs/scan/`, `outputs/signals/`, `outputs/strategies/`, `outputs/watchlist/` — per-domain output directories
  - `.trader/logs/agent.jsonl` — JSONL agent event log (append-only, one JSON object per line)
  - `.trader/profile.json` — User portfolio profile consumed by all agents
- **Caching:** In-process only. No Redis, Memcached, or persistent cache layer.

## Auth Provider
- No user-facing authentication. The system authenticates to external services as follows:
  - **IBKR Client Portal Gateway (`ibkr-rest`):** HTTPS to `https://{IB_HOST}:{IB_PORT}/v1/api` with session cookie established by browser login. `IBKRRestClient` disables TLS verification (`verify=False`) because the gateway uses a self-signed certificate. The adapter calls `POST /tickle` then `GET /iserver/auth/status` on `connect()`, retrying up to 8 times with 3-second delays.
  - **ibeam keepalive:** `ibeam` package maintains the gateway session. Configured via `IBEAM_*` env vars. When `IBEAM_AUTHENTICATE=True`, ibeam logs in automatically using `IBEAM_ACCOUNT`, `IBEAM_PASSWORD`, and `IBEAM_KEY` (base32 TOTP secret). When `False`, manual browser login is required once; ibeam then keeps the session alive.
  - **IBKR TWS (`ibkr-tws`):** Socket connection via `ib_insync.IB.connectAsync()` to `IB_HOST:IB_PORT`. TWS must already be authenticated. Client ID defaults to `101`.
  - **Benzinga:** API token sent as `token` query parameter. Header must include `Accept: application/json` (NOT `Authorization` header).
  - **Yahoo Finance:** No auth required.
  - **FMP:** API key sent as `apikey` query parameter.

## IBKR Client Portal Gateway Integration

**Base URL:** `https://{IB_HOST}:{IB_PORT}/v1/api` (constructed in `trader/config.py` `ibkr_rest_base_url` property)

**Client:** `trader/adapters/ibkr_rest/client.py` (`IBKRRestClient`) — `httpx.AsyncClient` with `verify=False`, 30-second timeout.

**Adapter:** `trader/adapters/ibkr_rest/adapter.py` (`IBKRRestAdapter`)

**Endpoints used:**
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/tickle` | POST | Initialize/refresh gateway session |
| `/iserver/auth/status` | GET | Check authentication state |
| `/iserver/secdef/search?symbol={ticker}` | GET | Resolve ticker → conid |
| `/iserver/secdef/strikes?conid=...&sectype=OPT&month=...` | GET | Option chain strikes |
| `/iserver/secdef/info?conid=...&sectype=OPT&month=...&strike=...&right=...` | GET | Resolve option conid |
| `/iserver/marketdata/snapshot?conids=...&fields=...` | GET | Real-time quotes (fields: 31=last, 84=bid, 86=ask) |
| `/iserver/account/orders` | GET | List open orders |
| `/iserver/account/{acct}/orders` | POST | Place new order |
| `/iserver/account/{acct}/order/{id}` | POST | Modify order |
| `/iserver/account/{acct}/order/{id}` | DELETE | Cancel order |
| `/iserver/reply/{id}` | POST | Confirm IBKR warning dialogs (required for order submission) |
| `/portfolio/{acct}/summary` | GET | Account balance and margin |
| `/portfolio/{acct}/positions/0` | GET | Open positions |
| `/iserver/news/news?conid=...&limit=...` | GET | News by conid |
| `/iserver/account/{acct}/alerts` | GET | List price alerts |
| `/iserver/account/{acct}/alert` | POST | Create price alert |
| `/iserver/account/{acct}/alert/{id}` | DELETE | Delete alert |
| `/iserver/scanner/run` | POST | Run market scanner |
| `/iserver/scanner/params` | GET | Available scanner parameters |

**Order confirmation flow:** IBKR may return `{"id": "...", "message": [...]}` instead of `{"order_id": "..."}`. `_confirm_replies()` loops up to 5 times posting `{"confirmed": true}` to `/iserver/reply/{id}` until a real order ID is returned.

**Quote snapshot retry:** First snapshot call subscribes the stream; a 1-second sleep + retry is performed for conids that return no price data.

**Order types supported:** `market` (MKT), `limit` (LMT), `stop` (STP), `trailing_stop` (TRAIL), `bracket` (LMT parent + LMT take-profit + STP stop-loss children linked via `parentId`).

## Benzinga News Integration

**Client:** `trader/news/benzinga.py` (`BenzingaClient`) — `httpx.AsyncClient`, 15-second timeout.

**Base URL:** `https://api.benzinga.com/api/v2`

**Endpoints used:**
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/news` | GET | Fetch news by ticker symbols |

**Request parameters:**
```python
params = {
    "token": BENZINGA_API_KEY,       # auth — query param, NOT Authorization header
    "symbols": "AAPL,MSFT",          # comma-separated tickers
    "pageSize": limit,
    "displayOutput": "abstract",
}
headers = {"Accept": "application/json"}
```

**Response mapping:** `id`, `title` → `headline`, `teaser` → `summary`, `created` → `published_at`, `url`, `stocks[0].name` → `ticker`. Returns list of `NewsItem` Pydantic models.

**Usage in CLI:** `trader news get --tickers AAPL,MSFT` and as sentiment signal filter in `trader strategies signals --with-news`.

## Yahoo Finance Integration
- Used via `yfinance` package for historical OHLCV data fetching.
- Data feeds into strategy `signals()` methods via `pd.DataFrame` with columns `open`, `high`, `low`, `close`, `volume`.
- No API key required.

## ibeam Session Keepalive

**Package:** `ibeam>=0.5.10`

**Config via env vars:**
| Variable | Purpose | Default |
|----------|---------|---------|
| `IBEAM_ACCOUNT` | IBKR account username | — |
| `IBEAM_PASSWORD` | IBKR login password | — |
| `IBEAM_GATEWAY_BASE_URL` | Gateway HTTPS URL | `https://localhost:5001` |
| `IBEAM_LOG_LEVEL` | Log verbosity | `WARNING` |
| `IBEAM_AUTHENTICATE` | Automatic login | `False` |
| `IBEAM_KEY` | Base32 TOTP secret for 2FA (only if `IBEAM_AUTHENTICATE=True`) | unset |

**Setup flow (from `.env.example`):**
1. Download and unzip `clientportal.gw.zip` → `clientportal.gw/`
2. Start: `cd clientportal.gw && ./bin/run.sh root/conf.yaml`
3. Browse to `https://localhost:5001` and log in once (manual mode)
4. Run `./scripts/start-gateway.sh` — ibeam keeps the session alive

## Claude Agent/Skill Integrations

**Not external HTTP services** — these are Claude Code prompt files that orchestrate the Python CLI.

**Agents** (`.claude/agents/*.md`): Markdown prompt files defining Claude subagents. Each agent uses the `trader` CLI commands as its primary tool. Key agents:
- `portfolio-conductor.md` — orchestrates pre-market, intraday, and weekly autonomous runs
- `portfolio-manager.md` — investment analysis and trade recommendations
- `risk-monitor.md` — position risk assessment
- `strategy-optimizer.md` — strategy parameter tuning
- `opportunity-finder.md` — new trade opportunity discovery

**Skills** (`.claude/skills/*/`): Reusable prompt fragments referenced by agents. Includes `trader-cli` (CLI command reference), `morning-routine`, `technical-analyst`, `market-news-analyst`, `options-strategy-advisor`, `position-sizer`, `backtest-expert`, and others.

**Scheduling:** `.claude/crons.json` defines recurring agent schedules (pre-market, intraday, weekly). `scripts/setup-crons.sh` is a SessionStart hook that prints registration instructions for Claude Code's `CronCreate` tool.

**Agent runtime data (Python side):**
- `trader/agents/log.py` — `AgentLog` writes/reads JSONL events at `.trader/logs/agent.jsonl`
- `trader/agents/context.py` — `build_context()` assembles snapshot + profile + guardrails dict for agent prompts; `load_profile()` reads `.trader/profile.json`

## Observability
- **Error Tracking:** None (no Sentry, Rollbar, Datadog).
- **Logging:** No structured logging framework. CLI uses `click.echo()` for stdout/stderr. Agent events use custom JSONL log at `.trader/logs/agent.jsonl`.
- **Agent audit trail:** Every agent run emits structured JSON events via `AgentLog.write()` with fields: `ts`, `run_id`, `agent`, `event`, `context`.

## CI/CD & Deployment
- **Hosting:** Not detected — no Dockerfile, docker-compose, Procfile, or cloud provider config.
- **CI:** Not detected — no `.github/workflows/`, `.circleci/`, or similar.
- **Execution:** `trader` CLI run manually or via Claude Code cron scheduling. ibeam manages gateway session.

## Required Environment Variables
| Variable | Service | Required |
|----------|---------|----------|
| `IB_HOST` | IBKR Client Portal Gateway host | No (default: `127.0.0.1`) |
| `IB_PORT` | IBKR Client Portal HTTPS port | No (default: `5000`; use `5001` in practice) |
| `IB_ACCOUNT` | IBKR account ID | Yes (for most commands) |
| `BENZINGA_API_KEY` | Benzinga news REST API | Yes (for news/sentiment commands) |
| `DEFAULT_BROKER` | Broker adapter selector | No (default: `ibkr-rest`) |
| `DEFAULT_STRATEGY` | Default strategy | No (default: `rsi`) |
| `MAX_POSITION_PCT` | Max single-position size fraction | No (default: `0.05`) |
| `AGENT_MODE` | Agent execution mode | No (default: `autonomous`; recommend `supervised`) |
| `AGENT_LOG_PATH` | Path for JSONL agent log | No (default: `.trader/logs/agent.jsonl`) |
| `AGENT_PROFILE_PATH` | Path for portfolio profile JSON | No (default: `.trader/profile.json`) |
| `IBEAM_ACCOUNT` | ibeam — IBKR login username | Yes (for ibeam keepalive) |
| `IBEAM_PASSWORD` | ibeam — IBKR login password | Yes (for ibeam keepalive) |
| `IBEAM_GATEWAY_BASE_URL` | ibeam — gateway URL | No (default: `https://localhost:5001`) |
| `IBEAM_AUTHENTICATE` | ibeam — auto-login mode | No (default: `False`) |
| `IBEAM_KEY` | ibeam — base32 TOTP secret | Only if `IBEAM_AUTHENTICATE=True` |
| `FM_API_KEY` | Financial Modeling Prep | No (only for fundamental screeners) |
| `IBKR_USERNAME`, `IBKR_PASSWORD` | TWS adapter credentials | Only if `--broker ibkr-tws` |

## Webhooks
- **Incoming:** None.
- **Outgoing:** None.
