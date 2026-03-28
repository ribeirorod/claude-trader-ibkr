# Trader — Agent-First Trading CLI

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![CI](https://github.com/ribeirorod/claude-trader-ibkr/actions/workflows/ci.yml/badge.svg)](https://github.com/ribeirorod/claude-trader-ibkr/actions/workflows/ci.yml)

An autonomous trading bot for stocks, ETFs, and options via Interactive Brokers. Powered by Claude — specialist AI agents scan markets, assess risk, and execute trades on a cron schedule.

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

---

## Setup

### 1. Clone and configure

```bash
git clone https://github.com/ribeirorod/claude-trader-ibkr.git && cd claude-trader-ibkr
cp .env.example .env
```

Edit `.env`:

| Variable | Description |
|----------|-------------|
| `IB_ACCOUNT` | IBKR account ID (paper: `DU...`, live: `U...`) |
| `BENZINGA_API_KEY` | News/sentiment — [benzinga.com/apis](https://benzinga.com/apis) |
| `TELEGRAM_BOT_TOKEN` | Telegram bot for notifications + MFA relay |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID |
| `AGENT_MODE` | `supervised` (logs only) or `autonomous` (places orders) |

### 2. Set up Claude authentication

The trader container uses the Claude agent SDK. Generate an OAuth token on your host machine:

```bash
claude setup-token
```

This opens a browser and prints a token (`sk-ant-oat01-...`). Add it to `.env`:

```
CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-...
```

> Tokens expire ~48h. When the agent stops responding in Telegram, re-run `claude setup-token`, update `.env`, and run `docker compose up -d trader`.

### 3. Download the IBKR gateway (one-time)

```bash
wget https://download2.interactivebrokers.com/portal/clientportal.gw.zip
unzip clientportal.gw.zip -d clientportal.gw
```

### 4. Start

```bash
make docker-up
```

Then authenticate at **https://localhost:5001** in your browser. The bot keeps the session alive automatically via healthcheck pings and Playwright-based re-auth.

### 5. Verify

```bash
uv run trader account balance
```

---

## What it does

The portfolio conductor runs on a cron schedule (EU pre-market through US close) and dispatches specialist agents:

- **Opportunity finder** — scans IBKR market scanners (US, EU, ETF, options) + news sentiment
- **Risk monitor** — checks drawdowns, stop-loss triggers, macro risk
- **Portfolio health** — allocation drift, concentration, diversification
- **Strategy optimizer** — backtests and tunes strategy parameters

All output is JSON. All commands support `--help`. Logs go to `.trader/logs/agent.jsonl`.

**Guardrails:** No margin. Cash floor at 10% NLV. Single position capped at 5% NLV. Max 3 new positions/day. Position sizes halved during high-impact calendar events.

![Autonomous Portfolio Conductor Workflow](docs/assets/workflow.svg)

---

## CLI

```bash
uv run trader account balance
uv run trader quote get AAPL MSFT
uv run trader orders buy AAPL 10 --type limit --price 195.00
uv run trader orders bracket AAPL 10 --entry 195 --take-profit 205 --stop-loss 190
uv run trader positions list
uv run trader news sentiment AAPL --lookback 24h
uv run trader strategies signals --tickers AAPL MSFT --strategy macd
uv run trader universe refresh --market all
uv run trader pipeline discover && uv run trader pipeline analyze
```

---

## Development

```bash
uv sync --extra dev          # install deps
make test                    # run tests (always use make, not bare pytest)
make server                  # run locally without Docker
```

```bash
make docker-up               # build and start
make docker-logs             # tail trader logs
make docker-status           # container health
make docker-reauth           # force Playwright re-auth
```

Rebuild trader only (keeps gateway session): `docker compose build trader && docker compose up -d --no-deps trader`

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Use [Conventional Commits](https://www.conventionalcommits.org/) — releases are tagged automatically on merge to `main`.

## License

[MIT](LICENSE)
