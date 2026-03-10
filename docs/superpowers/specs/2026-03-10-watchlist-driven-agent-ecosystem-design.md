# Watchlist-Driven Agent Ecosystem

**Date:** 2026-03-10
**Branch:** feature/trader-cli-rewrite
**Status:** Approved

---

## Problem

The trader CLI now has `scan`, `watchlist`, and `alerts` commands, but the agent/skill ecosystem does not use them. Screeners rebuild their universe from scratch on every run, strategy optimization only covers active holdings, alerts are not wired into the agent loop, and there is no agent that manages the lifecycle of open orders and alerts as a feedback loop.

---

## Design

### Core Principle

The watchlist is the **persistent candidate universe**. Screeners are writers (they add gems). The optimization and monitoring loop is the reader. Alerts are proposals — only the conductor executes.

### Flow

```
Screeners ──────────────► Watchlists (outputs/watchlists.json)
                                │
                    ┌───────────┴────────────┐
                    │                        │
          strategy-optimizer         opportunity-finder
          (bi-weekly baseline)       (depth decided by agent)
                    │                        │
                    └───────────┬────────────┘
                                ▼
                      order-alert-manager  ◄── trader alerts list
                      (new agent)          ◄── trader orders list
                                │
                                ▼
                         conductor
                         (decides + executes)
```

---

## Components

### 1. New Agent: `order-alert-manager`

A specialist the conductor dispatches alongside `risk-monitor` and `portfolio-health` on every run.

**Responsibilities:**
- Read all active IBKR alerts: `trader alerts list`
- Read all open orders: `trader orders list --status open`
- Receive incoming proposals from opportunity-finder, strategy-optimizer, and risk-monitor
- For each proposed alert: check if a duplicate already exists for that ticker/price → skip if so
- For each open order: check if signal has reversed → propose cancellation to conductor
- For each active alert that has triggered: propose a bracket entry order to conductor
- Return a structured, deduplicated action list — never executes directly

**Output format:**

```json
[
  {
    "action": "CREATE_ALERT",
    "ticker": "NVDA",
    "price": 891.50,
    "direction": "above",
    "name": "NVDA VCP pivot",
    "source": "opportunity-finder",
    "reason": "VCP breakout pivot. RSI 61, sentiment +0.65."
  },
  {
    "action": "PLACE_BRACKET",
    "ticker": "CRWD",
    "entry": 320.00,
    "stop": 298.00,
    "target": 365.00,
    "shares": 8,
    "source": "alert-triggered",
    "reason": "Alert triggered at pivot. Signal still valid (RSI 58, sentiment +0.4)."
  },
  {
    "action": "CANCEL_ORDER",
    "order_id": "12345",
    "ticker": "XLE",
    "reason": "MA cross reversed to downtrend since order was placed."
  },
  {
    "action": "NO_ACTION",
    "ticker": "AAPL",
    "reason": "Alert already active at $195.00. No change."
  }
]
```

The conductor reviews this list and makes final execution decisions.

---

### 2. `opportunity-finder` Agent — Updated Behavior

**Before scanning:**
1. Read JSONL log — when was the last watchlist-based signal run?
2. Check market regime (sector-analyst / stanley-druckenmiller) — has it shifted since last run?
3. **If watchlist is fresh AND regime unchanged:** read watchlist directly, run signals on those tickers. Skip full screener run.
4. **If watchlist is stale (>4h pre-market, >8h intraday) OR regime shifted:** run screeners, add gems to watchlist as a side effect, then run signals.

**Screener → watchlist side effect:**
- VCP setups scoring ≥75 → `trader watchlist add TICKER --list vcp-candidates`
- CANSLIM setups scoring ≥70 → `trader watchlist add TICKER --list canslim`
- High-conviction opportunistic plays → `trader watchlist add TICKER --list momentum`

**Alert proposals:**
- Opportunity-finder proposes entry prices but does NOT call `trader alerts create`
- Proposals are passed to the conductor via structured output, then routed through order-alert-manager

---

### 3. `strategy-optimizer` Agent — Updated Behavior

**Schedule:** Bi-weekly baseline (1st and 15th of the month). Conductor may invoke earlier in response to significant market events (post-FOMC, sector shock, earnings surprise cluster).

**Ticker selection (agent decides):**
- Read JSONL log for which tickers were last optimized and when
- Prioritize: new watchlist additions since last optimization run + tickers with recent signal failures (trade entered on signal but underperformed)
- Typically 3–8 tickers per run — not the full watchlist
- Tickers with no new information since last optimization keep existing params

**Signal output:**
- When optimized params yield a buy signal → emit `ALERT_PROPOSAL` with calculated entry price
- This flows to conductor → order-alert-manager → decides whether to create alert or place order directly

**Remove Sunday-only constraint.** The agent checks the date/log and determines if an optimization run is warranted.

---

### 4. `vcp-screener` Skill — Updated Universe Discovery

Step 1 becomes a priority chain:

1. **Watchlist first** — if a list name is provided (e.g., `--list vcp-candidates`), use those tickers as the starting universe. Skip to Stage 2 confirmation.
2. **`trader scan`** — run IBKR scanner for fresh candidates:
   ```bash
   uv run trader scan run HIGH_VS_52W_HL --ema200-above --avg-volume-above 200000 --limit 30
   uv run trader scan run TOP_PERC_GAIN --mktcap-above 300 --ema50-above --limit 20
   ```
3. **FinViz fallback** — if no watchlist provided and scanner unavailable, use FinViz URLs (existing behavior, retained as fallback/reference).

**Side effect:** Tickers scoring ≥75 at end of workflow → `trader watchlist add TICKER --list vcp-candidates`

---

### 5. `stock-screener` Skill — Updated Universe Discovery

Same priority chain as vcp-screener. Watchlist first → `trader scan` → FinViz fallback.

**Side effect:** Exceptional (≥85) and Strong (≥70) tickers → `trader watchlist add TICKER --list canslim`

---

### 6. `portfolio-conductor` Agent — Updated Dispatch

Add `order-alert-manager` to the standard dispatch list:

| Time slot | Agents dispatched |
|-----------|------------------|
| pre-market | risk-monitor, portfolio-health, opportunity-finder, **order-alert-manager** |
| intraday | risk-monitor, portfolio-health, opportunity-finder (if stale), **order-alert-manager** |
| bi-weekly | portfolio-health (deep), strategy-optimizer, **order-alert-manager** |

The conductor consolidates all proposals — including the order-alert-manager's action list — before executing anything. The conductor is the only agent that calls `trader alerts create`, `trader orders buy`, `trader orders stop`, or `trader orders sell`.

---

## What Is NOT Changed

- Order execution authority stays exclusively with the conductor
- Position sizing logic (ATR-based, Kelly) unchanged
- Risk guardrails (max position size, daily order limits) unchanged
- Supervised vs autonomous mode unchanged
- FinViz URLs retained in vcp-screener and stock-screener as fallback

---

## Success Criteria

- Screeners populate named watchlists as a side effect
- Bi-weekly optimization selects tickers intelligently (3–8, not full list)
- Alert proposals flow through order-alert-manager before conductor acts
- No duplicate alerts created for the same ticker/price
- Stale open orders are surfaced for cancellation review
- Agent decisions documented in JSONL log with enough context to audit
