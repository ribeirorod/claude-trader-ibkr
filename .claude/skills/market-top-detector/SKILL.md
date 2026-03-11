---
name: market-top-detector
description: Use when assessing whether the broad market is forming a top, evaluating distribution day counts, leadership breakdown, defensive rotation, or deciding whether to reduce equity exposure.
---

# Market Top Detector

## Overview

Scores the probability of a market top forming using a 6-component framework (0–100). Combines O'Neil distribution day tracking, Minervini leading-stock deterioration patterns, and defensive sector rotation signals. Targets 2–8 week tactical timing signals that precede 10–20% corrections. Pulls live signals from our CLI where available and supplements with analyst-sourced data.

**Output:** A score from 0–100 mapped to a risk zone, with a recommended action and position-size budget.

## When to Use

- User asks "is the market topping?" or "should I reduce exposure?"
- Distribution days are accumulating on major indices
- Leading stocks are breaking down while indices hold up
- Defensive sectors (utilities, staples, healthcare) are outperforming
- User wants a systematic framework before making a large position reduction

## CLI Integration

```bash
# Aggregate signal check across key tickers
trader strategies signals --tickers SPY,QQQ,IWM --strategy rsi
trader strategies signals --tickers SPY,QQQ,IWM --strategy macd

# Leading stock health — check top holdings for deterioration
trader strategies signals --tickers NVDA,AAPL,MSFT,AMZN,META --strategy ma_cross

# Defensive rotation check — compare sector ETF signals
trader strategies signals --tickers XLU,XLP,XLV,XLK,XLY --strategy rsi

# News sentiment on macro / market
trader news sentiment SPY --lookback 7d
trader news latest --tickers SPY --limit 20

# Portfolio P&L health
trader positions pnl
trader positions list
```

## Scoring Framework

Score each component and sum weighted scores. Final score = 0–100.

### Component 1 — Distribution Day Count (25 pts max)

Count distribution days on SPY/QQQ in the past 25 sessions (down ≥0.2% on higher volume than prior day).

| Count | Points |
|-------|--------|
| 0–2 | 0 |
| 3–4 | 10 |
| 5–6 | 18 |
| 7+ | 25 |

### Component 2 — Leading Stock Health (20 pts max)

Use `trader strategies signals --tickers <leaders> --strategy ma_cross` and count how many are below their 50-day MA or showing MACD bearish crosses.

| Leaders broken | Points |
|----------------|--------|
| <20% | 0 |
| 20–39% | 8 |
| 40–59% | 14 |
| 60%+ | 20 |

### Component 3 — Defensive Sector Rotation (15 pts max)

Compare XLU/XLP/XLV RSI signals vs XLK/XLY. Defensive outperformance is bearish.

```bash
trader strategies signals --tickers XLU,XLP,XLV,XLK,XLY --strategy rsi
```

| Signal | Points |
|--------|--------|
| Cyclicals leading | 0 |
| Mixed / neutral | 5 |
| Defensives clearly outperforming | 15 |

### Component 4 — Market Breadth Divergence (15 pts max)

Index at/near high but advance-decline line declining, or fewer stocks making new 52-week highs. Supplement with WebSearch for NYSE A/D line data.

| Breadth | Points |
|---------|--------|
| Confirming highs | 0 |
| Mild divergence | 7 |
| Strong divergence | 15 |

### Component 5 — Index Technical Condition (15 pts max)

```bash
trader strategies signals --tickers SPY,QQQ --strategy macd
trader strategies run SPY --strategy rsi --lookback 90d
```

| Condition | Points |
|-----------|--------|
| SPY above 50MA, RSI 50–70, MACD bullish | 0 |
| SPY near 50MA or RSI >75 | 7 |
| SPY below 50MA or RSI diverging | 15 |

### Component 6 — Sentiment & Speculation (10 pts max)

Use `trader news sentiment SPY --lookback 7d` plus check VIX level and put/call ratio (WebSearch if needed).

| Condition | Points |
|-----------|--------|
| VIX low, sentiment neutral-bearish | 0 |
| Euphoric sentiment, IPO frenzy | 5 |
| Extreme greed, VIX <13, put/call <0.7 | 10 |

## Risk Zones

| Score | Zone | Action | Max equity exposure |
|-------|------|---------|---------------------|
| 0–20 | Green — No signal | Normal trading | 100% |
| 21–40 | Yellow — Early caution | Tighten stops, no new laggards | 80% |
| 41–60 | Orange — Elevated risk | Trim weakest positions, raise cash | 60% |
| 61–80 | Red — High risk | Significant reduction, hedges | 40% |
| 81–100 | Critical — Top likely | Mostly cash/short, protect capital | 20% |

## Workflow

1. **Run CLI signals** — Execute the commands in CLI Integration above. Note bullish/bearish readings per component.
2. **Gather supplemental data** — Use WebSearch for NYSE A/D line, VIX term structure, put/call ratio if not in news output.
3. **Score each component** — Use tables above. Document evidence for each score.
4. **Sum and map to risk zone** — Report final score, zone, recommended action.
5. **Cross-check with positions** — Run `trader positions list` and `trader positions pnl`. If heavily long into a Red/Critical reading, suggest specific trims via `trader positions close` or `trader orders stop`.

## Output Format

```
Market Top Score: 67 / 100  →  RED ZONE

Component breakdown:
  Distribution Days (25):     18  — 6 days on SPY in 25 sessions
  Leading Stock Health (20):  14  — 45% of leaders below 50MA
  Defensive Rotation (15):     5  — mild defensive outperformance
  Breadth Divergence (15):    15  — A/D line diverging
  Index Technicals (15):       7  — SPY testing 50MA
  Sentiment (10):              8  — VIX 12.8, put/call 0.68

Recommendation: Reduce to 40% equity exposure.
Suggested actions:
  trader orders stop NVDA --price 118.00
  trader positions close LAGGARD_TICKER
```

## Common Mistakes

- **Scoring on index price alone** — The index can be flat while internals rot. Always check breadth and leadership separately.
- **Skipping CLI signals** — Don't estimate — run `trader strategies signals` before scoring components 2 and 5.
- **Reacting to a single distribution day** — One bad day isn't a top. Pattern requires 5+ days in 25 sessions.
- **Ignoring the trend of the score** — A score moving from 30 → 55 over two weeks is more actionable than a static 55.
- **Treating Critical as a short signal** — This skill signals risk reduction, not shorting. Avoid adding leveraged short positions without additional edge.
