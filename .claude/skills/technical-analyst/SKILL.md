---
name: technical-analyst
description: Use when the user wants a trend analysis, support/resistance levels, pattern recognition, or probability-weighted price scenarios for a specific ticker.
---

# Technical Analyst

## Overview

Performs chart-based technical analysis using trader CLI strategy outputs as the primary data source. Combines MA cross trend signals, RSI momentum readings, and current price/quote data to assess trend direction, identify key levels, and produce probability-weighted scenarios. Pattern recognition (higher highs/lows, support/resistance, candlestick formations) is overlaid on the quantitative signal output.

This skill does not require chart images — it derives all technical context from CLI JSON output.

---

## When to Use

- "Do a technical analysis on AAPL"
- "What's the trend for NVDA?"
- "Where is support/resistance for TSLA?"
- "Give me a bull/bear scenario breakdown for MSFT"
- "Is GOOGL in an uptrend or downtrend?"
- "Check the MA cross and RSI for [ticker]"

Do not use for:
- Fundamental or earnings analysis (use stock-screener)
- Placing orders (use trader-cli directly)
- Multi-stock screening (use stock-screener)

---

## Workflow

### Step 1: Gather Quantitative Signals

Run all three data pulls in parallel (or sequentially if needed):

```bash
# Current price, volume, 52wk range
uv run trader quotes get TICKER

# MA cross: trend direction, MA levels, crossover signals
uv run trader strategies run TICKER --strategy ma_cross --lookback 1y

# RSI: momentum, overbought/oversold
uv run trader strategies run TICKER --strategy rsi
```

Also pull recent news sentiment for context:

```bash
uv run trader news sentiment TICKER --lookback 7d
```

### Step 2: Assess Trend Direction

From `ma_cross` output, determine:

| Signal field | Interpretation |
|-------------|----------------|
| `trend: uptrend` | Price above both MAs, golden cross confirmed |
| `trend: downtrend` | Price below both MAs, death cross |
| `trend: sideways` | MAs converging, no clear direction |
| `short_ma` vs `long_ma` | Short above long = bullish structure |
| `price` vs `long_ma` | Price > long MA = above 200-period support |

Classify trend strength:
- **Strong uptrend** — Price > short MA > long MA, widening spread
- **Weak uptrend** — Price > long MA but below short MA (pullback)
- **Distribution** — Price < short MA but still > long MA (caution)
- **Downtrend** — Price < both MAs

### Step 3: RSI Momentum Assessment

From `rsi` strategy output:

| RSI Range | Interpretation |
|-----------|----------------|
| >70 | Overbought — momentum strong but watch for reversal |
| 50–70 | Bullish momentum — healthy uptrend zone |
| 30–50 | Bearish momentum — potential base-building |
| <30 | Oversold — watch for reversal signal |
| `signal: buy` | RSI crossed up through threshold |
| `signal: sell` | RSI crossed down |

Note divergences: if price makes new highs but RSI makes lower highs → bearish divergence.

### Step 4: Key Price Levels

From `quotes get` output:
- `week_52_high` / `week_52_low` — Macro range bounds
- `last` — Current price
- Compute distance to 52wk high: `(week_52_high - last) / week_52_high × 100`

From `ma_cross` output:
- `short_ma` — Near-term dynamic support/resistance
- `long_ma` — Long-term dynamic support/resistance

Derive key levels:
- **Primary resistance** — 52-week high (if not at ATH)
- **Near support** — Short MA (e.g., 50-day)
- **Major support** — Long MA (e.g., 200-day)
- **Secondary support** — Recent swing lows (use judgment from trend context)

### Step 5: Pattern Recognition Framework

Apply these pattern checks qualitatively using the trend and level data:

**Trend structure (from MA cross context):**
- Higher highs + higher lows = healthy uptrend
- Lower highs + lower lows = downtrend
- Converging highs and lows = consolidation / triangle

