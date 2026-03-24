---
name: options-strategy-advisor
description: Use when the user wants to analyze, simulate, or execute an options strategy — covered calls, protective puts, spreads, iron condors, straddles, earnings plays — or needs Greeks analysis, P/L simulation, IV assessment, or position sizing for options trades.
---

# Options Strategy Advisor

## Overview

Analyzes and simulates options strategies using live IBKR data from the trader CLI. Prices options via Black-Scholes, calculates Greeks, simulates P/L at expiration, and generates paste-ready `trader orders` commands for execution.

**Data sources:**
- Live options chain → `trader quotes chain`
- Current stock price → `trader quotes get`
- Portfolio context → `trader positions list`
- News catalyst → `trader news sentiment`

**No FMP API. No external scripts. All math inline. All execution via `trader orders`.**

---

## CLI Integration

```bash
# Live options chain (use for IV and real bid/ask)
uv run trader quotes chain AAPL --expiry 2026-04-17 [--strike 200] [--right call|put]

# Current stock price
uv run trader quotes get AAPL

# Check existing options positions
uv run trader positions list

# News context for earnings/catalyst plays
uv run trader news sentiment AAPL --lookback 7d

# Buy/sell an option
uv run trader orders buy  AAPL 1 --contract-type option --expiry 2026-04-17 --strike 200 --right call
uv run trader orders sell AAPL 1 --contract-type option --expiry 2026-04-17 --strike 200 --right call

# Bracket around an existing stock position
uv run trader orders bracket AAPL 100 --entry 200 --take-profit 215 --stop-loss 190
```

---

## Supported Strategies

### Income
| # | Strategy | Setup | Max Profit | Max Loss |
|---|----------|-------|-----------|---------|
| 1 | Covered Call | Own stock + sell call | Premium + strike upside | Unlimited down |
| 2 | Cash-Secured Put | Sell put + hold cash | Premium | Strike − Premium |

### Protection
| # | Strategy | Setup | Max Profit | Max Loss |
|---|----------|-------|-----------|---------|
| 3 | Protective Put | Own stock + buy put | Unlimited | Strike diff + premium |
| 4 | Collar | Own stock + sell call + buy put | Strike diff + premium | Strike diff + premium |

### Directional Spreads
| # | Strategy | Setup | Max Profit | Max Loss |
|---|----------|-------|-----------|---------|
| 5 | Bull Call Spread | Buy lower call + sell higher call | Spread width − debit | Debit paid |
| 6 | Bear Put Spread | Buy higher put + sell lower put | Spread width − debit | Debit paid |
| 7 | Bull Put Spread | Sell higher put + buy lower put | Credit received | Spread width − credit |
| 8 | Bear Call Spread | Sell lower call + buy higher call | Credit received | Spread width − credit |

### Volatility
| # | Strategy | Setup | Profit When |
|---|----------|-------|-------------|
| 9 | Long Straddle | Buy ATM call + ATM put | Big move either direction |
| 10 | Long Strangle | Buy OTM call + OTM put | Bigger move, cheaper cost |
| 11 | Short Straddle | Sell ATM call + ATM put | No movement (unlimited risk) |
| 12 | Short Strangle | Sell OTM call + OTM put | Range-bound |
| 13 | Iron Condor | Bull put spread + bear call spread | Range-bound |
| 14 | Iron Butterfly | Sell ATM straddle + buy OTM strangle | Tight range |

### Time-Based
| # | Strategy | Setup |
|---|----------|-------|
| 15 | Calendar Spread | Sell near-term option + buy longer-term same strike |
| 16 | Diagonal Spread | Calendar spread with different strikes |

---

## Analysis Workflow

### Step 1 — Gather Data

```bash
# 1. Current stock price
uv run trader quotes get AAPL

# 2. Live options chain around strikes of interest
uv run trader quotes chain AAPL --expiry 2026-04-17 --right call
uv run trader quotes chain AAPL --expiry 2026-04-17 --right put

# 3. Check existing positions
uv run trader positions list
```

Extract from chain output: `bid`, `ask`, `strike`, `expiry`, `implied_vol` (if provided), `delta`.

### Step 2 — Determine Volatility

**IV from chain (preferred):** Use mid-price from live chain and back-solve Black-Scholes. If `implied_vol` field exists in chain output, use it directly.

**HV fallback (if chain unavailable):**
```python
import numpy as np
# prices = array of daily close prices (90 days)
returns = np.log(np.array(prices[1:]) / np.array(prices[:-1]))
HV = returns.std() * np.sqrt(252)  # annualized
```

