---
name: trader-cli
description: Use when running, testing, or automating the trader CLI tool — invoking commands, parsing output, placing orders, fetching quotes, or reading account/position data.
---

# Trader CLI

## Overview

Agent-first trading CLI. All commands output JSON to stdout; errors output `{"error": "...", "code": "..."}` and exit 1. Requires IBKR Client Portal Gateway running on port 5001.

## Invocation

```bash
uv run trader [--broker ibkr-rest|ibkr-tws] [--output json|table] COMMAND [ARGS]
```

Global options (before the command):
- `--broker` — default `ibkr-rest` (Client Portal Gateway). Use `ibkr-tws` for local TWS.
- `--output` — default `json`. Use for agent consumption.

## Commands Reference

### account
```bash
trader account summary       # full account snapshot
trader account balance       # cash, net liquidation, buying power
trader account margin        # initial/maintenance/available margin
```

### quotes
```bash
trader quotes get AAPL MSFT TSLA           # live quotes, multi-ticker
trader quotes chain AAPL --expiry 2026-04-17 [--strike 200] [--right call|put]
```

### positions
```bash
trader positions list        # open positions with market value and unrealized P&L
trader positions pnl         # aggregated unrealized + realized P&L totals
trader positions close AAPL  # market-order close entire position
```

### orders
```bash
# Buy / Sell
trader orders buy  AAPL 10
trader orders buy  AAPL 10 --type limit --price 195
trader orders sell AAPL 10 --type market

# Bracket
trader orders bracket AAPL 10 --entry 195 --take-profit 210 --stop-loss 185
# or via buy:
trader orders buy AAPL 10 --type bracket --price 195 --take-profit 210 --stop-loss 185

# Risk management on existing positions
trader orders stop          AAPL --price 185          # stop-loss
trader orders take-profit   AAPL --price 210          # take-profit limit
trader orders trailing-stop AAPL --trail-percent 2.5  # trailing stop (or --trail-amount 5.00)

# Order lifecycle
trader orders list [--status open|filled|cancelled|all]
trader orders modify ORDER_ID [--price 198] [--qty 5]
trader orders cancel ORDER_ID

# Options (add to buy/sell)
trader orders buy AAPL 1 --contract-type option --expiry 2026-04-17 --strike 200 --right call
```

### news
```bash
trader news latest --tickers AAPL,MSFT [--limit 10]
trader news sentiment AAPL [--lookback 24h|48h|7d]   # returns score -1.0..1.0
```

### strategies
```bash
# Strategies: rsi, macd, ma_cross, bnf, momentum, pullback
trader strategies run     AAPL --strategy rsi [--interval 1d] [--lookback 90d]
trader strategies signals  --tickers AAPL,MSFT --strategy rsi [--with-news]
trader strategies backtest AAPL --strategy rsi [--from 2025-01-01]
trader strategies optimize AAPL --strategy rsi [--metric sharpe|returns|win_rate]

# Pullback strategy with options overlay
trader strategies signals --tickers SPY --strategy pullback --with-options [--expiry 2026-04-17] [--account-value 50000]
```

## Quick Reference

| Goal | Command |
|------|---------|
| Check buying power | `trader account balance` |
| Live price | `trader quotes get AAPL` |
| Open positions | `trader positions list` |
| Total P&L | `trader positions pnl` |
| Buy market | `trader orders buy AAPL 10` |
| Buy limit | `trader orders buy AAPL 10 --type limit --price 195` |
| Bracket trade | `trader orders bracket AAPL 10 --entry 195 --take-profit 210 --stop-loss 185` |
| Protect position | `trader orders stop AAPL --price 185` |
| Latest news | `trader news latest --tickers AAPL` |
| Signal check | `trader strategies signals --tickers AAPL --strategy rsi` |
| Pullback + options | `trader strategies signals --tickers SPY --strategy pullback --with-options` |

## Gateway Session Management (ibeam)

The IBKR Client Portal Gateway requires active session maintenance. **ibeam** handles this automatically — it keeps the session alive via periodic `/tickle` pings and can optionally handle re-authentication headlessly via Selenium.

### Architecture

```
[launchd] → start-gateway.sh → uv run python ibeam_starter.py -m
                                       ↓
                          Starts Java clientportal.gw process
                          Tickles /v1/api/tickle every 60s
                          Health server on :5002
```

### Starting the Gateway

```bash
# Manual start (foreground, useful for debugging)
bash scripts/start-gateway.sh

# Managed by launchd (auto-starts at login, auto-restarts on crash)
launchctl load ~/Library/LaunchAgents/com.vibe.ibkr-gateway.plist
```

The launchd plist is at `~/Library/LaunchAgents/com.vibe.ibkr-gateway.plist`. It runs at login and restarts automatically.

