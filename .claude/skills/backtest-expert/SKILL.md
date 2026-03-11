---
name: backtest-expert
description: Use when validating a trading strategy through backtesting, stress-testing parameters, evaluating out-of-sample performance, or deciding whether to deploy, refine, or abandon a strategy using `trader strategies backtest` and `trader strategies optimize`.
---

# Backtest Expert

## Overview

Systematic methodology for validating trading strategies via our CLI's `trader strategies backtest` and `trader strategies optimize` commands. Emphasizes robustness over optimism — the goal is to find strategies that "break the least" under adversity, not those that look best on paper. Produces a final verdict: **Deploy / Refine / Abandon**.

**Scope:** Applies only to rule-based, systematic strategies (rsi, macd, ma_cross, bnf). Not suitable for discretionary trade review.

## When to Use

- User wants to know if a strategy is worth trading live
- User has a new strategy idea and wants to validate it
- User is choosing between strategies or parameter sets
- A live strategy is underperforming and needs re-evaluation
- User asks "is this strategy curve-fit?"

## CLI Integration

```bash
# Core backtest
trader strategies backtest AAPL --strategy rsi --from 2020-01-01

# Optimize parameters (searches for best settings)
trader strategies optimize AAPL --strategy rsi --metric sharpe
trader strategies optimize AAPL --strategy rsi --metric returns
trader strategies optimize AAPL --strategy rsi --metric win_rate

# Multi-ticker validation (run individually)
trader strategies backtest MSFT --strategy rsi --from 2020-01-01
trader strategies backtest SPY  --strategy rsi --from 2020-01-01
trader strategies backtest QQQ  --strategy rsi --from 2020-01-01

# Live signal check to compare backtest behavior vs current
trader strategies signals --tickers AAPL --strategy rsi
trader strategies run AAPL --strategy rsi --lookback 90d
```

Available strategies: `rsi`, `macd`, `ma_cross`, `bnf`
Available metrics: `sharpe`, `returns`, `win_rate`

## Five-Phase Workflow

### Phase 1 — State the Hypothesis

Before running anything, write down:
- **Strategy:** which one (rsi / macd / ma_cross / bnf)?
- **Ticker universe:** single stock or multiple?
- **Expected edge:** why should this work? (e.g., "RSI mean-reversion on oversold large-caps")
- **Success criteria:** minimum Sharpe, win rate, or total return threshold to deploy

This prevents retrofitting an explanation after seeing results.

### Phase 2 — Initial Backtest

```bash
trader strategies backtest AAPL --strategy rsi --from 2020-01-01
```

Record from output:
- Total return, annualized return
- Sharpe ratio (target ≥ 1.0 for deployment)
- Max drawdown (target: survivable for your risk tolerance)
- Win rate and average win/loss ratio
- Number of trades (minimum 30; prefer 100+)
- Year-by-year breakdown if available

**Minimum data requirements:**
- At least 5 years of history (`--from 2020-01-01` or earlier)
- At least 30 completed trades
- Test includes at least one bear market period

If the number of trades is < 30, the results are statistically unreliable — do not proceed to deploy.

### Phase 3 — Stress-Test the Parameters

Run optimize, then manually probe parameter sensitivity:

```bash
trader strategies optimize AAPL --strategy rsi --metric sharpe
```

After getting the "optimal" parameters, test deliberately worse settings to look for a performance plateau:

**Look for plateaus, not peaks.** If Sharpe = 1.4 at RSI(14) but 0.3 at RSI(12) and 0.3 at RSI(16), the strategy is over-fit. If Sharpe = 1.2–1.5 across RSI(10)–RSI(20), the edge is robust.

**Stress-test checklist:**
- [ ] Performance degrades gracefully as parameters move ±20% from optimal
- [ ] Strategy works on at least 3 different tickers (not just one)
- [ ] Performance holds in both trending and range-bound years
- [ ] Adding realistic friction (wider stops, delayed entries) doesn't eliminate edge

