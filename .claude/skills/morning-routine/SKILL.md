---
name: morning-routine
description: Use when the user wants to run their daily pre-market workflow — a structured morning brief covering economic risk, market health, geopolitical events, news digest, sentiment scores, strategy signals, portfolio review, open orders, and trade decisions.
---

# Morning Routine

## Overview

Orchestrates a complete pre-market workflow before the US market open (9:30 AM ET). Invokes multiple skills and trader CLI commands in a defined sequence, then synthesizes findings into a structured morning brief with market regime, top opportunities, risk flags, and prioritized action items.

**Total time:** ~10-15 minutes. Run between 8:00-9:15 AM ET for maximum value.

## When to Use

- "Run my morning routine"
- "Give me the pre-market brief"
- "Morning check before open"
- Any session start where you want a full situational awareness update

## Dependencies (Other Skills)

This skill orchestrates the following skills — they must be available:

| Skill | Purpose |
|-------|---------|
| `economic-calendar-fetcher` | High-impact events today/tomorrow |
| `sector-analyst` | Market health via SPY/QQQ/IWM signals |
| `geopolitical-influence` | Overnight geopolitical event scan |

All market data comes from the trader CLI directly.

## Required Setup

Before running, confirm:
1. IBKR Client Portal Gateway is running on port 5001 and browser-authenticated
2. `.env` has `BENZINGA_API_KEY` set
3. Your **watchlist** is defined — ask the user if not already provided: "What tickers are on your watchlist today?"

## Workflow

---

### Step 1 — Economic Risk Check

Invoke the `economic-calendar-fetcher` skill for today and tomorrow.

Focus only on **High-impact events**. Key events to flag:
- FOMC rate decision or minutes
- CPI / PPI / PCE releases
- NFP (Non-Farm Payrolls)
- GDP revision
- Fed Chair speeches

**Decision gate:**
- If 2+ High-impact events today → set `risk_mode = ELEVATED`. Reduce position sizing, widen stops.
- If 0 High-impact events → set `risk_mode = NORMAL`.

Record: `economic_events[]`, `risk_mode`

---

### Step 2 — Market Health Check

Invoke the `sector-analyst` skill for the market indices: SPY, QQQ, IWM.

Assess:
- Trend direction (SPY above/below 50-day MA proxy via RSI momentum)
- Risk-on vs risk-off: QQQ vs IWM relative strength
- Breadth: are most sectors aligned or diverging?

Supplement with CLI signals:
```bash
uv run trader strategies signals --tickers SPY,QQQ,IWM --strategy rsi --with-news
uv run trader quotes get SPY QQQ IWM
```

**Market Regime Classification:**

| Regime | Criteria |
|--------|----------|
| Bull Trend | SPY RSI 45-65, QQQ outperforming, breadth positive |
| Cautious Bull | SPY RSI 40-50, mixed breadth, IWM lagging |
| Neutral / Choppy | SPY RSI 40-60 with no trend, mixed sector signals |
| Risk-Off | SPY RSI <40, VIX elevated, defensive sectors leading |
| Bear Pressure | SPY RSI <35, broad selling, QQQ underperforming |

Record: `market_regime`, `index_signals{SPY, QQQ, IWM}`

---

### Step 3 — Geopolitical Scan

Invoke the `geopolitical-influence` skill with a prompt focused on **overnight developments**.

Web search for: `"markets overnight" site:reuters.com OR site:bloomberg.com` and `"geopolitical risk" today site:reuters.com`

If a High-severity event is found:
- Add to `risk_flags[]`
- Note affected sectors
- Pre-stage hedge commands for Step 9

If no significant events: note "No material overnight geopolitical developments."

Record: `geo_events[]`, `affected_sectors[]`

---

### Step 4 — News Digest

Fetch latest headlines for all watchlist tickers:

```bash
uv run trader news latest --tickers WATCHLIST_TICKERS --limit 20
```

