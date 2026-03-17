---
name: sector-analyst
description: Use when the user asks about sector rotation, which sectors are leading or lagging, what phase of the market cycle we are in, or whether to add cyclical vs defensive exposure. Produces a risk regime score and 2-4 probability-weighted scenarios using MA cross signals and sentiment across the 11 SPDR sector ETFs.
---

# Sector Analyst

## Overview

Assesses sector rotation patterns and market cycle phase using MA cross trend signals and news sentiment across all 11 SPDR sector ETFs. Outputs a risk regime score, uptrend ratio, and 2-4 forward scenarios with probability weights.

## When to Use

- "Which sectors are in an uptrend right now?"
- "Are we in a risk-on or risk-off environment?"
- "Should I rotate from tech into energy?"
- "What phase of the market cycle are we in?"
- "Is the market breadth improving or deteriorating?"

## Sector ETF Reference

**Signal ETFs (SPDR — for trend/sentiment signals only; NOT tradeable from EU account due to MiFID II):**

| Sector | Signal ETF | Characteristic |
|--------|-----------|----------------|
| Technology | XLK | Cyclical / Growth |
| Financials | XLF | Cyclical / Rate-sensitive |
| Energy | XLE | Cyclical / Commodity-linked |
| Healthcare | XLV | Defensive |
| Industrials | XLI | Cyclical / Late-cycle |
| Consumer Discretionary | XLY | Cyclical / Growth |
| Consumer Staples | XLP | Defensive |
| Utilities | XLU | Defensive / Rate-sensitive |
| Materials | XLB | Cyclical / Commodity-linked |
| Real Estate | XLRE | Rate-sensitive |
| Communication Services | XLC | Cyclical / Growth |

**Tradeable UCITS equivalents (LSE/XETRA-listed — use these to execute rotations):**

| Signal ETF | UCITS Equivalent | Exchange | Notes |
|-----------|-----------------|----------|-------|
| XLK / QQQ (tech) | EQQQ | LSE | Nasdaq 100, acc |
| XLE (energy) | XLES | XETRA | S&P Energy Select Sector, acc |
| Broad US market | CSPX | LSE | S&P 500, acc |
| Global / diversified | IWDA | LSE | MSCI World, acc |
| Europe | IMEU | LSE | MSCI Europe, acc |
| Emerging Markets | EMIM | LSE | MSCI EM, acc |
| Gold / commodity | SGLN | LSE | Physical gold, acc |
| Bonds (safe haven) | IBTA | LSE | US Treasuries 1-3yr, acc |
| REITs | IUES | LSE | FTSE EPRA/NAREIT, acc |

Use SPDR tickers for reading signals; translate to UCITS tickers for any actual buy/sell orders.

## CLI Integration

### Step 1 — Pull MA Cross Trend Signals (All Sectors)

```bash
uv run trader strategies signals \
  --tickers XLK,XLF,XLE,XLV,XLI,XLY,XLP,XLU,XLB,XLRE,XLC \
  --strategy ma_cross
```

Parse output: for each ticker, note signal direction (`bullish` / `bearish` / `neutral`) and signal strength.

### Step 2 — Sentiment Overlay (Per Sector ETF)

```bash
# Run for each sector ETF of interest, or the top/bottom 3 by signal strength
uv run trader news sentiment XLK --lookback 7d
uv run trader news sentiment XLE --lookback 7d
uv run trader news sentiment XLF --lookback 7d
uv run trader news sentiment XLV --lookback 7d
uv run trader news sentiment XLU --lookback 7d
```

Sentiment score: -1.0 (bearish) → +1.0 (bullish). Combine with trend signal to build conviction.

### Step 3 — Market Breadth Check

```bash
# Benchmark ETF trends to anchor regime (signal reading only — not tradeable from EU account)
uv run trader strategies signals --tickers SPY,QQQ,IWM --strategy ma_cross
uv run trader strategies signals --tickers SPY,QQQ,IWM --strategy rsi
# Cross-check with EU-tradeable equivalents
uv run trader strategies signals --tickers CSPX,EQQQ,IWDA --strategy ma_cross
```

IWM (small caps) leading SPY = early-cycle signal. IWM lagging = late-cycle or risk-off.
Use CSPX/EQQQ/IWDA signals if IBKR doesn't provide data on SPY/QQQ/IWM from EU account.

### Step 4 — Individual Stock Confirmation (Optional)

```bash
# Spot-check leading stocks within a sector
uv run trader strategies signals --tickers NVDA,AMD,AVGO --strategy ma_cross  # XLK leaders
uv run trader strategies signals --tickers XOM,CVX,COP --strategy ma_cross    # XLE leaders
```

