---
name: market-news-analyst
description: Use when the user asks about market-moving news, wants to understand why a stock or sector moved, needs to assess the impact of a recent event (earnings, FOMC, geopolitical), or wants a news-driven trade rationale. Runs a 6-step workflow to collect, integrate, score, and report on news events from the past 10 days.
---

# Market News Analyst

## Overview

Analyzes recent market-moving news (past 10 days) using our trader CLI's news commands as the primary data source. Produces a structured impact report ranked by significance. Rigorously distinguishes causation from coincidence.

## When to Use

- "Why did AAPL drop today?"
- "What's moving the market this week?"
- "Give me a news-driven trade rationale for TSLA"
- "What happened after the FOMC announcement?"
- "Summarize market news for the last 48 hours"

## CLI Integration

```bash
# Fetch recent news for a ticker or basket
uv run trader news latest --tickers AAPL,MSFT,TSLA --limit 20

# Sentiment score for a ticker (-1.0 bearish → +1.0 bullish)
uv run trader news sentiment AAPL --lookback 48h
uv run trader news sentiment AAPL --lookback 7d

# Combine with strategy signals for price context
uv run trader strategies signals --tickers AAPL --strategy rsi
uv run trader strategies signals --tickers AAPL --strategy macd

# Cross-check current price vs recent levels
uv run trader quotes get AAPL

# Review open positions affected by news
uv run trader positions list
```

## 6-Step Workflow

### Step 1 — Collect

Gather news across these categories (use web search for macro events, CLI for ticker-specific news):

| Category | Source |
|---|---|
| Monetary policy (FOMC, Fed speakers) | Web search |
| Inflation / CPI / PCE / NFP | Web search |
| Mega-cap earnings | `trader news latest --tickers AAPL,MSFT,NVDA,GOOGL,AMZN,META` |
| Geopolitical / sanctions / tariffs | Web search |
| Commodities (oil, gold, rates) | Web search |
| Sector-specific corporate news | `trader news latest --tickers <relevant tickers>` |

Lookback window: default 48h for intraday context, 7d for weekly analysis.

### Step 2 — Integrate

For each event identified, pull sentiment data:

```bash
uv run trader news sentiment TICKER --lookback 48h
```

Cross-reference price reaction:

```bash
uv run trader quotes get TICKER
uv run trader strategies signals --tickers TICKER --strategy macd
```

Note the direction and magnitude of price move vs sentiment score direction.

### Step 3 — Impact Scoring

Score each event using this formula:

```
Impact Score = (Price Move % × Breadth Multiplier) × Forward-Looking Modifier

Price Move %      — actual % change in ticker/index
Breadth Multiplier — 1.0 (single stock) | 1.5 (sector) | 2.0 (broad market)
Forward Modifier  — 0.5 (one-time event) | 1.0 (ongoing trend) | 1.5 (structural shift)
```

Rank events by Impact Score descending.

### Step 4 — Market Reaction Analysis

For each top-ranked event, assess reaction across:

- **Equities**: affected tickers, sector ETFs (XLK, XLF, XLE, XLY, etc.)
- **Rates**: direction of move implies risk-on/risk-off
- **Volatility**: elevated VIX signals uncertainty, not just directional risk
- **Commodities**: oil/gold moves often lead or confirm macro thesis

### Step 5 — Causation vs Coincidence

For each price move + news pair, apply these tests before attributing causation:

1. **Timing**: Did the news precede the move by less than 2 hours? If not, look for the true catalyst.
2. **Magnitude**: Is the move outsized relative to the news importance?
3. **Breadth**: Did correlated assets move in the same direction? Broad co-movement supports causation.
4. **Alternative explanations**: Was there a macro event, options expiry, or technical level at play simultaneously?
5. **Reversal check**: Did the move reverse after initial reaction? Suggests algo/headline response, not fundamental repricing.

Label each event: **Causal**, **Contributing**, or **Coincidental**.

### Step 6 — Report

Produce a structured report:

```
## Market News Impact Report — [Date Range]

### Executive Summary
[2-3 sentence thesis on dominant market narrative]

### Top Events by Impact Score
| Rank | Event | Ticker(s) | Impact Score | Causation Label |
|------|-------|-----------|--------------|-----------------|

### Event Deep-Dives
[For each top-3 event: what happened, CLI data, price reaction, forward implications]

### Thematic Synthesis
[Connecting threads across events — e.g., "rate sensitivity dominating all moves"]

### Forward Implications
[What to watch in next 48h; event risk on the horizon]

### Positions at Risk
[Cross-reference against `trader positions list` output — which open positions are exposed?]
```

## Quick Reference

| Task | Command |
|------|---------|
| Ticker news feed | `trader news latest --tickers AAPL --limit 20` |
| Sentiment score | `trader news sentiment AAPL --lookback 48h` |
| Price context | `trader quotes get AAPL` |
| Technical confirmation | `trader strategies signals --tickers AAPL --strategy macd` |
| Check affected positions | `trader positions list` |

## Common Mistakes

- **Mistaking correlation for causation** — A stock moving on the same day as a news event does not mean the event caused the move. Apply the 5-point causation test in Step 5.
- **Anchoring to first headline** — Algo-driven moves on headlines often reverse. Wait for the secondary reaction before forming a thesis.
- **Ignoring macro backdrop** — Ticker-level news matters less in a risk-off macro environment. Always check rates/VIX context.
- **Stale sentiment scores** — `--lookback 48h` gives sharply different readings than `--lookback 7d`. Use 48h for intraday, 7d for swing trade context.
- **Missing the actual catalyst** — Use web search for FOMC/CPI/NFP events that the CLI news feed may not capture (macro events don't have tickers).
- **Not checking positions** — Run `trader positions list` at the end of every news analysis to identify open exposure to the events discussed.
