---
name: trader-strategies
description: Use when creating new trading strategies, adding custom metrics or indicators, or debugging/fixing existing strategy logic in this project's trader/ package.
---

# Trader Strategies

## Overview

Strategies are **pure functions**: OHLCV DataFrame in → `pd.Series[int]` out (1=buy, -1=sell, 0=hold). No I/O, no state, no broker calls inside a strategy. Data fetching and filtering happen in the CLI layer.

## Architecture at a Glance

```
yfinance OHLCV → strategy.signals(df) → pd.Series[int] → RiskFilter → CLI output
```

Key files:
| File | Purpose |
|------|---------|
| `trader/strategies/base.py` | `BaseStrategy` ABC — the contract |
| `trader/strategies/factory.py` | Registry — add new strategies here |
| `trader/strategies/rsi.py` | RSI example |
| `trader/strategies/macd.py` | MACD crossover example |
| `trader/strategies/ma_cross.py` | SMA crossover example |
| `trader/strategies/bnf.py` | Price-action breakout example |
| `trader/strategies/risk_filter.py` | Post-signal buy suppression |
| `trader/strategies/optimizer.py` | Grid search (sharpe / returns / win_rate) |
| `trader/news/sentiment.py` | Keyword sentiment scorer |

---

## Creating a New Strategy

### Step 1 — Create the strategy file

```python
# trader/strategies/my_strategy.py
import pandas as pd
from .base import BaseStrategy

class MyStrategy(BaseStrategy):
    def default_params(self) -> dict:
        return {"period": 20, "threshold": 0.01}

    def signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        close = ohlcv["close"]
        # ... compute your indicator inline with pandas ...
        signals = pd.Series(0, index=ohlcv.index)
        signals[buy_condition] = 1
        signals[sell_condition] = -1
        return signals.fillna(0).astype(int)  # ← always end with this
```

### Step 2 — Register in factory

```python
# trader/strategies/factory.py
from .my_strategy import MyStrategy

_REGISTRY = {
    "rsi": RSIStrategy,
    "macd": MACDStrategy,
    "ma_cross": MACrossStrategy,
    "bnf": BNFStrategy,
    "my_strategy": MyStrategy,  # ← add here
}
```

### Step 3 — Smoke test via CLI

```bash
uv run trader strategies run AAPL --strategy my_strategy --lookback 90d
uv run trader strategies backtest AAPL --strategy my_strategy
```

---

## Computing Metrics / Indicators

All indicators are computed **inline with pandas** — no external TA library. Patterns to follow:

### RSI (momentum oscillator)
```python
delta = close.diff()
gain = delta.clip(lower=0).rolling(period).mean()
loss = (-delta.clip(upper=0)).rolling(period).mean()
rs = gain / loss.replace(0, float("nan"))
rsi = 100 - (100 / (1 + rs))
```

### EMA / MACD
```python
ema_fast = close.ewm(span=fast, adjust=False).mean()
ema_slow = close.ewm(span=slow, adjust=False).mean()
macd_line = ema_fast - ema_slow
signal_line = macd_line.ewm(span=signal, adjust=False).mean()
```

### Rolling SMA crossover (detect the cross, not the state)
```python
fast = close.rolling(fast_window).mean()
slow = close.rolling(slow_window).mean()
prev_fast, prev_slow = fast.shift(1), slow.shift(1)
buy  = (fast > slow) & (prev_fast <= prev_slow)   # golden cross
sell = (fast < slow) & (prev_fast >= prev_slow)   # death cross
```

### Bollinger Bands
```python
sma = close.rolling(period).mean()
std = close.rolling(period).std()
upper, lower = sma + 2 * std, sma - 2 * std
```

### ATR (volatility filter)
```python
high, low = ohlcv["high"], ohlcv["low"]
tr = pd.concat([high - low,
                (high - close.shift(1)).abs(),
                (low  - close.shift(1)).abs()], axis=1).max(axis=1)
atr = tr.rolling(period).mean()
```

---

## OHLCV Contract

Data arrives from `yfinance` via the CLI layer. Expected format:
- Columns: `open, high, low, close, volume` (lowercase)
- Index: `DatetimeIndex`
- Prices: auto-adjusted (no splits/dividend distortions)
- **Do not call yfinance inside a strategy** — pure function only.

---

## Signal Contract

| Value | Meaning |
|-------|---------|
| `1` | Buy / go long |
| `-1` | Sell / go short |
| `0` | Hold (default) |

Rules:
- Return `pd.Series[int]` with **same index** as input `ohlcv`
- Always end: `return signals.fillna(0).astype(int)`
- NaNs at the head (from rolling windows) become `0` — that is correct

---

## Fixing Existing Strategies

### Common bugs

**Off-by-one in crossover** — crossover detection requires `shift(1)` on *both* series:
```python
# ❌ Wrong — fires on every bar where fast > slow
signals[fast > slow] = 1

# ✅ Correct — fires only on the cross itself
signals[(fast > slow) & (prev_fast <= prev_slow)] = 1
```

**NaN propagation killing signals** — always call `fillna(0)` before `astype(int)`:
```python
return signals.fillna(0).astype(int)
```

**Division by zero in RSI** — guard the loss=0 case:
```python
rs = gain / loss.replace(0, float("nan"))
```

**Lookahead bias** — when using rolling max/min for breakouts, always `.shift(1)`:
```python
rolling_high = high.rolling(lookback).max().shift(1)  # prior N bars, not current
```

**Wrong column names** — if yfinance returns uppercase after a download, the CLI normalizes. If testing manually, ensure columns are lowercase before passing to `signals()`.

---

## Risk Filter (post-signal)

`RiskFilter.filter()` in `risk_filter.py` may suppress a buy signal after the strategy runs:
- Sentiment score < -0.2 (bearish news) → suppressed
- Position value ≥ 5% of account → suppressed
- Sells are **never** suppressed

To test a strategy signal without the risk filter, use `strategies run` (single ticker, no filter) instead of `strategies signals`.

---

## Optimizer

Grid search over strategy params against historical data:

```bash
uv run trader strategies optimize AAPL --strategy rsi --metric sharpe
```

Available metrics: `sharpe` (default), `returns`, `win_rate`.

To add a new metric to the optimizer, edit `Optimizer._calc_metric()` in `optimizer.py` and add a new `Literal` value to the `metric` parameter.

---

## Quick Reference

| Task | Where |
|------|-------|
| New strategy file | `trader/strategies/<name>.py` |
| Register strategy | `trader/strategies/factory.py` → `_REGISTRY` |
| Inline indicator math | Inline pandas in `signals()`, no external TA lib |
| Post-signal filtering | `risk_filter.py`, not in strategy |
| Backtest performance | `optimizer.py` grid search |
| News sentiment score | `news/sentiment.py` keyword scorer |
| Run strategy | `uv run trader strategies run TICKER --strategy NAME` |
| Optimize params | `uv run trader strategies optimize TICKER --strategy NAME --metric sharpe` |
