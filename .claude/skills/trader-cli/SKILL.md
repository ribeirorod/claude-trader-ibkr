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
# Strategies: rsi, macd, ma_cross, bnf
trader strategies run     AAPL --strategy rsi [--interval 1d] [--lookback 90d]
trader strategies signals  --tickers AAPL,MSFT --strategy rsi [--with-news]
trader strategies backtest AAPL --strategy rsi [--from 2025-01-01]
trader strategies optimize AAPL --strategy rsi [--metric sharpe|returns|win_rate]
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
