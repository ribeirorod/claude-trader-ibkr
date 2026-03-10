# Autonomous Portfolio Agents — Design Spec
**Date:** 2026-03-10
**Status:** Approved

---

## 1. Overview

A multi-agent system that autonomously manages a trading portfolio using the existing skill library. A single orchestrator (`portfolio-conductor`) runs on a cron schedule, reads live portfolio state and JSONL history, decides which specialist sub-agents to invoke, collects their proposals, and executes approved orders via the trader CLI.

**Core principle:** The conductor never blocks action based on regime — it passes full context to specialists and lets their intelligence decide. "Do nothing" is a first-class outcome, not a gate.

---

## 2. Architecture

```
CRON (pre-market / intraday / weekly)
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│                  portfolio-conductor                    │
│                                                         │
│  1. Fetch snapshot (positions, account, open orders)    │
│  2. Read JSONL log (last 50 entries)                    │
│  3. Read portfolio profile (.trader/profile.json)       │
│  4. Assess context: regime, health, time_slot           │
│  5. Decide workflow — which agents make sense NOW?      │
│     → "do nothing" is always a valid outcome            │
│  6. Dispatch chosen specialists with shared context     │
│  7. Collect proposals → check guardrails → log intent   │
│  8. Execute orders via trader CLI                       │
│  9. Write RUN_END to JSONL                              │
└─────────────────────────────────────────────────────────┘
                          │
              Conductor picks from full skill library
                          │
        ┌─────────────────┼──────────────────────┐
        │                 │                      │
   RISK LAYER        OPPORTUNITY LAYER      MAINTENANCE LAYER
        │                 │                      │
  risk-monitor      stock-screener          portfolio-health
  market-top        vcp-screener            strategy-optimizer
  portfolio-mgr     earnings-analyzer
  sector-analyst    technical-analyst
  economic-cal      options-advisor
  geopolitical      market-news-analyst
  druckenmiller     sector-analyst
                    position-sizer
```

**Only the conductor places orders.** Specialists propose — conductor logs intent, fires.

---

## 3. Agent Files

```
.claude/agents/
├── portfolio-conductor.md     # orchestrator — sole cron entry point
├── risk-monitor.md            # position health, drawdown, stop triggers
├── opportunity-finder.md      # new trade ideas across all asset classes
├── portfolio-health.md        # allocation drift, concentration, rebalance
└── strategy-optimizer.md      # weekly backtest + param refresh (weekly only)
```

### Agent Responsibilities

| Agent | Invoked when | Skills drawn from | Places orders? |
|---|---|---|---|
| `portfolio-conductor` | Every cron tick | All (via sub-agents) | Yes — final executor only |
| `risk-monitor` | Every run with open positions | `portfolio-manager`, `market-top-detector`, `technical-analyst`, `stanley-druckenmiller-investment` | Yes — stops/trims only |
| `opportunity-finder` | Conductor decides | `stock-screener`, `vcp-screener`, `earnings-trade-analyzer`, `options-strategy-advisor`, `sector-analyst`, `market-news-analyst`, `technical-analyst`, `position-sizer` | No — proposes only |
| `portfolio-health` | Every run + weekly deep review | `portfolio-manager`, `sector-analyst` | No — proposes only |
| `strategy-optimizer` | Weekly only | `backtest-expert`, `trader-strategies` | No — recommendations only |

---

## 4. Conductor Decision Logic

```
1.  Fetch snapshot: positions, account summary, open orders
2.  Read last 50 entries from .trader/logs/agent.jsonl
3.  Read .trader/profile.json (portfolio north star)
4.  Determine time_slot: pre-market | intraday | weekly
5.  Always dispatch risk-monitor if open positions exist
6.  Always dispatch portfolio-health (surfaces drift even if no action)
7.  Opportunity-finder dispatch logic:
      pre-market → yes, full scan across all skills
      intraday   → yes, but narrow — high-conviction signals only
      weekly     → no
8.  strategy-optimizer dispatch logic:
      weekly     → yes
      otherwise  → no
9.  Collect all specialist proposals
10. For each proposal, apply mechanical guardrails:
      - cash_only: no margin, no leverage
      - max_single_position_pct: from profile
      - max_new_positions_per_day: from profile (check log for today's count)
11. Log ORDER_INTENT for each approved proposal
12. Execute via trader CLI
13. Log RUN_END with summary (actions taken, skipped, reasoning)
```

---

## 5. JSONL Log Schema

**File:** `.trader/logs/agent.jsonl`
**Format:** One JSON object per line. Append-only.

### Event Types

