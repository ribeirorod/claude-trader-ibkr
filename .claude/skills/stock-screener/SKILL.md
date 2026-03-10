---
name: stock-screener
description: Use when the user wants to screen for promising stock candidates using CANSLIM fundamentals combined with live technical signals from the trader CLI.
---

# Stock Screener

## Overview

Identifies growth stock candidates by combining CANSLIM fundamental scoring with live signals from the trader CLI. Uses `trader scan` to discover the initial universe from IBKR's live scanner, then validates each candidate with quotes, strategy signals, and news sentiment.

Two stages:
1. **Universe discovery** — `trader scan run` for IBKR live scanner results (no external services needed).
2. **Signal validation** — Live quotes + RSI signals + news sentiment via `trader` CLI, scored and ranked.

---

## When to Use

- "Screen for growth stocks"
- "Find CANSLIM setups"
- "What stocks have strong momentum right now?"
- "Show me stocks near 52-week highs with good earnings"
- "Run a stock screen and give me a ranked shortlist"

Do not use for:
- Pure value/dividend income screens
- Deep single-stock fundamental research
- Bear market conditions (RSI signals and MA cross will flag deterioration)

---

## CANSLIM Criteria (Scoring Checklist)

Each criterion scores 0–2 points (0 = fail, 1 = partial, 2 = strong). Max raw score: 14.

| Letter | Criterion | Strong (2) | Partial (1) | Fail (0) |
|--------|-----------|-----------|-------------|----------|
| C | Current quarterly EPS growth (YoY) | ≥25% | 10–24% | <10% |
| A | Annual EPS growth (3yr trend) | ≥25% CAGR | 15–24% | <15% |
| N | Near 52-week high / new product catalyst | Within 5% | 5–15% below | >15% below |
| S | Volume accumulation (up days > down days) | Ratio ≥1.5 | 1.0–1.5 | <1.0 |
| L | Relative strength vs S&P 500 (1yr) | Outperforms ≥20% | 0–20% | Underperforms |
| I | Institutional ownership trending up | Increasing | Stable | Declining |
| M | Market trend (S&P 500 above 50-day MA) | Uptrend | Sideways | Downtrend |

Composite score = (raw / 14) × 100. Bands:
- **Exceptional (85–100):** Immediate buy candidate
- **Strong (70–84):** Standard buy, await confirmation
- **Moderate (55–69):** Watchlist, buy on pullback
- **Weak (<55):** Skip or avoid

---

## Workflow

### Step 1: Discover Universe — Priority Chain

Use a priority chain — stop at the first source that yields ≥10 tickers:

**Priority 1 — Named watchlist (if provided or available):**
```bash
uv run trader watchlist show canslim
```
If the `canslim` watchlist exists and has tickers, use them as the starting universe. Skip scanner runs.

**Priority 2 — `trader scan` (live IBKR scanner):**
Run the default CANSLIM scan set and merge/deduplicate results:

```bash
# Near 52-week highs — criterion N
uv run trader scan run HIGH_VS_52W_HL \
  --price-above 10 --avg-volume-above 200000 --ema200-above --limit 30

# Momentum gainers with volume — criteria S, L
uv run trader scan run TOP_PERC_GAIN \
  --price-above 10 --avg-volume-above 500000 --mktcap-above 300 --limit 20

# Most active by dollar volume — large liquid names
uv run trader scan run MOST_ACTIVE_USD \
  --price-above 15 --ema50-above --limit 20
```

Extract `symbol` from each result. Deduplicate. Target 15–25 unique tickers for Step 2.

**Priority 3 — FinViz / web search fallback:**
If scanner is unavailable, use web search to source a universe from FinViz or similar:
```
site:finviz.com/screener "above 50-day MA" "above 200-day MA" "EPS growth"
```

**Adjust scans based on user intent:**

| User asks for... | Scan type to add |
|-----------------|-----------------|
| Earnings plays | `WSH_PREV_EARNINGS` |
| Options activity | `OPT_VOLUME_MOST_ACTIVE` or `HIGH_OPT_IMP_VOLAT` |
| Gap-up setups | `HIGH_OPEN_GAP` |
| After-hours movers | `TOP_AFTER_HOURS_PERC_GAIN` |
| ETF sector plays | `MOST_ACTIVE` with `--market ETF.EQ.US.MAJOR` |
| International | `TOP_PERC_GAIN` with `--market STK.EU.LSE` etc. |
| Weak/short setups | `TOP_PERC_LOSE` or `LOW_VS_52W_HL` |

### Step 2: Get Live Quotes

```bash
uv run trader quotes get AAPL NVDA MSFT META [... all tickers]
```

