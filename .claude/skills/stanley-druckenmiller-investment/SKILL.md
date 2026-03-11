---
name: stanley-druckenmiller-investment
description: Use when the user asks about overall market conviction, portfolio positioning, asset allocation, or wants a Druckenmiller-style synthesis of current conditions. Integrates market breadth, distribution risk, macro sentiment, and setup quality into a 7-component conviction score (0-100) and an allocation recommendation. Triggers on queries like "What is my conviction level?", "How should I position?", "Run the strategy synthesizer", "Druckenmiller analysis", "Should I be aggressive or defensive?".
---

# Stanley Druckenmiller Investment Synthesizer

## Overview

Druckenmiller-style conviction scoring: integrates upstream signals from our trader CLI (market breadth, distribution risk, sentiment, setup quality) into a single 0–100 conviction score that maps directly to an allocation posture. Emphasizes concentration over diversification, capital preservation over activity, and patience for high-probability fat pitches.

## Core Principles

1. **Concentration over diversification** — When conviction is high, size up. Diversification is for people who don't know what they're doing.
2. **Capital preservation is paramount** — Conviction below 40 = step aside. No score justifies ignoring downside.
3. **Fat pitch discipline** — Only swing when multiple signals converge. Mediocre setups at 60% conviction get a small bet, not a full position.
4. **Liquidity of mind** — Be willing to flip from bull to bear when evidence changes. No attachment to prior positions or thesis.
5. **Macro drives the bus** — Even the best stock setup fails in a broken macro regime.

## When to Use

- "What's my conviction level on the market right now?"
- "Should I add risk or reduce exposure?"
- "Druckenmiller synthesis — go or no go?"
- "How should I size my positions given current conditions?"
- "Is this a fat pitch or am I forcing a trade?"

## 7-Component Scoring System

| # | Component | Weight | Data Source |
|---|-----------|--------|-------------|
| 1 | Market Structure | 18% | MA cross signals on SPY, QQQ, IWM |
| 2 | Distribution Risk | 18% | RSI extremes + high-volume reversals on SPY/QQQ |
| 3 | Bottom Confirmation | 12% | Follow-Through Day pattern — IWM/small-cap leadership recovery |
| 4 | Macro Alignment | 18% | News sentiment on SPY + rates direction (web search) |
| 5 | Theme Quality | 12% | Top sector signals from sector-analyst output |
| 6 | Setup Availability | 10% | Number of tickers with clean bullish signals (strategies signals) |
| 7 | Signal Convergence | 12% | Agreement across RSI + MACD + MA cross on benchmark ETFs |

### Per-Component Scoring (0–10 scale, multiply by weight × 10 for contribution)

**Component 1 — Market Structure (18%)**
```bash
uv run trader strategies signals --tickers SPY,QQQ,IWM --strategy ma_cross
```
- All 3 bullish → 9-10
- 2 of 3 bullish → 6-8
- Mixed → 4-5
- 2-3 bearish → 0-3

**Component 2 — Distribution Risk (18%)**
```bash
uv run trader strategies signals --tickers SPY,QQQ --strategy rsi
uv run trader strategies run SPY --strategy macd --interval 1d --lookback 60d
```
- No distribution signals, RSI 45-65 → 9-10
- Minor RSI divergence → 6-8
- RSI overbought (>70) + MACD weakening → 3-5
- High distribution, RSI divergence, MACD rollover → 0-2

**Component 3 — Bottom Confirmation (12%)**
```bash
uv run trader strategies signals --tickers IWM,MDY --strategy ma_cross
uv run trader strategies signals --tickers IWM --strategy rsi
```
- IWM leading SPY upside, RSI building from 40-50 → 8-10
- IWM in line with SPY → 5-7
- IWM lagging / small caps weak → 0-4

**Component 4 — Macro Alignment (18%)**
```bash
uv run trader news sentiment SPY --lookback 7d
# Supplement with web search: "Fed rate expectations this week", "10-year yield direction"
```
- Positive sentiment + easing rate backdrop → 9-10
- Neutral sentiment, rates stable → 5-7
- Negative sentiment OR rising rates headwind → 2-4
- Both negative → 0-1

**Component 5 — Theme Quality (12%)**
Run sector-analyst skill first. Use uptrend ratio and risk regime score:
- Risk regime ≥ 70 + clear leading sector → 8-10
- Regime 50-69, moderate theme → 5-7
- Regime < 50, no clear leadership → 0-4

