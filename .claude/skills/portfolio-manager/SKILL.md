---
name: portfolio-manager
description: Use when the user wants a comprehensive portfolio review — allocation analysis, diversification health, risk metrics, rebalancing recommendations, or position-level trim/add/hold/sell action plans.
---

# Portfolio Manager

## Overview

Performs a full multi-dimensional portfolio analysis using live data from the trader CLI. Covers asset allocation (sector, cap, geography), diversification assessment, risk metrics (beta, volatility, drawdown), and generates prioritized rebalancing recommendations with specific trade actions.

## When to Use

- "Review my portfolio"
- "Am I over-concentrated anywhere?"
- "What should I rebalance?"
- "Give me a risk breakdown of my holdings"
- "Which positions should I trim or add to?"

## CLI Integration

All data comes from the trader CLI. No external broker API calls.

```bash
# Snapshot your holdings
uv run trader positions list

# Aggregate P&L totals
uv run trader positions pnl

# Account equity and buying power
uv run trader account summary

# Open orders that affect available capital
uv run trader orders list --status open

# Close a position (after confirmation)
uv run trader positions close TICKER

# News sentiment on a position you're evaluating
uv run trader news sentiment TICKER --lookback 7d

# Strategy signals on current holdings
uv run trader strategies signals --tickers TICKER1,TICKER2 --strategy rsi --with-news
```

## Workflow

### Step 1 — Fetch Live Data

Run these in sequence, capture JSON output:

```bash
uv run trader positions list    # → positions[]
uv run trader positions pnl     # → unrealized_pnl, realized_pnl
uv run trader account summary   # → net_liquidation, buying_power, equity
uv run trader orders list --status open  # → pending orders affecting capital
```

### Step 2 — Build Allocation Map

From `positions list` output, compute:

- **By sector** — group tickers into Technology, Healthcare, Energy, Financials, Consumer, Industrials, Materials, Utilities, Real Estate, Communication
- **By market cap** — Large (>$10B), Mid ($2-10B), Small (<$2B)
- **By geography** — US domestic, International developed, Emerging markets
- **By asset class** — Equities, ETFs, Options, Fixed income

Calculate each bucket as `% of net_liquidation`.

### Step 3 — Diversification Assessment

Flag concentration risks:

| Metric | Warning Threshold | Action |
|--------|-------------------|--------|
| Single position | >15% of portfolio | Consider trimming |
| Single sector | >35% of portfolio | Review correlation |
| Top 3 positions | >50% of portfolio | Reduce concentration |
| Cash at floor | <10% of portfolio | Block new buys immediately |
| HHI (sum of squares of weights) | >0.15 | High concentration risk |

Compute pairwise correlation risk for largest 5 positions by checking whether they share sector, geography, and macro drivers.

### Step 4 — Risk Metrics

For each position and the overall portfolio:

- **Beta estimate** — use sector ETF proxies (XLK=1.3, XLE=0.9, XLU=0.5, etc.) weighted by allocation
- **Unrealized drawdown** — from `positions list` `avg_cost` vs `market_price`
- **Position-level P&L ranking** — sort by `unrealized_pnl` desc
- **Tail risk flags** — any single position down >20% from cost → flag for review

### Step 5 — Position-Level Analysis

For each of the top 5 positions by market value, run:

```bash
uv run trader news sentiment TICKER --lookback 7d
uv run trader strategies signals --tickers TICKER --strategy rsi --with-news
```

Assess:
- Sentiment score: < -0.3 = bearish, > 0.3 = bullish
- RSI signal: overbought (>70) / oversold (<30)
- Combine into a **conviction rating**: Strong Hold / Hold / Trim / Sell

### Step 6 — Rebalancing Recommendations

Prioritize actions in this order:

1. **Immediate** — positions flagged for tail risk (>20% drawdown) or extreme concentration (>20% single position)
2. **Near-term** — sector rebalancing to target weights (typically 5-25% per sector)
3. **Opportunistic** — add to underweight positions with bullish signals
4. **Fine-tuning** — minor trim/add to approach target allocation

For each recommended trade, output:

```
Action:  TRIM | ADD | CLOSE | HOLD
Ticker:  AAPL
Current: 22% of portfolio ($44,000)
Target:  15% of portfolio ($30,000)
Trade:   Sell ~$14,000 (~32 shares at ~$437)
Command: uv run trader orders sell AAPL 32 --type limit --price <current_ask>
Reason:  Over-concentration; RSI overbought (74); sector (XLK) at 38% vs 25% target
```

### Step 7 — Generate Report

Produce a structured report:

```
PORTFOLIO ANALYSIS REPORT — {date}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SUMMARY
  Net Liquidation: $XXX,XXX
  Unrealized P&L:  $X,XXX (+X.X%)
  Realized P&L:    $X,XXX
  Open Positions:  N
  Portfolio Beta:  X.X

ALLOCATION HEALTH
  Sector breakdown (table)
  Cap breakdown (table)
  Concentration flags (list)

TOP POSITION ANALYSIS
  Per-ticker: allocation%, cost, current, unrealized%, sentiment, RSI signal, verdict

REBALANCING ACTIONS (prioritized)
  1. [Immediate] ...
  2. [Near-term] ...
  3. [Opportunistic] ...

COMMANDS TO EXECUTE
  # Paste-ready trader CLI commands
```

## Quick Reference

| Goal | Command |
|------|---------|
| Fetch all positions | `uv run trader positions list` |
| P&L totals | `uv run trader positions pnl` |
| Account equity | `uv run trader account summary` |
| Sentiment check | `uv run trader news sentiment TICKER --lookback 7d` |
| Technical signal | `uv run trader strategies signals --tickers TICKER --strategy rsi --with-news` |
| Close position | `uv run trader positions close TICKER` |
| Trim with limit | `uv run trader orders sell TICKER QTY --type limit --price PRICE` |

### Step 8 — Portfolio Evolution Report (optional, on request)

Read the evolution log written by the conductor on every run:

```bash
cat .trader/logs/portfolio_evolution.jsonl
```

Each line is a timestamped snapshot with `net_liquidation`, `cash_pct`, and full `positions[]` with `pct_of_nlv`.

Produce:

```
PORTFOLIO EVOLUTION — {start_date} to {end_date}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

NLV TREND
  {date}  $XXX,XXX   (change from prior: +X.X%)
  {date}  $XXX,XXX   ...

CASH RESERVE TREND
  Avg cash%: XX%    Min: XX% ({date})    Max: XX% ({date})
  ⚠ Days below 10% floor: N

POSITION SIZE COMPLIANCE
  Max single position seen: X.X% ({ticker}, {date})
  Positions ever > 3%: list of [ticker, date, pct]
  ✓ Compliant / ⚠ Violations found

TOP MOVERS (since first snapshot)
  Gainers:  TICKER +XX% unrealized_pnl_pct change
  Losers:   TICKER -XX% unrealized_pnl_pct change

ALLOCATION DRIFT SUMMARY
  Sector weights at start vs. end (table)
```

## Common Mistakes

- **Fetching stale data** — always re-run `positions list` at the start; don't rely on remembered state.
- **Ignoring open orders** — check `orders list --status open`; pending buy orders reduce effective buying power.
- **Over-rebalancing** — recommend no more than 3-5 trades per session; avoid excessive churn.
- **Closing vs. trimming** — use `positions close TICKER` only for full exit; use `orders sell TICKER QTY` for partial trim.
- **No confirmation before close** — always present the full trade plan and ask for user confirmation before issuing any close or sell command.
- **Missing cost basis** — use `avg_cost` from `positions list`, not spot price, for drawdown calculations.
