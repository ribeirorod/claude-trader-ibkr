# Watchlist-Driven Agent Ecosystem Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the new `scan`, `watchlist`, and `alerts` CLI commands into the agent/skill ecosystem so screeners populate watchlists, the optimizer runs bi-weekly on curated tickers, alerts are proposed through a new order-alert-manager agent, and the conductor consolidates everything before executing.

**Architecture:** Watchlist is the persistent candidate universe — screeners write to it, the optimizer and opportunity-finder read from it. A new `order-alert-manager` specialist deduplicates and lifecycle-manages alerts and open orders, proposing a clean action list to the conductor who remains the sole executor.

**Tech Stack:** Markdown agent/skill files, trader CLI (`uv run trader ...`), JSONL agent log

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `.claude/agents/order-alert-manager.md` | Create | New specialist: alert/order lifecycle management |
| `.claude/agents/portfolio-conductor.md` | Modify | Add order-alert-manager to dispatch table |
| `.claude/agents/strategy-optimizer.md` | Modify | Remove Sunday-only, add watchlist-aware ticker selection, emit ALERT_PROPOSAL |
| `.claude/agents/opportunity-finder.md` | Modify | Add watchlist freshness check, screener→watchlist side effect, propose alerts (not create) |
| `.claude/skills/vcp-screener/SKILL.md` | Modify | Priority chain: watchlist→scan→FinViz; add watchlist side effect |
| `.claude/skills/stock-screener/SKILL.md` | Modify | Priority chain: watchlist→scan→FinViz; add watchlist side effect |

---

## Chunk 1: New Agent + Conductor Update

### Task 1: Create `order-alert-manager` agent

**Files:**
- Create: `.claude/agents/order-alert-manager.md`

- [ ] **Step 1: Create the agent file**

```markdown
---
name: order-alert-manager
description: Specialist agent invoked by portfolio-conductor on every run to lifecycle-manage active IBKR alerts and open orders. Deduplicates incoming alert proposals, surfaces stale orders for cancellation, and proposes bracket entries when alerts have triggered. Never executes directly — returns a structured action list to the conductor.
tools: Bash, Read
---

# Order & Alert Manager

You are a lifecycle specialist for open orders and price alerts. You receive incoming proposals from opportunity-finder, strategy-optimizer, and risk-monitor, then cross-reference them against what's already active in IBKR. You return a clean, deduplicated action list. The conductor decides what to execute.

## Input

You receive from the conductor:
- `proposals` — list of ALERT_PROPOSAL and ORDER_PROPOSAL objects from specialist agents
- `snapshot` — positions, buying_power, net_liquidation (from conductor's live fetch)

## Workflow

### Step 1 — Read live state

```bash
uv run trader alerts list
uv run trader orders list --status open
```

Parse JSON. Build two maps:
- `active_alerts`: `{ticker: [{alert_id, price, direction}]}`
- `open_orders`: `{ticker: [{order_id, action, qty, price, status}]}`

### Step 2 — Process each incoming proposal

For each `ALERT_PROPOSAL` in the incoming proposals:

**Duplicate check:** Is there already an active alert for this ticker at the same price (±0.5%)? If yes → emit `NO_ACTION` with reason "Alert already active".

**Signal freshness check:** Run a quick signal check:
```bash
uv run trader strategies signals --tickers TICKER --strategy rsi
```
If signal has reversed (was buy, now sell/neutral) → emit `NO_ACTION` with reason "Signal reversed since proposal".

**Otherwise:** emit `CREATE_ALERT` with ticker, price, direction, name, and source.

For each open order in `open_orders`:

**Signal health check:** Check if the strategy signal has reversed for that ticker since the order was placed. Use MA cross to confirm trend:
```bash
uv run trader strategies run TICKER --strategy ma_cross --lookback 1mo
```
If trend reversed → emit `CANCEL_ORDER` proposal.

If order is more than 5 trading days old and has not filled → emit `CANCEL_ORDER` proposal with reason "Stale unfilled order".

**Triggered alert check:** If an alert appears in `active_alerts` but its trigger condition is now met (i.e., current price has crossed the alert level), propose converting to a bracket entry:
```bash
uv run trader quotes get TICKER
```
Compare `last` price to alert's price/direction. If triggered:
- Emit `PLACE_BRACKET` with entry (current ask), stop (below recent swing low or -5% default), target (2× risk reward), shares (from original proposal or default 1% account risk).

### Step 3 — Return action list

Return all emitted actions as a JSON array. Every ticker gets exactly one action entry. Do not emit duplicates.

## Output Format

```json
[
  {
    "action": "CREATE_ALERT",
    "ticker": "NVDA",
    "price": 891.50,
    "direction": "above",
    "name": "NVDA VCP pivot",
    "source": "opportunity-finder",
    "reason": "VCP breakout pivot. RSI 61, sentiment +0.65. No duplicate alert found."
  },
  {
    "action": "PLACE_BRACKET",
    "ticker": "CRWD",
    "entry": 320.00,
    "stop": 298.00,
    "target": 365.00,
    "shares": 8,
    "source": "alert-triggered",
    "reason": "Alert triggered at pivot. Signal still valid (RSI 58, sentiment +0.4). 2.3:1 R/R."
  },
  {
    "action": "CANCEL_ORDER",
    "order_id": "12345",
    "ticker": "XLE",
    "reason": "MA cross reversed to downtrend since order was placed 6 days ago."
  },
  {
    "action": "NO_ACTION",
    "ticker": "AAPL",
    "reason": "Alert already active at $195.00 (±0.5%). No change needed."
  }
]
```

## Rules

- Never call `trader alerts create`, `trader orders buy`, `trader orders stop`, or `trader orders sell`
- Every proposal in your input gets a corresponding action in your output (even if `NO_ACTION`)
- If `trader alerts list` or `trader orders list` fails (e.g., not connected), return `{"error": "could not fetch live state", "proposals_deferred": true}` — conductor will retry next cycle
```