Parse the JSON output. For each headline:
- Flag any **earnings surprises**, **guidance changes**, **FDA approvals/rejections**, **analyst upgrades/downgrades**, **M&A**
- These are high-conviction catalysts that override technical signals

Record: `catalyst_flags{}` — map of ticker → catalyst type

---

### Step 5 — Sentiment Scores

Run sentiment for each watchlist ticker:

```bash
# Run for each ticker individually
uv run trader news sentiment TICKER --lookback 24h
```

Build a sentiment table:

| Ticker | Sentiment Score | Bias |
|--------|----------------|------|
| AAPL | +0.41 | Bullish |
| TSLA | -0.28 | Neutral-Bearish |
| NVDA | +0.67 | Strong Bullish |

Thresholds:
- ≥ +0.4 → **Bullish**
- +0.15 to +0.39 → **Neutral-Bullish**
- -0.14 to +0.14 → **Neutral**
- -0.15 to -0.39 → **Neutral-Bearish**
- ≤ -0.4 → **Bearish**

Record: `sentiment_table{}`

---

### Step 6 — Strategy Signals

Run RSI signals across the full watchlist with news overlay:

```bash
uv run trader strategies signals --tickers WATCHLIST_TICKERS --strategy rsi --with-news
```

Optionally also run MACD for confirmation on top opportunities:
```bash
uv run trader strategies signals --tickers TOP_3_TICKERS --strategy macd --with-news
```

For each ticker, capture:
- Signal: `buy` | `sell` | `hold` | `neutral`
- RSI value
- Confirmation from news sentiment (Step 5)

**Signal scoring** (for ranking opportunities):
- RSI buy signal + Bullish sentiment + No negative catalyst = **Strong Long** (+2)
- RSI buy signal + Neutral sentiment = **Moderate Long** (+1)
- RSI sell signal + Bearish sentiment + Negative catalyst = **Strong Short** (-2)
- Conflicting signals = **No Trade** (0)

Record: `signal_scores{}` — ranked list of tickers by score

---

### Step 7 — Portfolio Review

Fetch current holdings and P&L:

```bash
uv run trader positions list
uv run trader positions pnl
```

For each open position:
- Is it in the affected sectors from Step 3 (geopolitical)?
- Is there a negative catalyst from Step 4?
- Is the RSI signal now sell/bearish (Step 6)?

Flag positions that need attention:
- **Protect** — add or tighten stop on positions with ≥2 bearish indicators
- **Watch** — one bearish indicator, monitor during session
- **Hold** — no bearish indicators, maintain

Record: `position_flags{}`, `unrealized_pnl`, `realized_pnl`

---

### Step 8 — Open Orders Check

```bash
uv run trader orders list --status open
```

Review all pending orders:
- Any limit orders from yesterday that are now outside a reasonable range?
- Any stops that need adjusting based on today's market regime?
- Any orders conflicting with today's new thesis?

Flag stale orders for cancellation. Provide cancel commands if needed:
```bash
uv run trader orders cancel ORDER_ID
```

Record: `open_orders[]`, `stale_order_ids[]`

---

### Step 9 — Decision Synthesis

Aggregate all inputs into the morning brief.

**Trade decision logic:**

```
IF risk_mode = ELEVATED AND market_regime in [Risk-Off, Bear Pressure]:
  → Reduce new trade sizing by 50%, prioritize protecting existing positions

IF signal_score >= +2 AND market_regime in [Bull Trend, Cautious Bull]:
  → Green light for long entries on top-scored tickers

IF position has ≥2 bearish flags (geopolitical + sentiment + signal):
  → Recommend stop tightening or close consideration

IF geo_event.severity = High:
  → Confirm hedge in place before any new longs
```

**Action Item categories:**
1. **Must-do before open** — stop adjustments on flagged positions, cancel stale orders
2. **Trade opportunities** — ranked by signal score, entry timing
3. **Watch list** — tickers to monitor for intraday confirmation
4. **Deferred** — good signals but wait for regime confirmation

---

## Output: Morning Brief

