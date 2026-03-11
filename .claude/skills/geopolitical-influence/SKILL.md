---
name: geopolitical-influence
description: Use when the user wants to analyze a geopolitical event (conflict, sanction, trade war, election, central bank policy shift) for market impact — mapping the event to affected sectors/assets, directional bias, recommended hedges, and 3 weighted scenarios.
---

# Geopolitical Influence Analyzer

## Overview

Analyzes geopolitical events for market impact. Searches current news, maps events to affected sectors and assets, confirms signals with live sentiment and strategy data from the trader CLI, and outputs structured scenarios (base/bull/bear) with probability weights and actionable hedging guidance.

## When to Use

- "How does the Russia/Ukraine escalation affect my portfolio?"
- "What's the market impact of the new US-China tariffs?"
- "Fed just signaled rate pause — what sectors benefit?"
- "There's an election in [country] — what moves?"
- "Analyze the oil embargo news for my energy positions"
- Any overnight geopolitical event before market open

## Event Categories

| Category | Examples | Primary Asset Impact |
|----------|----------|----------------------|
| Armed conflict / escalation | Regional wars, airstrikes | Oil, defense (LMT/RTX/NOC), gold, airlines |
| Sanctions / trade restrictions | Export controls, embargoes | Semiconductors, agricultural commodities |
| Trade war / tariffs | US-China duties, Section 301 | Industrials, consumer discretionary, logistics |
| Election / regime change | Major economy elections | Domestic equities, currency, sovereign bonds |
| Central bank policy shift | Rate hike/cut surprise, QE/QT | Rates-sensitive sectors, financials, growth stocks |
| Energy supply shock | OPEC cut, pipeline disruption | XLE, XOP, airlines, chemicals, transportation |
| Pandemic / health emergency | Outbreak, travel restrictions | Healthcare, pharma, travel & leisure |
| Cyber / infrastructure attack | Grid, financial system targets | Cybersecurity (CRWD/PANW), utilities |

## CLI Integration

```bash
# News sentiment on directly affected tickers
uv run trader news sentiment TICKER --lookback 48h

# Latest news headlines for affected tickers
uv run trader news latest --tickers TICKER1,TICKER2 --limit 15

# Strategy signals with news overlay on affected basket
uv run trader strategies signals --tickers AFFECTED_TICKERS --strategy rsi --with-news

# Check current positions for exposure
uv run trader positions list

# Quote affected tickers for current price context
uv run trader quotes get TICKER1 TICKER2 TICKER3
```

## Workflow

### Step 1 — Event Identification and Classification

Gather the geopolitical event details:
- **What**: Specific event description
- **Where**: Geography (country/region)
- **Who**: Key actors (governments, central banks, corporations)
- **When**: Timeline (announced, ongoing, expected resolution)
- **Category**: Use the Event Categories table above

Use web search to pull current headlines, official statements, and analyst reactions. Search for:
- `"[event keyword] market impact site:reuters.com OR site:bloomberg.com"`
- `"[event keyword] sector ETF"`
- `"[commodity/currency] [event keyword] outlook"`

### Step 2 — Sector and Asset Mapping

Map the event to directly and indirectly affected sectors:

**Direct impact** — sectors/assets with an obvious first-order link:

| Event Type | Long bias | Short bias |
|------------|-----------|------------|
| Oil supply disruption | XLE, XOP, CVX, XOM | Airlines (AAL/DAL/UAL), chemicals |
| US-China trade tension | Defense (ITA), domestic mfg | Semiconductors (SOXX), Apple supply chain |
| Rate hike surprise | Financials (XLF), short-duration | Utilities (XLU), REITs (VNQ), growth (QQQ) |
| Armed conflict (Europe) | Defense, gold (GLD), oil | European equities, tourism |
| Dollar strengthening | Gold shorts, EM debt caution | Commodities priced in USD |
| Sanctions on tech exports | Domestic semis (INTC/TXN) | NVDA China exposure, ASML |

**Indirect / second-order impact** — derive from supply chain, currency, consumer confidence effects.

### Step 3 — Confirm with Live CLI Data

For the top 5-8 most affected tickers, run:

```bash
# Latest news to confirm the event is being priced in
uv run trader news latest --tickers XLE,CVX,XOM,AAL,DAL --limit 10

# Sentiment score to gauge market reaction
uv run trader news sentiment XLE --lookback 48h
uv run trader news sentiment AAL --lookback 48h

# RSI signals to spot oversold/overbought reactions
uv run trader strategies signals --tickers XLE,CVX,AAL,DAL --strategy rsi --with-news
```

Parse the CLI output:
- Sentiment > 0.3 + RSI < 40 → strong bullish setup (oversold with positive catalyst)
- Sentiment < -0.3 + RSI > 60 → strong bearish setup (overbought with negative catalyst)
- Divergence between sentiment and RSI → wait for confirmation