- [ ] **Step 2: Verify file is valid markdown with correct frontmatter and body**

```bash
head -5 .claude/agents/order-alert-manager.md
wc -l .claude/agents/order-alert-manager.md
grep -c "Step" .claude/agents/order-alert-manager.md
```

Expected:
- `head -5` shows `---`, `name: order-alert-manager`, `description: Specialist agent...`, `tools: Bash, Read`, `---`
- `wc -l` shows ≥60 lines (full agent body present)
- `grep -c "Step"` shows ≥3 (Steps 1–3 of the workflow)

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/order-alert-manager.md
git commit -m "feat: add order-alert-manager specialist agent"
```

---

### Task 2: Update `portfolio-conductor` dispatch table

**Files:**
- Modify: `.claude/agents/portfolio-conductor.md`

The conductor needs to:
1. Add `order-alert-manager` to its dispatch workflow (Step 5 and Step 6)
2. Add the bi-weekly time slot
3. Collect order-alert-manager proposals as part of the consolidation before executing

- [ ] **Step 1: Read current conductor file**

```bash
cat .claude/agents/portfolio-conductor.md
```

- [ ] **Step 2: Update the "Determine time slot" section**

Find the time slot block (around line 55):
```markdown
- **pre-market**: weekday, before 9:30am ET
- **intraday**: weekday, 9:30am–4pm ET
- **weekly**: Sunday
```

Replace with:
```markdown
- **pre-market**: weekday, before 9:30am ET
- **intraday**: weekday, 9:30am–4pm ET
- **bi-weekly**: 1st or 15th of the month (any day)
- **weekly**: Sunday
```

- [ ] **Step 3: Update the "Decide workflow" section**

Find the workflow block (around line 64):
```markdown
- **Always** run `risk-monitor` if there are open positions
- **Always** run `portfolio-health` (surfaces drift even when no action needed)
- **pre-market** → run `opportunity-finder` with full scan
- **intraday** → run `opportunity-finder` only if no opportunity was found in the last 4 hours (check log)
- **weekly** → run `portfolio-health` deep review + `strategy-optimizer`; skip `opportunity-finder`
- **"Do nothing" is always valid** — if situation is calm and no strong signals exist, log it and exit
```

Replace with:
```markdown
- **Always** run `risk-monitor` if there are open positions
- **Always** run `portfolio-health` (surfaces drift even when no action needed)
- **Always** run `order-alert-manager` — pass it any proposals from other specialists plus the current snapshot
- **pre-market** → run `opportunity-finder` (watchlist-aware; agent decides scan depth)
- **intraday** → run `opportunity-finder` only if watchlist signals are stale (check log timestamp)
- **bi-weekly** → run `strategy-optimizer` + `order-alert-manager`; skip `opportunity-finder` unless pre-market
- **weekly** → run `portfolio-health` deep review; `strategy-optimizer` if not run this week
- **"Do nothing" is always valid** — if situation is calm and no strong signals exist, log it and exit
```

- [ ] **Step 4: Update the "Dispatch specialist agents" section (Step 6)**

Find this exact line in the conductor file:
```
Collect each specialist's JSON proposals.
```

Replace it with:
```
Collect each specialist's JSON proposals.