**Volume context (from quotes `volume`):**
- Volume spike on breakout above resistance = bullish confirmation
- Volume declining on rally = weakening momentum (distribution)
- High volume on down days = institutional selling

**Candlestick / price action signals (apply if price context available):**
- Price rejected at 52wk high multiple times = strong resistance
- Price bouncing off long MA repeatedly = reliable support
- Tight price range after advance = potential VCP / coiling (see vcp-screener skill)

### Step 6: Build Probability-Weighted Scenarios

Construct 2–4 scenarios that total 100%. Standard template:

| Scenario | Probability | Trigger | Target | Invalidation |
|----------|-------------|---------|--------|--------------|
| Base (continuation) | 40–60% | Holds above short MA + RSI 50+ | 52wk high / ATH | Close below long MA |
| Bull (breakout) | 15–30% | Break above 52wk high on volume | [next resistance / measured move] | Fails to hold breakout |
| Pullback (healthy) | 15–25% | Dip to short MA, holds | Bounce to prior high | Accelerates lower |
| Bear (breakdown) | 5–20% | Close below long MA | [support below / -15–20%] | Reclaims long MA |

Probability assignment rules:
- Assign highest probability to scenario consistent with dominant trend
- If RSI is overbought + price at 52wk high → reduce bull, increase pullback
- If trend is downtrend → bear scenario should be ≥30%
- Always include an invalidation level (where the thesis is wrong)

---

## Output Format

```
## Technical Analysis: TICKER — YYYY-MM-DD

### Trend Assessment
- Direction: [Strong Uptrend | Weak Uptrend | Sideways | Distribution | Downtrend]
- MA Structure: Price $XXX | Short MA $XXX | Long MA $XXX
- MA Cross Signal: [Golden cross / Death cross / No cross]
- RSI: [value] — [Overbought/Bullish/Bearish/Oversold]
- News Sentiment (7d): [score] — [Positive/Neutral/Negative]

### Key Levels
| Level | Price | Type |
|-------|-------|------|
| 52wk High | $XXX | Primary resistance |
| Short MA | $XXX | Near support |
| Long MA | $XXX | Major support |
| 52wk Low | $XXX | Macro floor |

### Pattern Notes
[2–4 bullet observations: trend structure, volume, price action, coiling/base]

### Scenarios

| Scenario | Probability | Trigger | Target | Invalidation |
|----------|-------------|---------|--------|--------------|
| Base (continuation) | X% | ... | $XXX | $XXX |
| Bull (breakout) | X% | ... | $XXX | $XXX |
| Pullback | X% | ... | $XXX | $XXX |
| Bear | X% | ... | $XXX | $XXX |

### Summary
[2–3 sentences: overall read, highest-conviction scenario, key risk to watch]
```

---

## CLI Integration Reference

| Purpose | Command |
|---------|---------|
| Current price + 52wk range | `uv run trader quotes get TICKER` |
| MA trend + levels (1yr lookback) | `uv run trader strategies run TICKER --strategy ma_cross --lookback 1y` |
| RSI momentum | `uv run trader strategies run TICKER --strategy rsi` |
| News sentiment context | `uv run trader news sentiment TICKER --lookback 7d` |

---

## Common Mistakes

- **Using short lookback for MA cross** — Always use `--lookback 1y` for meaningful 200-period MA computation.
- **Treating RSI in isolation** — RSI >70 in a strong uptrend is normal; pair with MA cross trend for context.
- **Skipping the invalidation level** — Every scenario needs a clear price where it is wrong. This prevents scenario drift.
- **Over-specifying targets without data** — Only state price targets you can derive from the CLI output (52wk levels, MA values). Do not invent arbitrary Fibonacci levels.
- **Ignoring news sentiment** — A -0.8 sentiment score during an otherwise bullish technical setup is a meaningful warning; mention it as a risk factor.
- **Assigning equal probabilities** — Scenarios should reflect the dominant trend. Equal weighting signals insufficient analysis.
