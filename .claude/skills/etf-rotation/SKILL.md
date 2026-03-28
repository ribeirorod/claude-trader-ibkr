---
name: etf-rotation
description: Use when the user wants to evaluate ETF rotation signals, run Dual Momentum or Ivy Portfolio analysis, check UCITS ETF momentum rankings, or decide which ETF position to enter, hold, or exit. Covers EU-listed UCITS ETFs only (MiFID II — US-listed ETFs not tradeable from this EU account).
---

# ETF Rotation Advisor

## Overview

Implements two complementary systematic ETF rotation strategies using live data from the trader CLI:

1. **Dual Momentum / GEM** (Gary Antonacci) — 3-asset rotation with absolute momentum gate
2. **Ivy Portfolio GTAA** (Mebane Faber) — 10-asset rotation with 10-month SMA trend filter

All ETFs are UCITS-compliant, LSE or XETRA-listed, and tradeable from this EU account.
**No US-listed ETFs (SPY, QQQ, IWM, XLE, XLF, etc.) — MiFID II KID restriction blocks them.**

---

## UCITS ETF Universe

| Asset Class | UCITS Ticker | Exchange | Benchmark | TER | Notes |
|-------------|-------------|----------|-----------|-----|-------|
| S&P 500 | CSPX | LSE | S&P 500 | 0.07% | iShares Core, acc |
| S&P 500 (alt) | VUSA | Euronext | S&P 500 | 0.07% | Vanguard, dist |
| World | IWDA | LSE | MSCI World | 0.20% | iShares Core, acc |
| World (alt) | SWDA | LSE | MSCI World | 0.20% | iShares Core, dist |
| Nasdaq 100 | EQQQ | LSE | Nasdaq 100 | 0.30% | Invesco, acc |
| Europe | IMEU | LSE | MSCI Europe | 0.12% | iShares, acc |
| Emerging Markets | EMIM | LSE | MSCI EM | 0.18% | iShares Core, acc |
| Energy | XLES | XETRA | S&P Energy Select | 0.15% | SPDR, acc |
| Gold | SGLN | LSE | Gold spot | 0.12% | iShares Physical Gold |
| Gold (alt) | PHAU | LSE | Gold spot | 0.15% | Invesco Physical Gold |
| Aggregate Bonds | AGGH | LSE | Bloomberg Global Agg | 0.10% | iShares, acc, ~7yr duration |
| Short-term Bonds | IBTA | LSE | US Treasuries 1-3yr | 0.07% | iShares, acc, ~2yr duration |
| Long-term Bonds | IDTL | LSE | US Treasuries 20yr+ | 0.10% | iShares, acc, ~18yr duration |
| REITs | IUES | LSE | FTSE EPRA/NAREIT | 0.40% | iShares, acc |

**Primary tickers for analysis:** CSPX, IWDA, EQQQ, IMEU, EMIM, XLES, SGLN, AGGH, IBTA, IDTL, IUES

---

## Universe Source — Watchlist First

Before running any momentum calculations, read the `etf-rotation` watchlist as the primary universe:

```bash
uv run trader watchlist show etf-rotation
```

If the watchlist returns ≥5 tickers with valid quotes, use those as the universe. This ensures any ETFs added by opportunity-finder or the conductor are automatically included in rotation analysis.

If the watchlist is empty or returns fewer than 5 tickers, fall back to the canonical universe hardcoded below (CSPX, IWDA, EQQQ, IMEU, EMIM, XLES, SGLN, AGGH, IBTA, IDTL, IUES).

After completing the rotation analysis, **update the watchlist** to reflect the current rotation winners — add ETFs that passed the SMA filter with positive momentum, remove those that have been below SMA for 2+ consecutive monthly checks:

```bash
# Add new entrants / reinforce existing
uv run trader watchlist add WINNER1 WINNER2 --list etf-rotation

# Remove persistent underperformers (below 10-mo SMA 2+ months)
uv run trader watchlist remove UNDERPERFORMER --list etf-rotation
```

This keeps the `etf-rotation` watchlist as a live, momentum-filtered universe — not a static seed.

---

## Strategy 1 — Dual Momentum / GEM (3-Asset)

**Antonacci's Global Equity Momentum.** Monthly rotation between 3 assets.

**Universe:** CSPX (US equities), IWDA (international equities), IBTA (bonds — safe haven)

### Step 1 — Fetch 12-month returns (skip last month)

```bash
# Get current prices
uv run trader quotes get CSPX IWDA IBTA

# Get prices from ~252 trading days ago (12 months) and ~21 days ago (1 month)
# Use strategy backtest to compute returns over the lookback window
uv run trader strategies run CSPX --strategy ma_cross --interval 1mo --lookback 390d
uv run trader strategies run IWDA --strategy ma_cross --interval 1mo --lookback 390d
uv run trader strategies run IBTA --strategy ma_cross --interval 1mo --lookback 390d
```