**IV guidance:**
- IV > HV significantly → options expensive → favor selling premium
- IV < HV significantly → options cheap → favor buying options
- Check `trader news sentiment` — high-impact upcoming events inflate IV

### Step 3 — Price with Black-Scholes

```python
from scipy.stats import norm
import numpy as np

def bs(S, K, T, r, sigma, right, q=0):
    """S=stock, K=strike, T=years to expiry, r=rate, sigma=IV, right=call|put"""
    d1 = (np.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)
    if right == 'call':
        price = S*np.exp(-q*T)*norm.cdf(d1) - K*np.exp(-r*T)*norm.cdf(d2)
    else:
        price = K*np.exp(-r*T)*norm.cdf(-d2) - S*np.exp(-q*T)*norm.cdf(-d1)
    return price
```

Use T = days_to_expiry / 365. Use r ≈ 0.045 (current ~4.5% short rate).

### Step 4 — Calculate Greeks

```python
def greeks(S, K, T, r, sigma, right, q=0):
    d1 = (np.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)
    delta = np.exp(-q*T) * (norm.cdf(d1) if right=='call' else norm.cdf(d1)-1)
    gamma = np.exp(-q*T) * norm.pdf(d1) / (S * sigma * np.sqrt(T))
    theta = ((-S*norm.pdf(d1)*sigma*np.exp(-q*T)/(2*np.sqrt(T))
              - r*K*np.exp(-r*T)*norm.cdf(d2 if right=='call' else -d2)) / 365)
    vega  = S * np.exp(-q*T) * norm.pdf(d1) * np.sqrt(T) / 100
    return {"delta": delta, "gamma": gamma, "theta": theta, "vega": vega}
```

For multi-leg strategies, sum Greeks across all legs (×contracts ×direction).

**Greeks cheat sheet:**

| Greek | Meaning | Rule of thumb |
|-------|---------|---------------|
| Delta | $ gain per +$1 stock | ATM ≈ 0.50, deep ITM ≈ 1.0 |
| Gamma | Delta change per +$1 | High near expiry, near ATM |
| Theta | $ lost per day | Negative for buyers, positive for sellers |
| Vega | $ gain per +1% IV | Positive for buyers, negative for sellers |

### Step 5 — Simulate P/L at Expiration

For a price range ±30% around current:
```python
price_range = np.linspace(S * 0.70, S * 1.30, 100)
pnl = []
for sp in price_range:
    leg_pnl = 0
    for leg in strategy_legs:
        intrinsic = max(0, sp - leg['strike']) if leg['right']=='call' else max(0, leg['strike'] - sp)
        if leg['position'] == 'long':
            leg_pnl += (intrinsic - leg['premium_paid']) * 100 * leg['contracts']
        else:
            leg_pnl += (leg['premium_received'] - intrinsic) * 100 * leg['contracts']
    pnl.append(leg_pnl)
```

Report: **max profit**, **max loss**, **breakeven(s)**, **probability of profit** (% of range above 0).

### Step 6 — Earnings / Catalyst Check

```bash
uv run trader news sentiment AAPL --lookback 7d
```

If earnings are imminent:
- **IV crush warning**: IV typically drops 30-50% after earnings. Long premium strategies (straddle, calls) suffer even if the stock moves as expected.
- **Implied move**: `IM = ATM_straddle_price / stock_price` — if actual move > IM, long straddle wins.
- **Preferred plays**: Short iron condor (collect elevated IV, profit from crush); long straddle only if expecting move > implied.

### Step 7 — Generate Recommendation

Output format:

```
OPTIONS ANALYSIS: [Strategy] on [TICKER]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SETUP
  Strategy:     Bull Call Spread
  Expiry:       2026-04-17 (38 DTE)
  Legs:         Long $200 call @ $5.20 mid
                Short $210 call @ $2.10 mid
  Net Debit:    $3.10 / share  ($310 per spread)
  Contracts:    2

PROFIT / LOSS
  Max Profit:   $1,380 (stock at $210+)
  Max Loss:     -$620 (stock at $200−)
  Breakeven:    $203.10
  Risk/Reward:  2.2 : 1

GREEKS (position total)
  Delta: +0.38  Gamma: +0.04  Theta: -$4/day  Vega: +$12/1%

VOLATILITY
  HV (90d): 28%  |  IV (chain): 32%  → Options slightly rich
  IV crush risk: Moderate (earnings in 22 days)

RECOMMENDATION
  ENTER if: Bullish to $210, willing to cap upside, IV stable
  AVOID if: Earnings in <7 days, or very bullish (buy call outright instead)
  Target exit: 50% profit ($155/spread) or 21 DTE

COMMANDS
  # Entry
  uv run trader orders buy  AAPL 2 --contract-type option --expiry 2026-04-17 --strike 200 --right call
  uv run trader orders sell AAPL 2 --contract-type option --expiry 2026-04-17 --strike 210 --right call

  # Exit (when target hit)
  uv run trader orders sell AAPL 2 --contract-type option --expiry 2026-04-17 --strike 200 --right call
  uv run trader orders buy  AAPL 2 --contract-type option --expiry 2026-04-17 --strike 210 --right call
```