```
╔══════════════════════════════════════════════════════╗
║  MORNING BRIEF — {date} {time} ET                    ║
╚══════════════════════════════════════════════════════╝

MARKET REGIME:  [Bull Trend / Cautious Bull / Neutral / Risk-Off / Bear Pressure]
RISK MODE:      [NORMAL / ELEVATED]

─── ECONOMIC CALENDAR ─────────────────────────────────
  High-impact today:   [event list or "None"]
  High-impact tomorrow:[event list or "None"]

─── INDEX SIGNALS ──────────────────────────────────────
  SPY:  RSI XX  Signal: [buy/hold/sell]
  QQQ:  RSI XX  Signal: [buy/hold/sell]
  IWM:  RSI XX  Signal: [buy/hold/sell]

─── GEOPOLITICAL ───────────────────────────────────────
  [Event summary or "No material overnight developments"]
  Affected sectors: [list or "None"]

─── WATCHLIST SIGNALS ──────────────────────────────────
  Ticker  | Sentiment | RSI  | Signal       | Score
  --------|-----------|------|--------------|------
  NVDA    | +0.67     | 38   | Strong Long  | +2
  AAPL    | +0.41     | 52   | Moderate Long| +1
  TSLA    | -0.28     | 61   | No Trade     |  0
  [...]

─── PORTFOLIO STATUS ───────────────────────────────────
  Unrealized P&L: $X,XXX  |  Realized P&L: $X,XXX
  Flagged positions:
    ⚠ TICKER — [reason: geopolitical exposure / bearish signal / catalyst]
    ✓ TICKER — Hold

─── OPEN ORDERS ────────────────────────────────────────
  [order list or "No open orders"]
  Stale orders to cancel: [list or "None"]

─── ACTION ITEMS ───────────────────────────────────────
  BEFORE OPEN (must-do):
    1. [e.g. Tighten stop on TSLA: uv run trader orders stop TSLA --price XXX]
    2. [e.g. Cancel stale limit ORDER_ID: uv run trader orders cancel XXXXX]

  TRADE OPPORTUNITIES:
    1. NVDA — Long setup. RSI 38, sentiment +0.67, no negative catalyst.
       Entry: uv run trader orders buy NVDA 10 --type limit --price XXX
       Stop:  uv run trader orders stop NVDA --price XXX

  WATCH (wait for confirmation):
    1. [ticker + what to watch for]

  DEFERRED:
    1. [ticker + reason for deferral]
```

## Quick Reference

| Step | Skill / Command |
|------|----------------|
| Economic events | `economic-calendar-fetcher` skill |
| Market health | `sector-analyst` skill on SPY/QQQ/IWM |
| Geopolitical scan | `geopolitical-influence` skill |
| News digest | `uv run trader news latest --tickers WATCHLIST --limit 20` |
| Sentiment | `uv run trader news sentiment TICKER --lookback 24h` |
| Signals | `uv run trader strategies signals --tickers WATCHLIST --strategy rsi --with-news` |
| Portfolio | `uv run trader positions list && uv run trader positions pnl` |
| Open orders | `uv run trader orders list --status open` |

## Common Mistakes

- **Running without a watchlist** — ask the user for their watchlist before starting; don't assume it's unchanged from yesterday.
- **Skipping the economic calendar** — a surprise CPI print can invalidate all technical signals. Step 1 is not optional.
- **Recommending trades during elevated risk mode** — in ELEVATED risk mode, default to protecting existing positions before adding new ones.
- **Acting on signals that conflict with regime** — a RSI buy signal in a Bear Pressure regime is a low-confidence setup. Note it but don't execute.
- **Forgetting stale orders** — old limit orders from prior sessions can execute at bad prices if not reviewed.
- **Issuing commands without user confirmation** — the morning brief is a recommendation document. Always present the full action list and wait for user approval before running any order commands.
- **Watchlist sentiment lookback** — use `--lookback 24h` for the morning routine (overnight news). Use `--lookback 7d` only for longer trend analysis.
