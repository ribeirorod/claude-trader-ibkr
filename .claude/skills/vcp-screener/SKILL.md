---
name: vcp-screener
description: Use when the user wants to find Volatility Contraction Pattern (VCP) setups — Stage 2 uptrend stocks with contracting volatility near a breakout pivot, à la Mark Minervini.
---

# VCP Screener

## Overview

Identifies Mark Minervini's Volatility Contraction Pattern (VCP) using trader CLI outputs. A VCP is a base formed after a Stage 2 uptrend advance: price pulls back in a series of progressively tighter contractions (lower correction depth, shrinking price swings), creating a pivot point just before a potential breakout.

No external scripts or APIs required — the trader CLI covers trend, price, and sentiment data.

---

## When to Use

- "Find VCP setups"
- "Screen for Minervini-style breakout candidates"
- "What stocks are coiling near highs?"
- "Look for tight base patterns in Stage 2 uptrends"
- "Show me stocks with volatility contraction near pivot"

Do not use for:
- Stocks in clear Stage 1 (basing) or Stage 4 (downtrend) — VCP requires Stage 2
- Bear market environments (M component red — wait for market to recover)
- Fundamental-only screening (use stock-screener)

---

## VCP Definition

A valid VCP requires all of the following:

1. **Stage 2 uptrend** — Stock is in a sustained uptrend; price above both short and long moving averages.
2. **Series of contractions** — At least 2–3 pullbacks where each correction is shallower than the prior (e.g., -15%, -10%, -5%).
3. **Volume contraction** — Volume dries up during the tightening phase (declining volume on down days).
4. **Pivot point** — Price compresses to a tight range (<5% wide) near the highs of the base.
5. **Proximity to pivot** — Current price within 5–8% of the base high / pivot.

---

## VCP Score (0–100)

Score each criterion and sum for a composite VCP score.

| Criterion | Points | How to Assess |
|-----------|--------|---------------|
| Stage 2 uptrend confirmed (MA cross) | 0–25 | `ma_cross` trend = uptrend: 25; sideways: 10; downtrend: 0 |
| Price proximity to 52wk / base high | 0–20 | Within 5%: 20; 5–10%: 12; 10–15%: 5; >15%: 0 |
| Contraction count (≥2 tighter pullbacks) | 0–20 | 3+ contractions: 20; 2: 12; 1: 5; 0: 0 |
| Volume dry-up near pivot | 0–15 | Confirmed via quotes volume vs average: low vol = 15; avg vol = 7; high vol = 0 |
| RSI in healthy range (45–65) | 0–10 | 50–65: 10; 45–50: 6; <45 or >70: 0 |
| News sentiment neutral-to-positive | 0–10 | ≥+0.2: 10; -0.2 to +0.2: 5; <-0.2: 0 |

**Rating bands:**
- **Textbook VCP (90–100):** All criteria near-perfect. High-conviction entry at pivot break.
- **Strong Setup (75–89):** Minor weakness in one criterion. Enter on volume confirmation.
- **Developing (60–74):** 1–2 criteria incomplete. Add to watchlist, revisit in 1–2 weeks.
- **No Setup (<60):** VCP conditions not present. Do not trade.

---

## Workflow

### Step 1: Build Candidate Universe

Use a priority chain — stop at the first source that yields ≥5 tickers:

**Priority 1 — Named watchlist (if provided or available):**
```bash
uv run trader watchlist show vcp-candidates
```
If the command returns a JSON object with a `quotes` array (not an `error` key), use those tickers as the starting universe and skip to Step 2. If the command returns `{"error": ...}` or exits non-zero (watchlist empty or missing), fall through to Priority 2.

**Priority 2 — `trader scan` (live IBKR scanner):**
Run two scans and merge results:
```bash
# Near 52-week highs above all MAs — classic VCP setup territory
uv run trader scan run HIGH_VS_52W_HL \
  --ema200-above --avg-volume-above 200000 --price-above 10 --limit 30

# Tight recent gainers with volume — catches emerging VCPs
uv run trader scan run TOP_PERC_GAIN \
  --ema50-above --ema200-above --mktcap-above 300 --limit 20
```

Extract `symbol` from results. Deduplicate. Target 10–20 unique tickers.

**Priority 3 — FinViz fallback (if scanner unavailable):**
Use web search for current FinViz screens:
```
site:finviz.com/screener "near 52-week high" "above 50-day MA" "above 200-day MA"
```

FinViz filter suggestion:
```
https://finviz.com/screener.ashx?v=111&f=cap_midover,ta_highlow52w_b0to10h,ta_sma50_pa,ta_sma200_pa&o=-volume
```
(Stocks within 10% of 52wk high, above both 50d and 200d MAs.)

### Step 2: Confirm Stage 2 Uptrend

For each candidate:

```bash
uv run trader strategies run TICKER --strategy ma_cross --lookback 6mo
```

Parse output:
- `trend: uptrend` + `price > long_ma` → Stage 2 confirmed (25 pts)
- `trend: sideways` → possibly Stage 1 or late Stage 3 (10 pts)
- `trend: downtrend` → disqualify immediately (0 pts)

Eliminate any ticker not in an uptrend. Continue only with uptrend-confirmed candidates.

### Step 3: Assess Price Proximity to Pivot

```bash
uv run trader quotes get TICKER1 TICKER2 TICKER3 [...]
```

For each ticker compute:
```
proximity_pct = (week_52_high - last) / week_52_high × 100
```

