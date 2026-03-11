---
name: position-sizer
description: Use when calculating how many shares to buy for a trade, sizing a position based on account risk, ATR volatility, or Kelly Criterion — and generating the final `trader orders buy` command.
---

# Position Sizer

## Overview

Calculates optimal share quantity for equity trades using account equity from `trader account balance` and live price from `trader quotes get`. Supports three sizing methods: Fixed Fractional (default), ATR-Based, and Kelly Criterion. Always outputs a ready-to-run `trader orders buy` command.

**Core principle:** Position sizing is about surviving losing streaks, not maximizing winners. Default to 1% account risk per trade. Round share counts DOWN. Never exceed 5% of portfolio in a single name.

## When to Use

- User asks "how many shares should I buy?"
- User provides a stop-loss price and wants risk-based sizing
- User wants volatility-adjusted position sizing (ATR method)
- User has win/loss stats and wants Kelly-optimal sizing
- User asks about position allocation or portfolio heat

## CLI Integration

```bash
# Step 1 — Get account equity and buying power
trader account balance

# Step 2 — Get current price (and ATR if using ATR method)
trader quotes get AAPL

# Step 3 — Get strategy signals for context (optional)
trader strategies run AAPL --strategy rsi

# Step 4 — Place the sized order
trader orders buy AAPL <QTY>
trader orders buy AAPL <QTY> --type limit --price <ENTRY>

# For bracket entry (entry + stop + target in one go):
trader orders bracket AAPL <QTY> --entry <PRICE> --stop-loss <STOP> --take-profit <TARGET>
```

Key fields from `trader account balance` output:
- `net_liquidation` — total account equity (use as sizing base)
- `buying_power` — must be >= position cost; hard constraint

## Workflow

### Step 1 — Gather inputs

Collect from user (or prompt if missing):
- Ticker, entry price, stop-loss price
- Sizing method (fixed-fractional / atr / kelly)
- Risk per trade (default: 1% of equity)

Fetch live data:
```bash
trader account balance   # → net_liquidation, buying_power
trader quotes get AAPL   # → last price, optionally atr_14
```

### Step 2 — Calculate shares

**Fixed Fractional (default)**
```
risk_dollars  = net_liquidation × risk_pct          # e.g. 0.01
stop_distance = entry_price − stop_price            # must be > 0
shares        = FLOOR(risk_dollars / stop_distance)
```

**ATR-Based**
```
atr_stop      = entry_price − (atr_multiplier × ATR_14)   # default multiplier = 2.0
stop_distance = entry_price − atr_stop
shares        = FLOOR(risk_dollars / stop_distance)
```
Use `atr_14` from `trader quotes get` output if available; otherwise ask user for ATR value.

**Kelly Criterion**
```
kelly_pct = win_rate − ((1 − win_rate) / avg_win_loss_ratio)
half_kelly = kelly_pct / 2          # always use half-Kelly
shares     = FLOOR((net_liquidation × half_kelly) / entry_price)
```
Requires user-supplied win rate and average win/loss ratio from historical performance.

### Step 3 — Apply constraints

Check all of these; use the most restrictive result:

| Constraint | Rule |
|------------|------|
| Max position size | shares × price ≤ net_liquidation × 0.05 |
| Buying power | shares × price ≤ buying_power |
| Minimum shares | If shares < 1, do not trade — risk too large for account |
| Portfolio heat | Sum of all open risk ≤ 6% of equity (check `trader positions list`) |

### Step 4 — Output recommendation

Present:
1. Method used and inputs
2. Calculated shares (post-constraint)
3. Dollar risk (shares × stop_distance)
4. Risk as % of equity
5. What constraint bound the result (if any)
6. Ready-to-run command

**Example output:**
```
Method: Fixed Fractional
Equity: $52,340   Risk: 1.0% = $523
Entry: $195.00    Stop: $188.50   Distance: $6.50
Shares: 80  →  Dollar risk: $520  (0.99% of equity)
Position cost: $15,600  (29.8% of buying power — OK)

Command:
trader orders bracket AAPL 80 --entry 195 --stop-loss 188.50 --take-profit 208
```

## Quick Reference

| Method | Required inputs | Best for |
|--------|----------------|----------|
| Fixed Fractional | entry, stop, risk% | Most trades |
| ATR-Based | entry, ATR multiplier | Volatile stocks, no obvious S/R stop |
| Kelly | win rate, W/L ratio | Systematic strategies with tracked stats |

## Common Mistakes

- **Using cash balance instead of net liquidation** — Always size off `net_liquidation`, not `cash_balance`.
- **Ignoring buying power** — A $100K equity account with $30K buying power (margin used) can still run out of room.
- **Rounding up** — Always FLOOR shares. Never round up; it silently increases risk.
- **Full Kelly** — Full Kelly is ruinous in drawdown. Always halve it.
- **No portfolio heat check** — A single well-sized trade is fine; six of them simultaneously can hit 6%+ portfolio heat. Check `trader positions list` first.
- **ATR from stale data** — Re-fetch `trader quotes get` on trade day; ATR from yesterday may not reflect today's gap.