Parse the JSON output. For each ticker note:
- `last` — current price
- `bid` / `ask` — spread
- Discard tickers that return null prices (illiquid or error).

### Step 3: Run RSI Signals with News

```bash
uv run trader strategies signals \
  --tickers AAPL,NVDA,MSFT,META \
  --strategy rsi \
  --with-news
```

Parse output for each ticker:
- `signal` — `buy`, `sell`, `neutral`
- `rsi` — current RSI value (target 50–70: momentum without overbought)
- `news_sentiment` — sentiment score (-1.0 to 1.0)

### Step 4: Score CANSLIM Criteria

For each candidate, evaluate using:
- Web search for C (current EPS), A (annual EPS), I (institutional ownership)
- Scanner result for N: `HIGH_VS_52W_HL` scan members score N=2; others use distance from 52wk high
- Volume ratio from scanner + quotes for S
- `strategies signals --strategy rsi` for L (relative strength proxy)
- `strategies run TICKER --strategy ma_cross --lookback 1y` for M:

```bash
uv run trader strategies run AAPL --strategy ma_cross --lookback 1y
```

If MA cross shows `trend: uptrend` → M=2. Sideways → M=1. Downtrend → M=0.

Assign scores and calculate composite (raw/14 × 100).

### Step 4b: Add strong candidates to watchlist (side effect)

For any ticker scoring ≥70 (Strong or Exceptional):
```bash
uv run trader watchlist add TICKER1 TICKER2 --list canslim
```

This populates the `canslim` watchlist so future screener runs can use it as the starting universe when signals are fresh.

### Step 5: Output Ranked Shortlist

Present results as a ranked table, then detail each top candidate.

**Format:**

```
## Stock Screener Results — YYYY-MM-DD

### Market Condition
[S&P 500 trend assessment from MA cross — overall M score]

### Ranked Shortlist

| Rank | Ticker | Score | Rating | RSI Signal | Sentiment | Notes |
|------|--------|-------|--------|------------|-----------|-------|
| 1 | NVDA | 91 | Exceptional | buy (RSI 63) | +0.72 | Near ATH, strong EPS |
| 2 | META | 82 | Strong | buy (RSI 58) | +0.41 | Annual growth solid |
| ... | ... | ... | ... | ... | ... | ... |

### Top 3 Candidates

#### 1. NVDA — Exceptional (91/100)
- C: 2 — EPS +78% QoQ
- A: 2 — 3yr CAGR ~65%
- N: 2 — 2% from 52wk high (confirmed by HIGH_VS_52W_HL scan)
- S: 2 — Volume accumulation confirmed
- L: 2 — Outperforming SPX by 45%
- I: 1 — Institutional ownership stable-high
- M: 2 — MA cross uptrend confirmed
- RSI signal: buy (63), sentiment: +0.72
- Entry consideration: Current $XXX, look for pullback to 20-day MA

[Repeat for top 3]

### Watchlist (Moderate, 55–69)
[List with brief rationale]

### Skipped
[Tickers that returned null quotes or scored <55]
```

---

## CLI Integration Reference

| Purpose | Command |
|---------|---------|
| Scan for universe | `uv run trader scan run TYPE [--filters...]` |
| List scan types | `uv run trader scan types` |
| List markets | `uv run trader scan markets` |
| All 563 scan types | `uv run trader scan params --section types` |
| Live quotes (multi-ticker) | `uv run trader quotes get T1 T2 T3 ...` |
| RSI signals with news | `uv run trader strategies signals --tickers T1,T2 --strategy rsi --with-news` |
| Trend confirmation | `uv run trader strategies run TICKER --strategy ma_cross --lookback 1y` |
| News sentiment | `uv run trader news sentiment TICKER --lookback 7d` |
| Show CANSLIM watchlist | `uv run trader watchlist show canslim` |
| Add to CANSLIM watchlist | `uv run trader watchlist add TICKER --list canslim` |

---

## Common Mistakes

- **Too many tickers in signals** — `strategies signals` works best with ≤15 tickers. Split into batches if needed.
- **RSI overbought confusion** — RSI >70 is not automatically bad in a momentum screen; check MA cross for trend health.
- **Skipping M criterion** — If S&P 500 is in a downtrend, CANSLIM recommends raising cash. Do not force buys.
- **Scanner returns micro-caps** — Add `--mktcap-above 300` and `--avg-volume-above 200000` to filter junk.
- **News sentiment without context** — A negative score on a strong-fundamentals stock may be short-term noise; weight it lightly vs. the composite.
- **Comma-separated tickers** — `--tickers` takes comma-separated values: `AAPL,MSFT` (no spaces).