- ≤5%: 20 pts
- 5–10%: 12 pts
- 10–15%: 5 pts
- >15%: 0 pts (VCP pivot too far away — watchlist only)

### Step 4: Estimate Contraction Pattern

Assess contraction depth qualitatively from available data:
- If the stock is within 5% of its 52wk high after being up significantly from its 52wk low, it has already contracted.
- Use `ma_cross --lookback 6mo` trend description and the spread between `short_ma` and `long_ma` to estimate tightening: a narrow spread vs. a wide prior spread indicates base contraction.
- If MA spread is converging while price holds near highs → contractions likely present.
- Score 2+ contractions (20 pts) if: 52wk low is >30% below current, price is within 10% of 52wk high, and MA structure is tight.

### Step 5: Check RSI Momentum

```bash
uv run trader strategies run TICKER --strategy rsi
```

- RSI 50–65: ideal VCP zone (momentum present, not overbought) → 10 pts
- RSI 45–50: base still forming → 6 pts
- RSI <45: momentum absent → 0 pts
- RSI >70: overbought, past the ideal entry → 0 pts

### Step 6: Check News Sentiment

```bash
uv run trader news sentiment TICKER --lookback 7d
```

- Score ≥+0.2: positive sentiment confirmation → 10 pts
- Score -0.2 to +0.2: neutral → 5 pts
- Score <-0.2: negative news risk → 0 pts

Note: negative sentiment does not disqualify a VCP but raises the risk of a failed breakout. Flag it explicitly.

### Step 7: Score and Rank

Calculate composite VCP score (sum of all criteria). Rank candidates.

### Step 7b: Add strong setups to watchlist (side effect)

For any ticker scoring ≥75 (Strong Setup or better):
```bash
uv run trader watchlist add TICKER1 TICKER2 --list vcp-candidates
```

This keeps the `vcp-candidates` watchlist current so future runs can skip the scanner step when signals are fresh.

Also remove tickers that fail Stage 2 screening (downtrend or no VCP structure) from the watchlist to prevent stale candidates accumulating:
```bash
uv run trader watchlist remove FAILED_TICKER1 FAILED_TICKER2 --list vcp-candidates
```

### Step 8: Output Report

```
## VCP Screener Results — YYYY-MM-DD

### Market Context
[MA cross signal on SPY or summary of broad market trend]
[If downtrend: WARNING — VCP breakouts fail at elevated rates in bear markets]

### Ranked VCP Candidates

| Rank | Ticker | VCP Score | Rating | Proximity | RSI | Sentiment |
|------|--------|-----------|--------|-----------|-----|-----------|
| 1 | NVDA | 92 | Textbook | 3.1% from pivot | 61 | +0.65 |
| 2 | CRWD | 81 | Strong | 6.4% from pivot | 57 | +0.31 |
| 3 | AXON | 68 | Developing | 11.2% from pivot | 52 | +0.08 |

### Textbook / Strong Setups — Detail

#### 1. NVDA — Textbook VCP (92/100)
- Stage 2: Confirmed (uptrend, price > both MAs)
- Proximity: $XXX — 3.1% from pivot ($XXX 52wk high)
- Contractions: 3 estimated (wide-to-tight base structure)
- Volume: Dry-up confirmed (current vol below average)
- RSI: 61 — healthy momentum zone
- Sentiment: +0.65 — positive news backdrop
- Pivot entry: $XXX (52wk high break on volume)
- Stop: below short MA ($XXX) — [X]% risk
- Target: [measured move or next resistance]

[Repeat for each Strong setup]

### Developing Setups (Watchlist)
[List with brief note — check again in 1–2 weeks]

### Eliminated
[Tickers removed: reason (downtrend / too far from pivot / RSI failed)]
```

---

## CLI Integration Reference

| Purpose | Command |
|---------|---------|
| Stage 2 trend confirmation | `uv run trader strategies run TICKER --strategy ma_cross --lookback 6mo` |
| Price proximity to pivot | `uv run trader quotes get TICKER` |
| RSI momentum check | `uv run trader strategies run TICKER --strategy rsi` |
| News sentiment | `uv run trader news sentiment TICKER --lookback 7d` |
| Place pivot breakout order | `uv run trader orders buy TICKER QTY --type limit --price PIVOT` |
| Protect with stop | `uv run trader orders stop TICKER --price STOP_LEVEL` |
| Show VCP watchlist | `uv run trader watchlist show vcp-candidates` |
| Add to VCP watchlist | `uv run trader watchlist add TICKER [TICKER2 ...] --list vcp-candidates` |

---

## Common Mistakes

- **Entering a VCP in a downtrend market** — Check SPY/QQQ MA cross first. VCP breakouts fail at >50% rate in bear markets.
- **Buying before the pivot break** — VCP entry is on the breakout above the pivot, ideally with volume surge. Anticipating before the break is premature.
- **Ignoring RSI >70** — If RSI is already overbought at the supposed pivot, the setup is late. The base needs more time to form.
- **Wide stop-loss** — VCP setups should have tight stops (below the base low or short MA). A stop >8% means the base is not tight enough.
- **No volume confirmation** — A pivot breakout on below-average volume is a weak signal. Wait for volume to confirm or reduce position size.
- **Treating 52wk high as automatic pivot** — The pivot is the high of the base (last contraction high), which may be below the 52wk high if the stock pulled back sharply from its ATH.
