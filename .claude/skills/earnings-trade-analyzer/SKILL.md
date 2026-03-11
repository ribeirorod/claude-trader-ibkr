---
name: earnings-trade-analyzer
description: Use when analyzing a post-earnings gap-up stock to decide whether to buy, scoring it on gap size, volume, MA200, MA50, and pre-earnings trend. Outputs a letter grade and a buy/pass recommendation.
---

# Earnings Trade Analyzer

## Overview

Evaluates post-earnings stocks using a 5-factor weighted scoring system (0–100) and assigns a letter grade (A–D) with a buy/pass recommendation. Relies on `trader quotes get` for price and gap data. Designed for stocks that have already reported and gapped up — this is a momentum follow-through entry framework, not an event-straddle strategy.

**Decision rule:** Grade A = buy. Grade B = monitor. Grade C/D = pass.

## When to Use

- A stock just reported earnings and gapped up significantly
- User wants to know if a post-earnings gap is tradeable
- User asks "should I buy this earnings reaction?"
- Screening multiple tickers after earnings season for the strongest reactions

## CLI Integration

```bash
# Get current price and gap data
trader quotes get AAPL

# Technical signal context
trader strategies run AAPL --strategy rsi --lookback 90d
trader strategies run AAPL --strategy macd --lookback 90d
trader strategies signals --tickers AAPL --strategy ma_cross

# News — confirm earnings beat narrative
trader news latest --tickers AAPL --limit 5
trader news sentiment AAPL --lookback 24h

# If buying: use a bracket order to manage risk
trader orders bracket AAPL <QTY> --entry <PRICE> --stop-loss <STOP> --take-profit <TARGET>
```

## 5-Factor Scoring System

Score each factor 0–20. Total = composite score (0–100).

---

### Factor 1 — Gap Size (20 pts)

The gap on earnings day as a percentage of the prior close.

| Gap % | Points |
|-------|--------|
| <3% | 2 |
| 3–5% | 8 |
| 5–8% | 14 |
| 8–12% | 18 |
| >12% | 20 |

Calculate: `gap_pct = (open_price − prior_close) / prior_close × 100`

Use `trader quotes get TICKER` — compare `open` to `prev_close` fields. For intraday analysis, note that gap has already occurred; use the reported open vs prior close.

---

### Factor 2 — Volume on Earnings Day (20 pts)

Volume vs the 50-day average daily volume.

| Volume ratio | Points |
|--------------|--------|
| <1.0x | 2 |
| 1.0–1.5x | 8 |
| 1.5–2.5x | 14 |
| 2.5–4.0x | 18 |
| >4.0x | 20 |

High volume = institutional participation. Low volume gap-ups fade. Get volume from `trader quotes get`; ADV requires supplemental data (WebSearch or user-supplied).

---

### Factor 3 — Position vs MA200 (20 pts)

Where the stock is relative to its 200-day moving average at the time of earnings.

| Condition | Points |
|-----------|--------|
| Below MA200 | 0 |
| Within 5% below MA200 | 6 |
| Within 5% above MA200 | 12 |
| 5–20% above MA200 | 18 |
| >20% above MA200 (extended trend) | 20 |

Use `trader strategies signals --tickers TICKER --strategy ma_cross` — the MA200 level appears in signal output. Alternatively use `trader strategies run TICKER --strategy ma_cross --lookback 200d`.

---

### Factor 4 — Position vs MA50 (20 pts)

The stock's position relative to its 50-day moving average.

| Condition | Points |
|-----------|--------|
| Below MA50 | 0 |
| Within 2% of MA50 | 8 |
| 2–10% above MA50 | 16 |
| >10% above MA50 | 20 |

Same source: `trader strategies signals --tickers TICKER --strategy ma_cross`.

---

### Factor 5 — Pre-Earnings Trend (20 pts)

Price trend in the 4 weeks before earnings. A stock in a prior uptrend extending on earnings is very different from one that crashed and bounced.

| Condition | Points |
|-----------|--------|
| Down >10% in 4 weeks pre-earnings | 0 |
| Down 5–10% | 5 |
| Flat (±5%) | 10 |
| Up 5–15% (constructive base) | 17 |
| Up >15% (strong trend) | 20 |

Use `trader strategies run TICKER --strategy rsi --lookback 90d` and inspect the price trend in the 4 weeks leading to earnings date. Supplement with `trader news sentiment TICKER --lookback 48h` to confirm no pre-earnings leak or fade.

---

## Grade Table

| Score | Grade | Action |
|-------|-------|--------|
| 85–100 | A | Strong buy — enter with full position size |
| 70–84 | B | Watchlist — wait for pullback to gap-fill or 10-day MA |
| 55–69 | C | Mixed signals — pass unless other conviction |
| <55 | D | Avoid — gap likely to fade |

## Entry Quality Filter

Even with a Grade A score, apply these go/no-go checks:

- [ ] Gap has NOT filled intraday (price still above earnings open)
- [ ] Sentiment score from `trader news sentiment` is positive (> 0.1)
- [ ] No secondary offering or guidance-cut in news (`trader news latest`)
- [ ] Buying power available (`trader account balance`)
- [ ] Market context is not Red/Critical (run market-top-detector skill first)

## Workflow

1. Run `trader quotes get TICKER` — record open, prev_close, volume, current price.
2. Run `trader strategies signals --tickers TICKER --strategy ma_cross` — get MA50 and MA200.
3. Run `trader strategies run TICKER --strategy rsi --lookback 90d` — assess pre-earnings trend.
4. Run `trader news latest --tickers TICKER --limit 5` and `trader news sentiment TICKER --lookback 24h` — confirm narrative.
5. Score each factor. Sum total.
6. Apply entry quality filter.
7. Output grade, score breakdown, and recommended command.

## Output Format

```
Earnings Trade Analysis: AAPL  (reported 2026-03-10)

Factor Scores:
  Gap Size           (gap: +9.2%)    →  18 / 20
  Volume             (3.1x ADV)      →  18 / 20
  MA200 position     (+12% above)    →  18 / 20
  MA50 position      (+6% above)     →  16 / 20
  Pre-earnings trend (+8% prior 4wk) →  17 / 20

Composite Score: 87 / 100  →  GRADE A

Entry filter:
  [x] Gap intact    [x] Positive sentiment    [x] No dilution news
  [x] Buying power OK    [x] Market not in Red zone

Recommendation: BUY

Suggested command (after sizing via position-sizer skill):
  trader orders bracket AAPL 50 --entry 198.50 --stop-loss 191.00 --take-profit 218.00
```

## Common Mistakes

- **Buying the gap fill** — This skill is for momentum follow-through. If the stock has already filled the gap, the setup is voided. Pass.
- **Ignoring MA200** — Stocks below their 200MA that gap up often fail within 2–3 weeks. Score honestly.
- **Skipping news check** — A guidance cut or secondary offering buried in the press release will tank the trade regardless of price action.
- **Using daily close instead of earnings open** — Gap size must be measured from the earnings-day open vs prior-day close, not intraday high/low.
- **Grade B FOMO** — Grade B is "watch," not "buy now." Wait for a pullback entry or skip.
