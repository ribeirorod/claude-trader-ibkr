---
name: economic-calendar-fetcher
description: Use when the user wants to check upcoming economic events before placing trades, or when performing a pre-trade risk check. Fetches the economic calendar via web search (no FMP API required) and flags high-impact events within 48 hours. Triggers on queries like "any events this week?", "is it safe to trade before NFP?", "check the calendar", "pre-trade risk check", "any Fed announcements coming up?".
---

# Economic Calendar Fetcher (Pre-Trade Risk Check)

## Overview

Fetches upcoming macroeconomic events using web search and classifies them by impact level. Primary use case is a **pre-trade risk check**: before placing any significant order, verify that no high-impact event (Fed meeting, NFP, CPI) falls within the next 48 hours. No API key required — uses web search.

## When to Use

- Before placing a bracket order or large position
- "What's on the economic calendar this week?"
- "Is it safe to enter AAPL now, or is CPI tomorrow?"
- "Any Fed speakers today?"
- "Pre-trade check before I add to my position"
- Anytime you want to avoid getting caught in an event-driven spike/crash

## Pre-Trade Risk Rule

> **Do not open new positions within 24 hours before a High-impact event.**
> Reduce existing size within 4 hours before any High-impact event if the position is in profit.
> Medium-impact events warrant awareness but not necessarily avoidance.

## Event Categories and Impact Levels

### High Impact (Avoid new trades within 24h)

| Event | Typical Schedule | Why It Matters |
|-------|-----------------|----------------|
| FOMC Rate Decision | 8x/year (Wed 2pm ET) | Reprices entire risk curve |
| Fed Chair Press Conference | Post-FOMC (Wed 2:30pm ET) | Forward guidance = volatility |
| Non-Farm Payrolls (NFP) | 1st Fri of month (8:30am ET) | Key labor market signal |
| CPI (Consumer Price Index) | ~12th of month (8:30am ET) | Inflation = rate expectations |
| PCE Deflator | ~last Fri of month (8:30am ET) | Fed's preferred inflation gauge |
| GDP (Advance/Preliminary) | Quarterly (8:30am ET) | Growth trajectory signal |
| JOLTS / ADP Payrolls | Mid-month | Labor market leading indicators |

### Medium Impact (Be aware, manage size)

| Event | Notes |
|-------|-------|
| ISM Manufacturing / Services PMI | First week of month |
| Retail Sales | Mid-month |
| Producer Price Index (PPI) | Day before CPI |
| Consumer Confidence / Sentiment | End of month |
| Fed Speaker Appearances | Can move markets if discussing policy |
| Treasury Auctions (3Y, 10Y, 30Y) | Rates volatility |
| Initial Jobless Claims | Weekly, Thursdays 8:30am ET |

### Low Impact (Monitor only)

- Housing starts, building permits
- Factory orders
- Import/export prices
- Non-voting Fed speakers (routine remarks)

## Workflow

### Step 1 — Fetch the Calendar

Use web search to retrieve the current week's economic calendar:

```
Search: "economic calendar this week [current date] high impact"
Search: "FOMC meeting dates 2026"
Search: "NFP date [current month] 2026"
Search: "CPI release date [current month] 2026"
```

Also check for surprises or revisions that could move markets even on low-scheduled weeks.

### Step 2 — Identify Events Within 48 Hours

From the fetched calendar, extract all events in the next 48 hours. Flag:
- **RED**: High-impact event within 24h → do not open new positions
- **YELLOW**: High-impact event in 24-48h → reduce sizing, tighten stops
- **GREEN**: No high-impact events within 48h → proceed with normal risk rules

### Step 3 — Cross-Reference Open Positions

```bash
uv run trader positions list
```

For each open position, ask: is this position directionally exposed to the upcoming event?
- Long AAPL before CPI → rate-sensitive tech = elevated risk
- Long XLE before NFP → less directly exposed
- Long TLT before FOMC → extremely rate-sensitive = reduce or hedge

### Step 4 — Check Sentiment Drift Pre-Event

Market sentiment often shifts in the 24-48h window before a major event. Check:

```bash
uv run trader news sentiment SPY --lookback 48h
uv run trader news sentiment [relevant sector ETF] --lookback 48h
```

Negative sentiment drift pre-event amplifies downside risk if the event disappoints.

### Step 5 — Pre-Trade Decision

Based on Steps 1-4:

| Condition | Decision |
|-----------|----------|
| RED (High-impact < 24h) | No new positions. Consider reducing existing. |
| YELLOW (High-impact 24-48h) | Reduce position size by 50%. Set tighter stops. |
| YELLOW + negative sentiment | Treat as RED. |
| GREEN + positive signals | Proceed. Normal position sizing applies. |
| GREEN + mixed signals | Proceed with reduced size (75% normal). |

If proceeding with a trade, place the order:

```bash
# Example: bracket order with tighter stops pre-event
uv run trader orders bracket AAPL 5 --entry 195 --take-profit 205 --stop-loss 190

# Or set a protective stop on existing position
uv run trader orders stop AAPL --price 190
```

## Output Format

```
## Pre-Trade Economic Risk Check — [Date/Time]

### 48-Hour Event Window
| Time (ET) | Event | Impact | Direction Risk |
|-----------|-------|--------|----------------|

### Risk Flag: [RED / YELLOW / GREEN]
[One sentence explaining the flag]

### Open Position Exposure
[List positions from `trader positions list` and their event sensitivity]

### Recommendation
[Go / Size-Down / Stand-Aside — with specific reasoning]

### Next High-Impact Event
[Event name, date/time, what it measures, consensus expectation if available]
```

## Quick Reference

| Task | Action |
|------|--------|
| Fetch calendar | Web search "economic calendar [date]" |
| Check open positions | `trader positions list` |
| Pre-event sentiment | `trader news sentiment SPY --lookback 48h` |
| Place protective stop | `trader orders stop TICKER --price X` |
| Reduce position | `trader orders sell TICKER N --type market` |
| Check account headroom | `trader account margin` |

## FOMC Meeting Dates 2026 (Reference)

Approximate schedule (confirm via web search — dates shift):
- Late January, Mid-March, Late April, Mid-June, Late July, Mid-September, Early November, Mid-December

Each FOMC has a 2-day meeting followed by a Wednesday 2pm ET decision + 2:30pm press conference. The day before (Tuesday) often sees elevated implied volatility.

## Common Mistakes

- **Skipping the calendar check before earnings** — This skill covers macro events. For individual stock earnings dates, use `trader news latest --tickers TICKER` and check for earnings announcement news.
- **Assuming a GREEN flag means safe** — GREEN means no *scheduled* high-impact macro events. Market-moving surprises (geopolitical shocks, unscheduled Fed statements) can always occur.
- **Ignoring the pre-event drift window** — Markets often make their biggest moves the day before a major event (positioning). Check sentiment 48h out, not just on event day.
- **Not protecting profitable positions** — Use `trader orders trailing-stop TICKER --trail-percent 2.5` to lock in gains before an event rather than closing outright.
- **Treating all High-impact events equally** — An FOMC rate decision is more impactful than JOLTS. Weight accordingly when deciding to sit out vs size down.
- **Forgetting time zones** — All times above are Eastern Time (ET). Adjust if trading foreign sessions.