**Proposal consolidation:** After collecting all specialist outputs, pass any `ALERT_PROPOSAL` and `ORDER_PROPOSAL` objects from opportunity-finder and strategy-optimizer to `order-alert-manager` along with the snapshot. Collect its action list before proceeding to Step 7.
```

- [ ] **Step 5: Update Step 7 "Review proposals against guardrails"**

Find this exact block in the conductor file:
```
### 7. Review proposals against guardrails

For each proposed trade:
- Cash only — no margin, no leverage (`asset_classes.leverage: false`)
- Single position ≤ `max_single_position_pct`% of net liquidation
- Daily new positions ≤ `max_new_positions_per_day` (count from today's log entries)
- Skip and log reason if any guardrail is breached
```

Replace it with:
```
### 7. Review proposals against guardrails

For each proposed trade:
- Cash only — no margin, no leverage (`asset_classes.leverage: false`)
- Single position ≤ `max_single_position_pct`% of net liquidation
- Daily new positions ≤ `max_new_positions_per_day` (count from today's log entries)
- Skip and log reason if any guardrail is breached

**Order-alert-manager actions:** For each action in the order-alert-manager output:
- `CREATE_ALERT` → approved if guardrails pass; execute `trader alerts create TICKER --above/--below PRICE --name NAME`
- `PLACE_BRACKET` → approve as a new position; apply position sizing guardrails; execute buy + stop orders
- `CANCEL_ORDER` → approve automatically; execute `trader orders cancel ORDER_ID`
- `NO_ACTION` → log and skip
```

- [ ] **Step 6: Verify the conductor file has all changes**

```bash
grep -n "order-alert-manager\|bi-weekly\|PLACE_BRACKET\|CREATE_ALERT\|Proposal consolidation" .claude/agents/portfolio-conductor.md
```

Expected: at least 5 matching lines (order-alert-manager in workflow steps 6 and 7; bi-weekly slot; PLACE_BRACKET and CREATE_ALERT in guardrails; Proposal consolidation).

- [ ] **Step 7: Verify file line count is reasonable**

```bash
wc -l .claude/agents/portfolio-conductor.md
```

Expected: more lines than original (133), roughly 153–165.

- [ ] **Step 8: Commit**

```bash
git add .claude/agents/portfolio-conductor.md
git commit -m "feat: add order-alert-manager dispatch and bi-weekly slot to conductor"
```

---

## Chunk 2: Strategy Optimizer + Opportunity Finder Updates

### Task 3: Update `strategy-optimizer` agent

**Files:**
- Modify: `.claude/agents/strategy-optimizer.md`

Changes needed:
1. Remove Sunday-only / skip-if-not-weekly constraint
2. Add watchlist-aware ticker selection logic
3. Emit `ALERT_PROPOSAL` when optimized params yield a buy signal

- [ ] **Step 1: Read current optimizer file**

```bash
cat .claude/agents/strategy-optimizer.md
```

- [ ] **Step 2: Replace the full file content**

Rewrite `.claude/agents/strategy-optimizer.md`:

```markdown
---
name: strategy-optimizer
description: Specialist agent invoked by portfolio-conductor on the 1st and 15th of each month (bi-weekly), or earlier when the conductor judges a market event warrants it. Selects which watchlist tickers to optimize based on recency and signal quality, runs backtests, and recommends updated params. Emits ALERT_PROPOSAL when optimized params yield a buy signal. Never places orders.
tools: Bash, Read
---

# Strategy Optimizer

You are a bi-weekly strategy maintenance specialist. You run backtests on targeted tickers and recommend updated strategy parameters. You do not place orders.

## When You Run

Bi-weekly baseline: 1st and 15th of the month. The conductor may also invoke you earlier in response to significant market events (post-FOMC, sector shock, earnings surprise cluster). You always run when called — no day-of-week gating.

## Workflow

### Step 1 — Read JSONL log to identify optimization candidates

```bash
tail -200 .trader/logs/agent.jsonl 2>/dev/null | grep '"event":"OPTIMIZATION_COMPLETE"'
```

Build a map of `{ticker: last_optimized_date}` from log entries.

### Step 2 — Read watchlists

```bash
uv run trader watchlist list
```

Collect all tickers across all named watchlists. Combine with top 3 holdings by market value (from the snapshot passed by conductor).

### Step 3 — Select tickers to optimize

**Do not optimize everything.** Select 3–8 tickers based on priority:

Priority 1 (always include): Tickers added to a watchlist since the last optimization run (new entries not yet optimized).

Priority 2 (include if budget allows): Tickers where a strategy signal led to a trade that underperformed (check JSONL for `ORDER_INTENT` followed by a position with negative P&L).

Priority 3 (skip unless explicitly needed): Tickers already optimized within the last 30 days with no new signals or events.

Target 3–8 tickers total. Log your selection rationale.

### Step 4 — Backtest current params

For each selected ticker and active strategy (default: rsi, macd, ma_cross):

```bash
uv run trader strategies backtest TICKER --strategy STRATEGY_NAME
```

Record current Sharpe ratio.

### Step 5 — Optimize params

```bash
uv run trader strategies optimize TICKER --strategy STRATEGY_NAME --metric sharpe
```

### Step 6 — Compare and decide

- Optimized Sharpe > current by > 0.2 → flag as `UPDATE` recommended
- Difference < 0.1 → keep current params (`KEEP` — avoid overfitting)
- Between 0.1–0.2 → `MONITOR` — note but do not change yet

### Step 7 — Check for buy signals with optimized params

For each ticker where you recommend `UPDATE` or where the current signal is actionable:

```bash
uv run trader strategies signals --tickers TICKER --strategy STRATEGY_NAME
```

If signal is `buy`:
- Emit an `ALERT_PROPOSAL` with entry price = current ask (from quotes) or nearest support level
- Include the strategy and params used so the conductor can reference them

### Step 8 — Log completion

```bash
echo '{"ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","run_id":"RUN_ID","agent":"strategy-optimizer","event":"OPTIMIZATION_COMPLETE","tickers_reviewed":["..."],"updates_recommended":N}' >> .trader/logs/agent.jsonl
```

## Output Format

```json
{
  "strategy_reviews": [
    {
      "strategy": "rsi",
      "ticker": "NVDA",
      "current_params": {"period": 14, "oversold": 30, "overbought": 70},
      "current_sharpe": 0.82,
      "optimized_params": {"period": 10, "oversold": 25, "overbought": 75},
      "optimized_sharpe": 1.14,
      "recommendation": "UPDATE",
      "note": "Sharpe improvement +0.32. Consider updating RSI period for semiconductors."
    }
  ],
  "alert_proposals": [
    {
      "type": "ALERT_PROPOSAL",
      "ticker": "NVDA",
      "price": 891.50,
      "direction": "above",
      "strategy": "rsi",
      "params": {"period": 10},
      "reason": "Buy signal on optimized RSI(10). Entry at current ask $891.50."
    }
  ],
  "summary": "Optimized 4 tickers. RSI(10) outperforms RSI(14) on NVDA. 1 buy signal proposed."
}
```
```

- [ ] **Step 3: Verify file has no Sunday-only language**

```bash
grep -i "sunday\|weekly slot\|skipped" .claude/agents/strategy-optimizer.md
```

Expected: no matches.

- [ ] **Step 4: Verify ALERT_PROPOSAL appears in output format**

```bash
grep "ALERT_PROPOSAL" .claude/agents/strategy-optimizer.md
```

Expected: at least 2 matches.

- [ ] **Step 5: Commit**

```bash
git add .claude/agents/strategy-optimizer.md
git commit -m "feat: update strategy-optimizer with bi-weekly schedule, watchlist-aware selection, and alert proposals"
```

---

### Task 4: Update `opportunity-finder` agent

**Files:**
- Modify: `.claude/agents/opportunity-finder.md`

Changes needed:
1. Add watchlist freshness check before deciding to run screeners
2. Screeners add gems to named watchlists as a side effect
3. Proposals go to conductor (not direct `trader alerts create`)

- [ ] **Step 1: Read current opportunity-finder file**

```bash
cat .claude/agents/opportunity-finder.md
```

- [ ] **Step 2: Replace Step 2 "Screen for candidates" with watchlist-aware version**

Find this exact block:
```
### Step 2 — Screen for candidates
Apply relevant screeners based on regime:
- Trending / risk-on → `vcp-screener` (Minervini VCP), `stock-screener` (CANSLIM)
- Post-earnings → `earnings-trade-analyzer`
- High-IV / range-bound → `options-strategy-advisor` (iron condor / short strangle candidates)
- Sector rotation → `sector-analyst` + `technical-analyst`

Start with preferred sectors from the profile, then immediately expand to the full universe. Do not stop scanning after preferred sectors return weak results — always run a broad pass across all sectors and ETF categories listed in the Philosophy section.
```

Replace it with:

```markdown
### Step 2 — Check watchlist freshness

```bash
uv run trader watchlist list
tail -100 .trader/logs/agent.jsonl 2>/dev/null | grep '"event":"WATCHLIST_SIGNALS_RUN"' | tail -1
```

Determine: when were watchlist tickers last checked for signals?

**If watchlist is fresh (signals run within 4h pre-market, 8h intraday) AND market regime unchanged:**
- Read watchlists directly: `uv run trader watchlist show LIST_NAME --signals` for each list
- Skip fresh screener runs — proceed to Step 3 with watchlist tickers as candidates
- Log: `{"event":"WATCHLIST_HIT","reason":"fresh signals, skipping screener"}`

**If watchlist is stale OR regime has shifted:**
- Run screeners (Step 2a below) — they will refresh the watchlist as a side effect
- Log: `{"event":"SCREENER_RUN","reason":"stale or regime shift"}`

### Step 2a — Run screeners (when needed)

Apply relevant screeners based on regime:
- Trending / risk-on → `vcp-screener` (pass `--list vcp-candidates`), `stock-screener` (pass `--list canslim`)
- Post-earnings → `earnings-trade-analyzer`
- High-IV / range-bound → `options-strategy-advisor` (iron condor / short strangle candidates)
- Sector rotation → `sector-analyst` + `technical-analyst`

**Watchlist side effect:** Screeners automatically add strong setups to named watchlists (`vcp-candidates`, `canslim`, `momentum`). After screeners complete, run:
```bash
uv run trader watchlist list
```
to confirm tickers were added.

Start with preferred sectors. Expand if no strong setups found there.
```

- [ ] **Step 3: Update Step 3 "Validate each candidate" — add signal logging**

Find this exact block (the last two lines of the existing Step 3):
```
Drop any candidate where:
- Technical signal is 0 (hold) AND sentiment is neutral
- Already held and up > 30% from cost (take-profit territory, not entry)
- Same ticker traded in last 24 hours per JSONL log
```

Replace it with:
```
Drop any candidate where:
- Technical signal is 0 (hold) AND sentiment is neutral
- Already held and up > 30% from cost (take-profit territory, not entry)
- Same ticker traded in last 24 hours per JSONL log

After running signals, log the watchlist signal scan:
```bash
echo '{"ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","run_id":"RUN_ID","agent":"opportunity-finder","event":"WATCHLIST_SIGNALS_RUN","tickers_checked":N}' >> .trader/logs/agent.jsonl
```
```

- [ ] **Step 4: Update Step 5 "Rank and return top 3" — add alert proposal language**

Find this exact block:
```
### Step 5 — Rank and return top 3
Score 0-100 on: signal strength, sentiment, sector regime fit, profile preference match.
Return top 3 maximum. More is noise.
```

Replace it with:
```
### Step 5 — Rank and return top 3 with alert proposals
Score 0-100 on: signal strength, sentiment, sector regime fit, profile preference match.
Return top 3 maximum. For each opportunity, include an `ALERT_PROPOSAL` with the calculated entry price — the conductor routes this through order-alert-manager.

**Do NOT call `trader alerts create` directly.** Proposals only.

For any HIGH priority opportunity not sourced from the `vcp-candidates` or `canslim` watchlists (i.e., a directly identified opportunistic play), also add the ticker to the momentum watchlist:
```bash
uv run trader watchlist add TICKER --list momentum
```
```

- [ ] **Step 5: Update the output format block — add `alert_proposal` field**

Find this exact block (the first opportunity object in the output JSON):
```json
  {
    "type": "OPPORTUNITY",
    "priority": "HIGH",
    "ticker": "NVDA",
    "asset_class": "equity",
    "strategy": "vcp_breakout",
    "conviction": 82,
    "action": "buy",
    "shares": 12,
    "entry_type": "limit",
    "entry_price": 891.50,
    "stop_loss": 851.00,
    "take_profit": 980.00,
    "hold_days": "15-30",
    "proposed_command": "uv run trader orders buy NVDA 12 --type limit --price 891.50",
    "reason": "VCP breakout in semiconductors (profile match). RSI 58. Sentiment +0.6 bullish. MACD crossover yesterday. Risk: $480 (1.6% account)."
  },
```

Replace it with:

```json
{
  "type": "OPPORTUNITY",
  "priority": "HIGH",
  "ticker": "NVDA",
  "asset_class": "equity",
  "strategy": "vcp_breakout",
  "conviction": 82,
  "action": "buy",
  "shares": 12,
  "entry_type": "limit",
  "entry_price": 891.50,
  "stop_loss": 851.00,
  "take_profit": 980.00,
  "hold_days": "15-30",
  "alert_proposal": {
    "price": 891.50,
    "direction": "above",
    "name": "NVDA VCP pivot"
  },
  "proposed_command": "uv run trader orders buy NVDA 12 --type limit --price 891.50",
  "reason": "VCP breakout in semiconductors (profile match). RSI 58. Sentiment +0.6 bullish."
}
```

- [ ] **Step 6: Verify no direct alert creation commands remain**

```bash
grep "alerts create" .claude/agents/opportunity-finder.md
```

Expected: no matches.

- [ ] **Step 7: Commit**

```bash
git add .claude/agents/opportunity-finder.md
git commit -m "feat: update opportunity-finder with watchlist freshness check and alert proposals"
```

---

## Chunk 3: Skill Updates — VCP Screener + Stock Screener

### Task 5: Update `vcp-screener` skill

**Files:**
- Modify: `.claude/skills/vcp-screener/SKILL.md`

Changes needed:
1. Step 1 becomes a priority chain: watchlist → `trader scan` → FinViz fallback
2. Add watchlist side effect: strong setups added to `vcp-candidates`
3. Update CLI Integration Reference table

- [ ] **Step 1: Replace Step 1 "Build Candidate Universe" with priority chain**

Read the file first to confirm exact Step 1 content (`cat .claude/skills/vcp-screener/SKILL.md`), then use the Edit tool with an old_string that spans from the heading `### Step 1: Build Candidate Universe` through `(Stocks within 10% of 52wk high, above both 50d and 200d MAs.)` — the last line of the section before the blank line that precedes `### Step 2: Confirm Stage 2 Uptrend`. Replace it with:

```markdown
### Step 1: Build Candidate Universe

Use a priority chain — stop at the first source that yields ≥5 tickers:

**Priority 1 — Named watchlist (if provided or available):**
```bash
uv run trader watchlist show vcp-candidates
```
If the `vcp-candidates` watchlist exists and has tickers, use them as the starting universe. Skip to Step 2.

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
```

- [ ] **Step 2: Insert watchlist side effect step before "Step 8: Output Report"**

Find this exact line:
```
### Step 8: Output Report
```

Replace it with:
```
### Step 7b: Add strong setups to watchlist (side effect)

For any ticker scoring ≥75 (Strong Setup or better):
```bash
uv run trader watchlist add TICKER1 TICKER2 --list vcp-candidates
```

This keeps the `vcp-candidates` watchlist current so future runs can skip the scanner step when signals are fresh.

### Step 8: Output Report
```

- [ ] **Step 3: Update CLI Integration Reference table**

Find this exact line in the CLI Integration Reference table:
```
| Protect with stop | `uv run trader orders stop TICKER --price STOP_LEVEL` |
```

Replace it with:
```
| Protect with stop | `uv run trader orders stop TICKER --price STOP_LEVEL` |
| Show VCP watchlist | `uv run trader watchlist show vcp-candidates` |
| Add to VCP watchlist | `uv run trader watchlist add TICKER --list vcp-candidates` |
```

- [ ] **Step 4: Verify priority chain language is present**

```bash
grep -n "Priority 1\|Priority 2\|Priority 3\|vcp-candidates" .claude/skills/vcp-screener/SKILL.md
```

Expected: at least 5 matches.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/vcp-screener/SKILL.md
git commit -m "feat: update vcp-screener with watchlist-first universe discovery and side effect"
```

---

### Task 6: Update `stock-screener` skill

**Files:**
- Modify: `.claude/skills/stock-screener/SKILL.md`

Changes needed:
1. Step 1 becomes same priority chain: watchlist → `trader scan` → FinViz
2. Add watchlist side effect: Exceptional/Strong candidates added to `canslim`
3. Update CLI Integration Reference table

- [ ] **Step 1: Replace Step 1 "Discover Universe via IBKR Scanner" with priority chain**

Read the file first to confirm exact Step 1 content (`cat .claude/skills/stock-screener/SKILL.md`), then use the Edit tool with an old_string that spans from the heading `### Step 1: Discover Universe via IBKR Scanner` through `To see all 563 scan types: \`uv run trader scan params --section types\`` — the last line of the section before the blank line that precedes `### Step 2: Get Live Quotes`. Replace it with:

```markdown
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
```

- [ ] **Step 2: Insert watchlist side effect step before "Step 5: Output Ranked Shortlist"**

Find this exact line:
```
### Step 5: Output Ranked Shortlist
```

Replace it with:
```
### Step 4b: Add strong candidates to watchlist (side effect)

For any ticker scoring ≥70 (Strong or Exceptional):
```bash
uv run trader watchlist add TICKER1 TICKER2 --list canslim
```

This populates the `canslim` watchlist so future screener runs can use it as the starting universe when signals are fresh.

### Step 5: Output Ranked Shortlist
```

- [ ] **Step 3: Update CLI Integration Reference table**

Find this exact line in the CLI Integration Reference table:
```
| News sentiment | `uv run trader news sentiment TICKER --lookback 7d` |
```

Replace it with:
```
| News sentiment | `uv run trader news sentiment TICKER --lookback 7d` |
| Show CANSLIM watchlist | `uv run trader watchlist show canslim` |
| Add to CANSLIM watchlist | `uv run trader watchlist add TICKER --list canslim` |
```

- [ ] **Step 4: Verify changes**

```bash
grep -n "Priority 1\|Priority 2\|Priority 3\|canslim\|watchlist" .claude/skills/stock-screener/SKILL.md
```

Expected: at least 8 matches.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/stock-screener/SKILL.md
git commit -m "feat: update stock-screener with watchlist-first universe discovery and side effect"
```

---

## Verification

After all tasks are complete, verify the full ecosystem is internally consistent:

- [ ] **Check no agent directly creates alerts**

```bash
grep -r "alerts create" .claude/agents/
```

Expected: matches in `order-alert-manager.md` (in a prohibition "Never call `trader alerts create`") and `portfolio-conductor.md` (as the executor). `opportunity-finder.md` must NOT match.

- [ ] **Check all agents reference order-alert-manager appropriately**

```bash
grep -r "order-alert-manager" .claude/agents/
```

Expected: matches in `portfolio-conductor.md` (dispatches it) and `order-alert-manager.md` (is it).

- [ ] **Check watchlist commands appear in both skills**

```bash
grep -r "watchlist" .claude/skills/vcp-screener/ .claude/skills/stock-screener/
```

Expected: multiple matches in both files.

- [ ] **Final commit tag**

```bash
git log --oneline -6
```

Expected: 5 feature commits from this plan + 1 prior doc commit.