**12-1 momentum formula:**
```
momentum_score = (price_now / price_12mo_ago) - (price_now / price_1mo_ago)
```

This skips the most recent month to avoid short-term reversal bias — stocks that surged last month often mean-revert.

### Step 2 — Absolute momentum gate

Compare CSPX's 12-1 momentum score to 0 (cash/bonds threshold):
- If CSPX momentum > 0 → risk-on, rotate between CSPX and IWDA (whichever scores higher)
- If CSPX momentum ≤ 0 → risk-off, move entirely to IBTA (safe haven)

This prevents equity exposure during bear markets regardless of relative rankings.

### Step 3 — Relative momentum selection

Among the two equity ETFs (CSPX, IWDA), select the one with the higher 12-1 score.

**Decision tree:**
```
CSPX_momentum > 0?
├── YES → pick MAX(CSPX_score, IWDA_score)
│         → enter/hold winner; exit other
└── NO  → exit all equity; enter/hold IBTA
```

### Step 4 — Current positions check

```bash
uv run trader positions list
```

If already holding the winner → hold (no action). If holding the loser or nothing → rotate.

---

## Strategy 2 — Ivy Portfolio GTAA (10-Asset)

**Faber's Global Tactical Asset Allocation.** Monthly rotation with trend filter.

**Universe (10 assets):** CSPX, IWDA, IMEU, EMIM, EQQQ, XLES, SGLN, AGGH, IBTA, IUES

### Step 1 — Compute 12-1 momentum for all 10 assets

```bash
uv run trader quotes get CSPX IWDA IMEU EMIM EQQQ XLES SGLN AGGH IBTA IUES
```

Rank all 10 by 12-1 momentum score (highest to lowest).

### Step 2 — Apply 10-month SMA trend filter

For each ETF, check if current price is above its 10-month SMA:

```bash
uv run trader strategies signals --tickers CSPX,IWDA,IMEU,EMIM,EQQQ,XLES,SGLN,AGGH,IBTA,IUES --strategy ma_cross
```

**SMA filter rule:**
- Price > 10mo SMA → ELIGIBLE (trend intact)
- Price < 10mo SMA → INELIGIBLE → replace allocation with IBTA (bonds as cash proxy)

Faber uses ±1% buffer to reduce whipsaws: only switch when price crosses SMA by more than 1%.

### Step 3 — Select top holdings

- Pick top 3 eligible ETFs by momentum score
- Equal-weight allocation across the 3 (or fewer if <3 pass trend filter)
- Any ETF that fails the trend filter → substitute slot goes to IBTA

**Example output:**
```
Rank 1: CSPX  score=0.23  above_SMA=yes → ELIGIBLE
Rank 2: EQQQ  score=0.19  above_SMA=yes → ELIGIBLE
Rank 3: EMIM  score=0.14  above_SMA=no  → INELIGIBLE → replaced by IBTA
Rank 4: SGLN  score=0.11  above_SMA=yes → (not in top 3)

Holdings: CSPX 33%, EQQQ 33%, IBTA 33%
```

### Step 4 — Compare to current positions

```bash
uv run trader positions list
```

For each current ETF holding:
- Still in top 3 eligible → hold
- Dropped out → sell
- New entrant → buy

---

## Bond Rotation Logic

Bonds are not monolithic — duration matters enormously. Use this rotation within the bond allocation:

| Regime | Bond ETF | Rationale |
|--------|----------|-----------|
| Risk-off / flight to safety (any uncertainty) | IBTA (1-3yr) | Lowest duration, minimal rate risk, liquid |
| Recession / rate cut cycle beginning | AGGH (~7yr) | Intermediate duration captures rate decline |
| Confirmed rate cut cycle / deflation | IDTL (20yr+) | Maximum price appreciation from falling rates |
| Uncertainty about rates | IBTA | Default safe haven; don't reach for duration |

**How to determine regime:**

```bash
uv run trader news sentiment IBTA --lookback 48h
uv run trader news sentiment AGGH --lookback 48h
# Check Fed commentary and yield curve slope
```

Signal for AGGH/IDTL rotation: Yield curve uninverting + confirmed Fed pivot language.
Default: use IBTA unless there's a clear case for extending duration.

---

## ETF-Specific Quality Checks

Before proposing any ETF entry, verify:

### 1. Bid-ask spread
```bash
uv run trader quotes get TICKER
```
Accept if spread < 0.5% of mid price. Wide spreads (>1%) indicate illiquidity — wait for better price or use limit order mid-spread.

### 2. NAV premium/discount
ETFs should trade near NAV. A premium >1% means you're overpaying; wait for it to compress or use a limit below the ask.