## Uptrend Ratio and Risk Regime Scoring

### Uptrend Ratio

```
Uptrend Ratio = (# sector ETFs with bullish MA cross signal) / 11

≥ 0.73 (8+/11) → Strong Bull
0.55–0.72 (6-7/11) → Moderate Bull
0.36–0.54 (4-5/11) → Transitional / Mixed
≤ 0.35 (0-3/11) → Risk-Off / Bear
```

### Risk Regime Score (0–100)

Weighted composite:

| Factor | Weight | Source |
|--------|--------|--------|
| Uptrend ratio | 40% | MA cross signals |
| Cyclical vs Defensive ratio | 25% | XLK+XLF+XLE+XLI+XLY vs XLV+XLP+XLU |
| Benchmark breadth (SPY/QQQ/IWM) | 20% | MA cross on benchmarks |
| Sentiment overlay | 15% | `news sentiment` on sector ETFs |

```
Score 70–100 → Risk-On: favor cyclicals (XLK, XLY, XLF, XLE)
Score 40–69  → Mixed: balanced exposure, watch for rotation signals
Score 0–39   → Risk-Off: favor defensives (XLV, XLP, XLU) or cash
```

## Market Cycle Phases

Match uptrend ratio + cyclical/defensive pattern to phase:

| Phase | Description | Leading Sectors | Lagging |
|-------|-------------|-----------------|---------|
| Early Recovery | Rates falling, cyclicals waking | XLF, XLY, XLK | XLP, XLU |
| Mid Expansion | Broad uptrend, earnings-driven | XLK, XLI, XLB | XLU |
| Late Cycle | Narrowing leadership, inflation | XLE, XLB, XLI | XLY, XLK |
| Recession/Bear | Defensive rotation, falling breadth | XLV, XLP, XLU | XLE, XLY |

## 5-Step Workflow

1. **Signals** — Run `strategies signals` on all 11 sector ETFs with `ma_cross`. Record bullish/bearish counts.
2. **Sentiment** — Run `news sentiment` on top 3 and bottom 3 ETFs by signal strength. Note divergences (strong trend signal + weak sentiment = possible turn).
3. **Breadth** — Check SPY/QQQ/IWM MA cross + RSI. Assign uptrend ratio and regime score.
4. **Phase** — Map readings to market cycle phase table. Note any conflicting signals.
5. **Scenarios** — Generate 2-4 scenarios:

```
Most Likely (50-65%): [e.g., "Mid-expansion continues — XLK/XLI overweight"]
  Confirms if: [specific trigger to watch]

Alternative (20-30%): [e.g., "Late-cycle rotation to XLE/XLB"]
  Confirms if: [specific trigger]

Tail Risk (5-15%): [e.g., "Breadth collapse, defensive shift"]
  Confirms if: [specific trigger]
```

## Output Format

```
## Sector Analysis — [Date]

Risk Regime Score: [0-100] ([label])
Uptrend Ratio: [X/11] ([%])
Market Cycle Phase: [Phase]

### Sector Rankings (by MA Cross Signal Strength)
| Rank | ETF | Sector | Signal | Sentiment | Conviction |
|------|-----|--------|--------|-----------|------------|

### Cyclical vs Defensive Balance
Cyclical avg signal: [bullish/neutral/bearish]
Defensive avg signal: [bullish/neutral/bearish]

### Scenarios
[2-4 scenarios with probabilities]

### Recommended Positioning
[Overweight / Underweight / Avoid per sector]
```

## Quick Reference

| Task | Command |
|------|---------|
| All sector trend signals | `trader strategies signals --tickers XLK,XLF,XLE,XLV,XLI,XLY,XLP,XLU,XLB,XLRE,XLC --strategy ma_cross` |
| Sector sentiment | `trader news sentiment XLK --lookback 7d` |
| Benchmark breadth | `trader strategies signals --tickers SPY,QQQ,IWM --strategy ma_cross` |
| Live sector prices | `trader quotes get XLK XLF XLE XLV XLI` |

## Common Mistakes

- **Treating a single signal as a regime change** — One sector flipping bearish is noise. Require at least 3 sectors to shift before calling a rotation.
- **Ignoring sentiment divergence** — A strong bullish MA cross + deeply negative sentiment score is a warning sign, not a confirmation.
- **Confusing sector ETF moves with single stocks** — XLK can be bullish while NVDA is in a correction. Always check the ETF as representative of the sector, not a proxy for top holdings.
- **Skipping the benchmark check** — Sector analysis is meaningless without knowing if SPY/QQQ are in uptrend. Always run Step 3.
- **Assigning probabilities that don't sum to ~100%** — Scenario probabilities must be mutually exclusive and collectively exhaustive.