---

## Position Sizing

```
Account size: $50,000
Risk per trade: 2% = $1,000

Debit spread (Bull Call):
  Max loss = debit × 100 × contracts
  Contracts = floor($1,000 / ($3.10 × 100)) = 3

Credit spread (Iron Condor):
  Max loss = (spread width - credit) × 100 × contracts
  Contracts = floor($1,000 / ($3.00 × 100)) = 3

Naked put:
  Max loss = (strike - premium) × 100 × contracts
  → Size conservatively; use 1-2% risk max
```

---

## Exit Rules by Strategy

| Strategy | Profit target | Stop loss | Time exit |
|----------|--------------|-----------|-----------|
| Debit spread | 50% of max profit | 2× debit | 21 DTE, close or roll |
| Credit spread / Iron Condor | 50% of credit | 2× credit received | 21 DTE |
| Long straddle/strangle | Close when move ≥ breakeven | Theta drain >50% of premium | 7 DTE |
| Covered call | Let expire or buy back at 10-20% of sold premium | — | 7-10 DTE, roll |
| Protective put | Exercise or sell put if stock falls to strike | Let expire if stock holds | — |

---

## Common Mistakes

- **Ignoring IV crush before earnings** — buying straddles when IV is already elevated loses even with a large move.
- **Using theoretical price without checking the chain** — always verify mid-price from `trader quotes chain` before entering.
- **Sizing too large** — options can go to zero; keep max loss ≤2% of account per trade.
- **Expiry too short** — <21 DTE gamma risk accelerates; spreads can blow through quickly.
- **Wrong `--right` flag** — double-check `call` vs `put` in every `trader orders` command.
- **Legging into spreads** — enter both legs with separate commands quickly; don't leave one leg open.
- **Not confirming before execution** — always present full command plan and await confirmation.

---

---

## Pullback Strategy Integration

The `pullback` strategy (`trader/strategies/pullback.py`) generates directional signals specifically designed for options trades. When invoked with `--with-options`, it automatically recommends a contract.

### Quick workflow — pullback-driven options trade

```bash
# 1. Check for pullback signals with options recommendation
uv run trader strategies signals --tickers SPY,QQQ,AAPL --strategy pullback --with-options --expiry 2026-04-17

# 2. Output includes an "options" block with strike, delta, qty, max_risk
# 3. If recommendation looks good, execute:
uv run trader orders buy SPY 2 --contract-type option --expiry 2026-04-17 --strike 420 --right put
```

### When to use pullback vs manual options analysis

| Scenario | Use |
|----------|-----|
| Automated signal → defined-risk directional trade | `pullback --with-options` (fast, systematic) |
| Earnings play, IV crush, multi-leg spread | This skill (manual options-strategy-advisor) |
| Hedging existing equity position | This skill (protective put / collar) |
| Income generation on held stock | This skill (covered call) |

### Pullback signal → options strategy mapping

| Signal | Default recommendation | When to upgrade |
|--------|----------------------|-----------------|
| -1 (bearish pullback) | Buy put (1 ATR OTM, 30-45 DTE) | High IV → bear put spread instead (sell further OTM put to reduce cost) |
| +1 (bullish pullback) | Buy call (1 ATR OTM, 30-45 DTE) | High IV → bull call spread instead |
| -1 (high conviction + low IV) | Buy put outright | IV < HV → cheap premium, outright is efficient |
| -1 (high conviction + high IV) | Bear put spread | IV > HV → spread offsets inflated premium |

To upgrade from a single leg to a spread, use this skill's full analysis workflow (Steps 1-7) after getting the initial pullback signal.

---

## See Also

- `trader-cli` skill — full CLI reference for orders, quotes, positions
- `trader-strategies` skill — pullback strategy details, options_selector module
- `portfolio-manager` skill — to check how options positions affect overall portfolio Greeks
- `position-sizer` skill — for equity position sizing if converting an options trade to stock