### Phase 4 — Out-of-Sample Validation

Split the data: use `--from` to test on a period NOT included in optimization.

```bash
# In-sample: optimize on 2020–2023
trader strategies optimize AAPL --strategy rsi --metric sharpe
# (optimization uses data from --from date to present by default)

# Out-of-sample: backtest the resulting params on a held-out earlier window
trader strategies backtest AAPL --strategy rsi --from 2018-01-01
# Compare 2018-2019 results vs 2020-2023 optimized results
```

Out-of-sample Sharpe should be within ~0.3 of in-sample. A larger degradation signals curve-fitting.

### Phase 5 — Multi-Ticker Validation

A strategy with genuine edge should work across similar instruments:

```bash
trader strategies backtest MSFT --strategy rsi --from 2020-01-01
trader strategies backtest SPY  --strategy rsi --from 2020-01-01
trader strategies backtest QQQ  --strategy rsi --from 2020-01-01
```

Pass: Sharpe ≥ 0.8 on most tickers tested.
Fail: Strategy only works on the one ticker it was optimized for.

## Verdict Framework

After all phases, assign one of three verdicts:

### Deploy
All of these must be true:
- Sharpe ≥ 1.0 (in-sample) and ≥ 0.7 (out-of-sample)
- ≥ 30 trades, ≥ 5 years data
- Plateau confirmed — not a parameter spike
- Works on ≥ 3 tickers
- Max drawdown is survivable at intended position size

Start with 25–50% of intended position size for the first 30 live trades.

### Refine
One or two issues, but core edge may exist:
- Sharpe 0.7–1.0, or drawdown too large
- Too few trades (< 30) — needs longer history or more tickers
- Works on some tickers but not all
- Parameter sensitivity moderate — not a spike, but not a plateau

Action: adjust parameters, test on more tickers, extend history, and re-run.

### Abandon
Any of these is disqualifying:
- Sharpe < 0.7 out-of-sample
- Performance collapses with realistic friction
- < 30 trades total — can't conclude anything
- Only works in one market regime (e.g., 2020–2021 bull only)
- Parameter spike — peak performance is a narrow island
- Look-ahead bias suspected in signal construction

## Red Flags Checklist

| Red Flag | What it means |
|----------|---------------|
| Backtest Sharpe > 3.0 | Almost certainly curve-fit |
| Performance concentrated in 1–2 years | Regime-dependent, not robust |
| < 30 trades | No statistical validity |
| Optimize → deploy same data | No out-of-sample, likely overfit |
| Works on TSLA, fails on everything else | Data-mined |
| Sharpe collapses with 1% more slippage | Not live-tradeable |

## Quick Reference

| Phase | Command |
|-------|---------|
| Initial backtest | `trader strategies backtest TICKER --strategy STRAT --from DATE` |
| Find best params | `trader strategies optimize TICKER --strategy STRAT --metric sharpe` |
| Multi-ticker check | Repeat backtest on MSFT, SPY, QQQ |
| Live comparison | `trader strategies signals --tickers TICKER --strategy STRAT` |

## Common Mistakes

- **Optimizing then backtesting the same data** — Always hold out a time period for out-of-sample testing. Run optimize on recent data; check earlier data separately.
- **Stopping at Sharpe alone** — A Sharpe of 1.5 with a 60% max drawdown is not deployable. Check drawdown against your actual position sizing.
- **Ignoring trade count** — 15 trades over 5 years tells you nothing statistically. Seek strategies that generate ≥ 100 trades for high confidence.
- **Over-optimizing metric choice** — Optimizing for `win_rate` can produce strategies that win often but lose big. Use `sharpe` as primary; cross-check with `returns` and `win_rate` for sanity.
- **Skipping multi-ticker validation** — If you only tested AAPL and plan to trade NVDA, you don't know if the edge transfers.
- **Deploying at full size immediately** — Start at half size for the first 30 live trades. Confirms live fills match backtest assumptions before scaling.