```jsonl
// Run lifecycle
{"ts":"2026-03-10T08:01:00Z","run_id":"abc123","agent":"conductor","event":"RUN_START","context":{"regime_score":72,"positions":5,"buying_power":18400,"time_slot":"pre-market"}}
{"ts":"2026-03-10T08:01:12Z","run_id":"abc123","agent":"conductor","event":"WORKFLOW_DECISION","skills_invoked":["sector-analyst","vcp-screener","technical-analyst","options-advisor"],"skipped":["strategy-optimizer"],"reason":"pre-market slot, no weekly tasks"}
{"ts":"2026-03-10T08:04:02Z","run_id":"abc123","agent":"conductor","event":"ORDER_INTENT","ticker":"NVDA","action":"buy","shares":12,"type":"limit","price":891.50,"reason":"VCP breakout + bullish sentiment + RSI not overbought"}
{"ts":"2026-03-10T08:04:05Z","run_id":"abc123","agent":"conductor","event":"ORDER_PLACED","ticker":"NVDA","order_id":"ibkr-9921","status":"submitted"}
{"ts":"2026-03-10T08:04:05Z","run_id":"abc123","agent":"conductor","event":"RUN_END","actions_taken":1,"orders_placed":1,"do_nothing":false,"duration_s":125}

// Specialist signals
{"ts":"2026-03-10T08:03:44Z","run_id":"abc123","agent":"opportunity-finder","event":"SIGNAL","ticker":"NVDA","signal":"buy","strategy":"vcp_breakout","conviction":0.81,"sentiment":0.4}
{"ts":"2026-03-10T08:03:50Z","run_id":"abc123","agent":"risk-monitor","event":"RISK_FLAG","ticker":"XOM","flag":"drawdown_20pct","current_pnl_pct":-21.3,"recommendation":"review stop-loss"}
{"ts":"2026-03-10T08:03:55Z","run_id":"abc123","agent":"portfolio-health","event":"DRIFT","sector":"technology","current_pct":38,"target_max_pct":35,"recommendation":"trim on next opportunity"}

// Do nothing
{"ts":"2026-03-10T12:01:00Z","run_id":"def456","agent":"conductor","event":"RUN_END","actions_taken":0,"orders_placed":0,"do_nothing":true,"reason":"no high-conviction signals, portfolio within targets, risk monitor clean"}
```

**Key fields on every entry:** `ts` (ISO-8601), `run_id`, `agent`, `event`.

---

## 6. Shared Context Object

Built by the conductor, passed to every specialist sub-agent:

```json
{
  "run_id": "abc123",
  "time_slot": "pre-market",
  "snapshot": {
    "net_liquidation": 92400,
    "buying_power": 18400,
    "positions": ["...positions list output..."],
    "open_orders": ["...open orders output..."],
    "unrealized_pnl": 3120
  },
  "recent_log": ["...last 50 JSONL entries..."],
  "profile": {"...contents of .trader/profile.json..."},
  "guardrails": {
    "cash_only": true,
    "max_single_position_pct": 0.10,
    "max_new_positions_per_day": 3
  }
}
```

---

## 7. Portfolio Profile

**File:** `.trader/profile.json`
**Purpose:** North star document agents read on every run. Guidance, not hard constraints — strong signals override sector preferences.

```json
{
  "profile_version": "1.0",
  "last_updated": "2026-03-10",

  "risk_tolerance": "moderate",
  "time_horizon": "mid-term",
  "trading_style": {
    "day_trading": "minimal",
    "preferred_hold_days": "5-90",
    "note": "keep turnover low, favor swing and position trades"
  },

  "asset_classes": {
    "equities": true,
    "etfs": true,
    "options": true,
    "futures": true,
    "crypto": false,
    "leverage": false
  },

  "preferred_sectors": [
    "energy",
    "emerging_markets",
    "semiconductors",
    "defense"
  ],
  "sector_note": "agents may screen and invest in other sectors when signals are strong — these are starting bias, not exclusions",

  "portfolio_targets": {
    "max_single_position_pct": 10,
    "max_sector_concentration_pct": 35,
    "max_new_positions_per_day": 3,
    "target_cash_reserve_pct": 10
  },

  "options_preferences": {
    "allowed_strategies": ["covered_call", "cash_secured_put", "spreads", "iron_condor", "directional", "earnings_plays"],
    "max_options_portfolio_pct": 20
  },

  "notes": "Free-form field. Update as your thesis evolves — agents read this on every run."
}
```

---

## 8. Cron Schedule

Three schedule slots, all routing through `portfolio-conductor`:

| Schedule | Cron | Slot | Focus |
|---|---|---|---|
| Pre-market | `0 8 * * 1-5` | `pre-market` | Full workflow: risk + opportunity + health |
| Intraday | `0 9-16 * * 1-5` | `intraday` | Risk-first, narrow opportunity scan |
| Weekly | `0 18 * * 0` | `weekly` | Deep health review + strategy optimization |

---

## 9. Operating Modes

| Mode | Behavior |
|---|---|
| **Autonomous** (default) | Conductor executes approved orders automatically after logging intent |
| **Supervised** | Conductor logs ORDER_INTENT to JSONL and halts — human reviews and confirms before execution |

Mode is set via environment variable: `AGENT_MODE=autonomous` or `AGENT_MODE=supervised`.

---

## 10. Guardrails (mechanical, non-judgmental)

These are portfolio math limits, not market judgements:

| Guardrail | Value | Source |
|---|---|---|
| Cash only | No margin, no leverage | Hard-coded |
| Max single position | 10% of net liquidation | `profile.json` |
| Max new positions/day | 3 | `profile.json` |
| Target cash reserve | 10% of portfolio | `profile.json` |
| Max options allocation | 20% of portfolio | `profile.json` |

All other decisions — what to buy, when, in what direction — belong to the specialist agents.
