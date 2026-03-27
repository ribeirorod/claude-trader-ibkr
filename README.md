# Trader — Agent-First Trading CLI

A headless trading CLI for stocks, ETFs, and options via Interactive Brokers. Designed for AI agent consumption — all output is JSON, all commands are self-documenting via `--help`.

An autonomous portfolio conductor runs on a cron schedule, dispatching specialist agents that assess market conditions, manage risk, and execute trades — all without manual intervention.

---

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- IBKR account (paper or live) — [open one here](https://www.interactivebrokers.com)
- Docker (for the recommended setup) or Java 17+ (for running the gateway locally)
- [Benzinga API key](https://benzinga.com/apis) (for news/sentiment commands)

---

## Quick Start

### 1. Install

```bash
git clone <this-repo> && cd trader
uv sync
```

### 2. Configure

```bash
cp .env.example .env
```

Fill in the required values in `.env`:

| Variable | Description |
|----------|-------------|
| `IB_ACCOUNT` | Your IBKR account ID — paper starts with `DU`, live with `U` |
| `BENZINGA_API_KEY` | From [benzinga.com/apis](https://benzinga.com/apis) |
| `AGENT_MODE` | `supervised` (safe default) or `autonomous` |
| `CLAUDE_CODE_OAUTH_TOKEN` | For Docker agent — see [docs/docker-auth.md](docs/docker-auth.md) |
| `TELEGRAM_BOT_TOKEN` | Telegram bot for notifications and MFA relay |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID |

Everything else can stay as defaults to get started.

> **Start with `AGENT_MODE=supervised`** — the agent logs what it *would* do without placing real orders. Switch to `autonomous` once you're comfortable.

### 3. Start with Docker (recommended)

Download the IBKR Client Portal Gateway (one-time):

```bash
wget https://download2.interactivebrokers.com/portal/clientportal.gw.zip
unzip clientportal.gw.zip -d clientportal.gw
```

Start everything:

```bash
make docker-up
```

This builds and starts two containers:

| Container | Image | Purpose |
|-----------|-------|---------|
| `trader-ibkr-gateway-1` | `Dockerfile.gateway` (Eclipse Temurin JRE 17) | IBKR Client Portal REST API on port 5001 |
| `trader-trader-1` | `Dockerfile` (Python 3.12 + Node.js + Playwright) | FastAPI server, APScheduler crons, Telegram bot, Claude agent SDK |

### 4. Authenticate

Open **https://localhost:5001** in your browser and log in with your IBKR credentials (+ 2FA if enabled). Select **Paper Trading** or **Live Trading** at the login screen.

For headless / remote servers, SSH tunnel first:

```bash
ssh -L 5001:localhost:5001 user@your-server
# then open https://localhost:5001 locally
```

> **macOS:** If port 5001 is blocked, go to System Settings → General → AirDrop & Handoff → AirPlay Receiver → **Off**.

### 5. Session management

The gateway session expires after ~24h. The trader container keeps it alive automatically:

- **Healthcheck** (`ibkr-healthcheck` cron, every 5 min) — pings `/tickle` and checks auth status
- **Auto re-auth** (`ibkr-reauth.py`) — Playwright-based headless re-authentication triggered when the session expires. For live accounts, MFA codes are relayed via Telegram.

If auto re-auth fails, authenticate manually in the browser at `https://localhost:5001`.

> **Note:** `buying_power` from `trader account balance` reflects IBKR's margin capacity (~6.7x cash on some accounts). This system always uses `cash` only — never margin.

### 6. Verify connection

```bash
uv run trader account balance
```

Expected output:
```json
{
  "cash": 250000.0,
  "net_liquidation": 250000.0,
  "buying_power": 1666666.6,
  "currency": "USD"
}
```

### Local setup (without Docker)

If you prefer to run the gateway locally without Docker:

```bash
# Start the gateway (requires Java 17+)
cd clientportal.gw && ./bin/run.sh root/conf.yaml

# In another terminal, start the server
make server
```

---

## Command Reference

```bash
# Account
uv run trader account summary
uv run trader account balance
uv run trader account margin

# Quotes
uv run trader quote get AAPL MSFT TSLA
uv run trader quote chain AAPL --expiry 2026-04-17

# Orders
uv run trader orders buy AAPL 10 --type limit --price 195.00
uv run trader orders sell AAPL 10 --type market
uv run trader orders bracket AAPL 10 --entry 195 --take-profit 205 --stop-loss 190
uv run trader orders stop AAPL --price 190.00
uv run trader orders trailing-stop AAPL --trail-percent 2.5
uv run trader orders take-profit AAPL --price 210.00
uv run trader orders list --status open
uv run trader orders cancel <order-id>
uv run trader orders modify <order-id> --price 196.00

# Positions
uv run trader positions list
uv run trader positions close AAPL
uv run trader positions pnl

# News
uv run trader news latest --tickers AAPL MSFT --limit 10
uv run trader news sentiment AAPL --lookback 24h

# Strategies
uv run trader strategies run AAPL --strategy rsi
uv run trader strategies signals --tickers AAPL MSFT TSLA --strategy macd
uv run trader strategies backtest AAPL --strategy rsi --from 2025-01-01
uv run trader strategies optimize AAPL --strategy rsi
```

All commands support `--help` for full options.

---

## Autonomous Agent

The portfolio conductor runs on a cron schedule and dispatches specialist agents. All times are CET.

| Schedule | Slot | What runs |
|----------|------|-----------|
| Weekdays 8:03am | eu-pre-market | calendar gate → geo scan → news analyst → risk-monitor → portfolio-health → opportunity-finder (EU) → order-alert-manager |
| Weekdays 9am–3pm hourly | eu-market | risk-monitor → portfolio-health → opportunity-finder (EU + US pre-market) if stale |
| Weekdays 3:03pm | eu-us-overlap | full dispatch — both EU and US universes, highest liquidity window |
| Weekdays 5–9pm hourly | us-market | calendar gate → geo scan → news analyst → risk-monitor → portfolio-health → opportunity-finder (US) if stale |
| Sundays 6pm | weekly | market-top-detector → sector-analyst → market-news-analyst → portfolio-health → strategy-optimizer → performance review |
| 1st Sunday of month | monthly | strategy-optimizer → system-improver (decision quality audit + self-improvement) |

Logs: `.trader/logs/agent.jsonl` — every decision, intent, and order.
Snapshots: `.trader/logs/portfolio_evolution.jsonl` — timestamped NLV/position state on every run.

**Guardrails (enforced on every proposed trade):**
- Never uses margin — all sizing uses `cash`, never `buying_power`
- Cash floor: no new buys if cash < 10% of net liquidation (`CASH_FLOOR_BLOCK`)
- Single position cap: configurable in `profile.json` (default 5% NLV)
- Max 3 new positions per day
- `risk_mode=ELEVATED` (2+ high-impact calendar events): position sizes halved, no new entries

Edit `.trader/profile.json` to adjust risk tolerance, preferred sectors, and position limits.

---

## Workflow Diagram

![Autonomous Portfolio Conductor Workflow](docs/assets/workflow.svg)

---

## Paper vs Live

Select **Paper Trading** or **Live Trading** at the gateway login screen (`https://localhost:5001`). No code or config change needed.

---

## Development

### Running locally

```bash
make server          # start FastAPI + scheduler + Telegram polling
make kill            # stop it
```

Or directly: `uv run trader-server`

### Testing

```bash
make test
```

> **Always use `make test` or `uv run python -m pytest`** — never bare `pytest`.
> The system Homebrew `pytest` runs on Python 3.12 and can't see the packages in the uv venv (Python 3.10), causing all server tests to fail with `ModuleNotFoundError`.

### Docker

```bash
make docker-up              # build and start gateway + trader
make docker-down            # stop and remove containers
make docker-status          # show container health
make docker-logs            # tail trader logs
make docker-gateway-logs    # tail gateway logs
make docker-reauth          # manually trigger Playwright re-auth
```

**Rebuilding only the trader** (preserves gateway auth session):

```bash
docker compose build trader && docker compose up -d --no-deps trader
```

**Architecture:**

```
┌─────────────────────────────────────────────────────────┐
│  docker compose                                         │
│                                                         │
│  ┌─────────────────┐    ┌────────────────────────────┐  │
│  │  ibkr-gateway    │    │  trader                    │  │
│  │  JRE 17          │◄───│  Python 3.12 + Node.js    │  │
│  │  Port 5001       │    │  Port 9090                 │  │
│  │                  │    │                            │  │
│  │  Client Portal   │    │  FastAPI server            │  │
│  │  REST API        │    │  APScheduler crons         │  │
│  │                  │    │  Telegram bot              │  │
│  └─────────────────┘    │  Claude agent SDK          │  │
│         ▲                │  Playwright (reauth)       │  │
│         │                └────────────────────────────┘  │
│    :5001 exposed                    │                    │
│    for browser auth           :9090 health endpoint      │
└─────────────────────────────────────────────────────────┘
```

**Volumes:**
- `trader-data` → `/app/.trader` — logs, pipeline state, universe cache, profiles
- `claude-auth` → `/home/trader/.claude` — Claude SDK auth state

See [docs/docker-auth.md](docs/docker-auth.md) for Claude OAuth token setup.

---

## Common Issues

**`ConnectTimeout`** — Gateway is not running. Run `make docker-up` or start it manually.

**`not authenticated`** — Session expired. Open `https://localhost:5001` and log in again. The healthcheck cron will keep it alive after that.

**`Address already in use` (port 5001)** — On macOS, disable AirPlay Receiver in System Settings → General → AirDrop & Handoff.

**`No open position for AAPL`** — You don't hold a position; buy first before closing or setting stops.

**Agent places no orders** — Check `AGENT_MODE` in `.env`. If `supervised`, it logs intent only. Check `.trader/logs/agent.jsonl` for `CASH_FLOOR_BLOCK` or guardrail rejections.

**Scanner returns 0 results for EU/ETF/options** — Check `uv run trader universe refresh --market all` output for `scan_errors`. The IBKR scanner requires specific exchange location codes (e.g., `STK.EU.IBIS`, not `STK.EU.MAJOR`).

**`Not logged in` in Telegram** — Claude OAuth token expired. Re-run `claude setup-token` on the host, update `.env`, then `docker compose up -d trader`. See [docs/docker-auth.md](docs/docker-auth.md).