### 3. Accumulating vs Distributing
Prefer **accumulating (acc)** share classes for tax efficiency — dividends reinvested automatically without withholding tax event. CSPX, IWDA, IMEU, EMIM, EQQQ, XLES, SGLN, AGGH, IBTA, IUES are all accumulating.

### 4. Currency
Most UCITS ETFs are USD-denominated or hedged. IMEU is EUR-hedged. EMIM holds EM currencies internally. For a EUR-based account, IWDA (USD-denominated) introduces USD/EUR FX exposure — acceptable for global diversification.

### 5. TER (ongoing cost)
Already embedded in performance. Don't double-count. Prefer lower TER when all else equal (e.g., CSPX 0.07% vs EQQQ 0.30% — EQQQ justified only if Nasdaq outperformance expected).

---

## Execution Workflow

### Full rotation check

1. Run GEM (3-asset) first — if risk-off signal, move to IBTA and stop
2. If risk-on, run GTAA (10-asset) for diversified allocation
3. Check current positions against proposed allocation
4. Calculate rebalancing trades

### Position sizing

```bash
# Account context
uv run trader account summary
```

- Target equal-weight allocation across selected ETFs
- Max single ETF position: 40% of net liquidation (avoid concentration)
- Minimum trade size: avoid orders < 0.5% NLV (transaction costs not worth it)

### Order execution

```bash
# Check live price and spread first
uv run trader quotes get CSPX

# Place limit order at mid-price (bid-ask midpoint)
uv run trader orders buy CSPX SHARES --type limit --price MID_PRICE

# Set trailing stop for risk management (ETFs use wider trails than individual stocks)
uv run trader orders trailing-stop CSPX --trail-percent 8
```

**ETF order notes:**
- Always use limit orders — spreads can be wide at open/close
- Place during EU-US overlap (3:30–5:30pm CET) for max liquidity on LSE-listed ETFs
- Avoid first/last 30 minutes when spreads are widest

---

## Output Format

Produce a rotation report with both strategies:

```
=== ETF ROTATION REPORT — [date] ===

DUAL MOMENTUM (GEM):
  CSPX 12-1 score: +0.18 (positive → risk-on)
  IWDA 12-1 score: +0.12
  IBTA 12-1 score: +0.03
  Signal: RISK-ON — CSPX wins relative momentum
  Action: BUY CSPX / EXIT IWDA (if held)

IVY PORTFOLIO GTAA (top 3 of 10):
  Rank 1: CSPX  +0.18  above 10mo SMA ✓ ELIGIBLE
  Rank 2: EQQQ  +0.15  above 10mo SMA ✓ ELIGIBLE
  Rank 3: EMIM  +0.09  BELOW 10mo SMA ✗ → replaced by IBTA
  Rank 4: SGLN  +0.07  above 10mo SMA (not in top 3)
  Target: CSPX 33% | EQQQ 33% | IBTA 33%

CURRENT POSITIONS vs TARGET:
  CSPX: holding 8 shares (~32%) → HOLD
  EQQQ: not held → BUY ~33% allocation
  IBTA: not held → BUY ~33% allocation

BOND REGIME: IBTA (default safe haven; no confirmed rate cut cycle)

REBALANCING TRADES:
  BUY EQQQ 12 shares @ limit 385.50  [33% of NLV]
  BUY IBTA 45 shares @ limit 104.20  [33% of NLV]

COMMANDS:
  uv run trader orders buy EQQQ 12 --type limit --price 385.50
  uv run trader orders buy IBTA 45 --type limit --price 104.20
  uv run trader orders trailing-stop EQQQ --trail-percent 8
  uv run trader orders trailing-stop IBTA --trail-percent 4
```

---

## Rebalancing Frequency

- **Monthly** — run on the 1st of the month (aligned with monthly cron)
- **Intraday do not rotate** — ETF rotation is a monthly signal; ignore daily noise
- **Drift rebalancing** — if any position drifts >10% from target weight, rebalance early
- **Tax efficiency** — hold winners; only sell when momentum signal clearly reverses (reduces churn)

---

## Integration with Portfolio System

The `opportunity-finder` agent uses this skill's universe for ETF candidates. The `portfolio-conductor` invokes this skill during weekly and monthly reviews via the `sector-analyst` and `portfolio-health` agents.

**Signal handoff to conductor:**
```json
{
  "type": "ETF_ROTATION",
  "strategy": "dual_momentum + gtaa",
  "risk_on": true,
  "target_etfs": ["CSPX", "EQQQ", "IBTA"],
  "weights": {"CSPX": 0.33, "EQQQ": 0.33, "IBTA": 0.34},
  "bond_regime": "IBTA",
  "rebalancing_trades": [
    {"action": "buy", "ticker": "EQQQ", "shares": 12, "reason": "Rank 2 momentum, above SMA"},
    {"action": "buy", "ticker": "IBTA", "shares": 45, "reason": "Trend filter fallback for EMIM"}
  ]
}
```