**Component 6 — Setup Availability (10%)**
```bash
uv run trader strategies signals --tickers AAPL,MSFT,NVDA,GOOGL,AMZN,META,TSLA,JPM,XOM,UNH --strategy rsi
uv run trader strategies signals --tickers AAPL,MSFT,NVDA,GOOGL,AMZN,META,TSLA,JPM,XOM,UNH --strategy ma_cross
```
Count tickers with bullish signals across both strategies:
- 7+ tickers bullish → 8-10
- 4-6 bullish → 5-7
- 1-3 bullish → 2-4
- 0 bullish → 0-1

**Component 7 — Signal Convergence (12%)**
```bash
uv run trader strategies signals --tickers SPY --strategy rsi
uv run trader strategies signals --tickers SPY --strategy macd
uv run trader strategies signals --tickers SPY --strategy ma_cross
```
Count strategies agreeing on direction for SPY:
- All 3 agree bullish → 9-10
- 2 agree → 5-7
- All disagree / mixed → 0-4

## Conviction Score Calculation

```
Score = Σ (component_raw_score × component_weight × 10)
```

| Conviction Zone | Score | Allocation Posture |
|-----------------|-------|-------------------|
| Maximum | 80–100 | 80-100% deployed; concentrate in top 3-5 setups |
| High | 60–79 | 50-80% deployed; 4-7 positions, moderate size |
| Moderate | 40–59 | 25-50% deployed; selective, smaller sizing |
| Low | 20–39 | 10-25% deployed; capital preservation priority |
| Capital Preservation | 0–19 | Cash / hedges only; no new longs |

## Pattern Classification

After scoring, classify the market environment into one of 4 patterns:

| Pattern | Characteristics | Action |
|---------|-----------------|--------|
| **Policy Pivot Anticipation** | Macro turning bullish, breadth early recovery, sentiment improving | Accumulate leaders; be early |
| **Unsustainable Distortion** | High score but narrow leadership, extreme RSI, low IWM breadth | Reduce size; look for exits |
| **Extreme Sentiment Contrarian** | Very negative sentiment + good technical structure = washout bottom | Start building; tight stops |
| **Wait & Observe** | Mixed signals, no clear regime | Sit on hands; watch for resolution |

## Full Workflow

1. **Run prerequisites** — If sector-analyst skill output is available, use it for Components 5. Otherwise run it first.
2. **Score each component** — Use CLI commands listed per component. Score 0–10.
3. **Calculate total** — Weighted sum → 0–100 conviction score.
4. **Classify pattern** — Assign one of the 4 market patterns.
5. **Map to allocation** — Use conviction zone table for posture.
6. **Identify fat pitches** — Only in Maximum/High zones: run `strategies signals` on best setups.
7. **Output report** — Structured Markdown with score breakdown + allocation recommendation.

## Output Format

```
## Druckenmiller Conviction Report — [Date]

### Conviction Score: [X/100] — [Zone Label]
Pattern: [Policy Pivot / Unsustainable Distortion / Extreme Contrarian / Wait & Observe]

### Component Breakdown
| Component | Raw Score | Weight | Contribution |
|-----------|-----------|--------|--------------|

### Market Conditions Summary
[2-3 sentences on what the data is telling us]

### Allocation Recommendation
Posture: [Capital Preservation / Low / Moderate / High / Maximum]
Deployment: [X%]
Position sizing: [concentration guidance]

### Fat Pitch Candidates (if High/Maximum)
[Top 2-3 tickers with bullish signal convergence]

### Key Risks
[What would change the conviction score downward]
```

## Quick Reference

| Task | Command |
|------|---------|
| Market structure | `trader strategies signals --tickers SPY,QQQ,IWM --strategy ma_cross` |
| Distribution risk | `trader strategies signals --tickers SPY,QQQ --strategy rsi` |
| Signal convergence | `trader strategies signals --tickers SPY --strategy macd` |
| Macro sentiment | `trader news sentiment SPY --lookback 7d` |
| Setup scan | `trader strategies signals --tickers AAPL,MSFT,NVDA,GOOGL,AMZN --strategy rsi` |
| Account readiness | `trader account balance` |

## Common Mistakes

- **Scoring without running sector-analyst first** — Component 5 (Theme Quality) requires sector-analyst output. Run it first.
- **Forcing a conviction score in a Wait & Observe environment** — A 45 score means do less, not act more.
- **Ignoring Capital Preservation zone** — Score < 20 means cash, full stop. Don't rationalize a trade just because a setup looks good on a chart.
- **Skipping macro (Component 4)** — Even a perfect technical setup can fail if macro is adverse. Rates and Fed expectations matter.
- **Over-diversifying in Maximum zone** — Druckenmiller concentrates when right. 3-5 positions with proper sizing beats 15 positions with diluted size.
- **Not updating the score after major events** — Re-run after FOMC, major earnings, or significant price breaks. The score decays fast in volatile markets.