### Step 4 — Check Portfolio Exposure

```bash
uv run trader positions list
```

Identify which current holdings overlap with the affected sectors. Flag:
- **Direct exposure** — position in an affected ticker
- **Sector exposure** — position in an ETF covering the affected sector
- **Indirect exposure** — position in companies with significant revenue from the affected region

### Step 5 — Build Three Scenarios

For each scenario, assign a probability (Base + Bull + Bear = 100%):

**Base Case (most likely, 50-60%)**
- Event resolves along consensus expectations
- Affected sectors reprice moderately then stabilize
- Describe: duration, magnitude of move, key triggers to watch

**Bull Case (upside, 20-30%)**
- Event resolves faster or better than expected (ceasefire, deal, policy reversal)
- Describe: specific positive catalyst, sectors that outperform, magnitude

**Bear Case (downside, 15-25%)**
- Event escalates or broadens (widening conflict, retaliatory sanctions, contagion)
- Describe: specific escalation trigger, sectors that underperform, magnitude, tail risk

### Step 6 — Recommended Hedges

Based on event type and portfolio exposure, suggest hedges:

| Situation | Hedge Instrument | CLI Command |
|-----------|-----------------|-------------|
| Equity downside | Put on SPY or QQQ | `trader orders buy SPY 1 --contract-type option --right put --expiry ... --strike ...` |
| Energy spike risk | Long XLE calls | `trader orders buy XLE 1 --contract-type option --right call --expiry ...` |
| Safe haven flight | Long GLD | `trader orders buy GLD 50` |
| Portfolio short | Trailing stop on vulnerable positions | `trader orders trailing-stop TICKER --trail-percent 3.0` |

Only recommend hedges proportional to the event severity rating.

### Step 7 — Output Report

```
GEOPOLITICAL INFLUENCE ANALYSIS
Event: [Event Name]
Date:  {date}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EVENT SUMMARY
  Category:   [e.g. Armed Conflict / Energy Supply Shock]
  Severity:   High | Medium | Low
  Geography:  [Region]
  Status:     Developing | Contained | Resolving

SEVERITY RATING
  High   = Systemic risk, broad market impact, VIX likely spikes >25
  Medium = Sector-specific, 1-3 weeks of elevated volatility
  Low    = Limited to single asset class, market likely shrugs within days

AFFECTED SECTORS & DIRECTIONAL BIAS
  ↑ XLE (Energy)      — Oil supply disruption → price spike → producers benefit
  ↑ GLD (Gold)        — Flight to safety
  ↓ AAL/DAL/UAL       — Fuel cost spike, potential route disruptions
  ↓ SOXX (Semis)      — Export restriction risk

LIVE SIGNAL CONFIRMATION
  XLE:  Sentiment +0.62, RSI 38 → Bullish setup (oversold + positive catalyst)
  AAL:  Sentiment -0.51, RSI 64 → Bearish setup (overbought + negative catalyst)

PORTFOLIO EXPOSURE
  Direct:   [list overlapping positions]
  Indirect: [list sector/geographic overlaps]

SCENARIOS
  Base (55%): [Description, expected moves, timeline]
  Bull (25%): [Catalyst, outperformers, magnitude]
  Bear (20%): [Escalation trigger, downside, tail risk]

RECOMMENDED ACTIONS
  1. [Immediate hedge if severity=High]
  2. [Trim or protect vulnerable positions]
  3. [Opportunistic long in benefiting sector]

COMMANDS TO EXECUTE
  # Paste-ready CLI commands with specific parameters
```

## Quick Reference

| Goal | Command |
|------|---------|
| Sector sentiment scan | `uv run trader news sentiment XLE --lookback 48h` |
| Affected tickers news | `uv run trader news latest --tickers T1,T2 --limit 15` |
| Signal confirmation | `uv run trader strategies signals --tickers T1,T2 --strategy rsi --with-news` |
| Portfolio exposure | `uv run trader positions list` |
| Protect position | `uv run trader orders trailing-stop TICKER --trail-percent 3.0` |
| Safe haven buy | `uv run trader orders buy GLD 50` |

## Common Mistakes

- **Overcalling severity** — not every geopolitical headline is High severity. Use the VIX proxy (>25 = High, 18-25 = Medium, <18 = Low) as a calibration check.
- **Ignoring second-order effects** — a conflict's biggest market impact is often indirect (e.g. Europe energy crisis → USD strength → EM pressure).
- **Skipping CLI confirmation** — always run sentiment + RSI signals before committing to a trade thesis. News may already be priced in.
- **Probability math** — Base + Bull + Bear must equal exactly 100%.
- **Wrong lookback for sentiment** — use `--lookback 48h` for breaking news, `--lookback 7d` for slower-developing situations.
- **Acting without checking positions** — always run `positions list` first to know your existing exposure before recommending new trades.