### Session Health Check

```bash
# ibeam liveness (process running)
curl -s http://localhost:5002/livez

# ibeam readiness (gateway session authenticated)
curl -s http://localhost:5002/readyz

# Trader CLI check (end-to-end — also verifies gateway auth)
uv run trader account summary
```

**Response codes:**
- `200 OK` from `/readyz` → session active, ready for trading commands
- `503 Service Unavailable` from `/readyz` → session expired, needs re-authentication
- `ConnectionError` from `trader account summary` → gateway not running

### Authentication Modes

**Manual mode (default, `IBEAM_AUTHENTICATE=False`):**
- ibeam starts the gateway and maintains the session via tickle
- You authenticate once via browser (`https://localhost:5001`)
- Session lasts ~24h; repeat browser login when `/readyz` returns 503

**Automatic mode (`IBEAM_AUTHENTICATE=True`):**
- ibeam uses Selenium + Chrome to log in headlessly
- Requires `IBEAM_KEY` (base32 TOTP secret) for 2FA
- To enable: set in `.env`:
  ```
  IBEAM_AUTHENTICATE=True
  IBEAM_KEY=YOUR_BASE32_TOTP_SECRET
  ```
- Dependency: chromedriver installed at `/opt/homebrew/bin/chromedriver`

### Key `.env` Variables

| Variable | Value | Purpose |
|----------|-------|---------|
| `IBEAM_ACCOUNT` | `DUP391462` | IBKR account ID |
| `IBEAM_GATEWAY_BASE_URL` | `https://localhost:5001` | Gateway URL |
| `IBEAM_AUTHENTICATE` | `False` | Auto-login via Selenium |
| `IBEAM_CHROME_DRIVER_PATH` | `/opt/homebrew/bin/chromedriver` | Chromedriver for Selenium |
| `IBEAM_HEALTH_SERVER_PORT` | `5002` | ibeam health endpoint port |
| `IBEAM_LOG_LEVEL` | `WARNING` | Suppress info noise |
| `IB_PORT` | `5001` | Port for trader CLI to connect |

### Logs

```bash
# ibeam stdout (startup messages, tickle activity)
tail -f .trader/logs/ibeam-stdout.log

# ibeam stderr (errors, exceptions)
tail -f .trader/logs/ibeam-stderr.log

# Gateway Java process logs
tail -f clientportal.gw/root/logs/gateway.log
```

### Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `/readyz` → 503 | Session expired (~24h) | Re-authenticate in browser at `https://localhost:5001` |
| `ConnectionError` from CLI | Gateway not running | `bash scripts/start-gateway.sh` or check launchd |
| ibeam exiting immediately | `IBEAM_CHROME_DRIVER_PATH` not set | Check `.env` for the path |
| Port conflict on restart | Health server port clash | `IBEAM_HEALTH_SERVER_PORT=5002` (not 5001, which is the gateway) |
| `uv run ibeam` fails | No console script in venv | Use `uv run python .venv/lib/python3.10/site-packages/ibeam/ibeam_starter.py -m` |
| Selenium fails to start | chromedriver not installed | `brew install chromedriver` |

### Stopping the Gateway

```bash
# Stop launchd job (and ibeam process)
launchctl unload ~/Library/LaunchAgents/com.vibe.ibkr-gateway.plist

# Kill gateway Java process manually
pkill -f clientportal.gw
```

---

## Error Handling

All errors produce JSON on stdout and exit code 1:
```json
{"error": "Connection refused", "code": "ConnectionError"}
```

Parse with `jq .error` or check exit code before acting on output.

## Common Mistakes

- **Wrong port** — Gateway runs on HTTPS `5001`, not TWS `7497`. Set `IB_PORT=5001` in `.env`.
- **Auth not done** — Browser-auth the Client Portal Gateway before running any command.
- **Bracket via `buy`** — Use `--type bracket` with `--price`, `--take-profit`, `--stop-loss`. Or use the dedicated `bracket` subcommand.
- **Trailing stop qty** — `trailing-stop` reads qty from the open position automatically; no `--qty` needed.
- **News tickers format** — `--tickers` accepts comma-separated (`AAPL,MSFT`) or space-separated (quote the arg: `'AAPL MSFT'`).
- **`uv run ibeam` broken** — ibeam has no console script; use `uv run python .venv/.../ibeam_starter.py -m` or run `bash scripts/start-gateway.sh`.
- **Stop orders show `price: null`** — Display bug in adapter; price is set correctly at placement, confirm in `.trader/logs/agent.jsonl`.
- **Stop without open position** — `trader orders stop TICKER --price X` fails if position not yet filled. Use `--qty N` to pre-place: `trader orders stop TICKER --price X --qty N`.
