# Autonomous Portfolio Agents — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a multi-agent autonomous portfolio management system — a `portfolio-conductor` orchestrator dispatched on cron that reads live portfolio state and JSONL history, decides which specialist agents to invoke, and executes approved orders via the trader CLI.

**Architecture:** A single Claude Code agent (`portfolio-conductor`) serves as the sole cron entry point. It builds a shared context object (snapshot + JSONL history + portfolio profile) and dispatches specialist sub-agents (`risk-monitor`, `opportunity-finder`, `portfolio-health`, `strategy-optimizer`). Only the conductor places orders. A Python utility package handles JSONL logging and context building.

**Tech Stack:** Python 3.11+, `uv`, trader CLI (`uv run trader`), Claude Code agents (`.claude/agents/*.md`), JSONL for persistent memory.

**Spec:** `docs/superpowers/specs/2026-03-10-autonomous-portfolio-agents-design.md`

---

## File Map

### New files to create

```
trader/agents/
├── __init__.py                    # package init
├── log.py                         # JSONL read/write utility
└── context.py                     # builds shared context object

.claude/agents/
├── portfolio-conductor.md         # orchestrator agent (existing dir)
├── risk-monitor.md                # specialist: position health + stops
├── opportunity-finder.md          # specialist: new trade ideas, all asset classes
├── portfolio-health.md            # specialist: allocation drift + rebalance
└── strategy-optimizer.md          # specialist: weekly backtest + param refresh

.trader/
├── profile.json                   # portfolio north star (investment preferences)
└── logs/
    └── .gitkeep                   # track directory, ignore *.jsonl

tests/agents/
├── __init__.py
├── test_log.py                    # JSONL utility tests
└── test_context.py                # context builder tests
```

### Modified files

```
.gitignore                         # add .trader/logs/*.jsonl
trader/config.py                   # add AGENT_MODE env var
```

---

## Chunk 1: Infrastructure — Profile, Log Utility, Context Builder

### Task 1: Portfolio profile + log directory

**Files:**
- Create: `.trader/profile.json`
- Create: `.trader/logs/.gitkeep`
- Modify: `.gitignore`

- [ ] **Step 1: Create `.trader/` directory structure**

```bash
mkdir -p .trader/logs
touch .trader/logs/.gitkeep
```

- [ ] **Step 2: Create `.trader/profile.json`**

```json
{
  "profile_version": "1.0",
  "last_updated": "2026-03-10",

  "risk_tolerance": "moderate",
  "time_horizon": "mid-term",
  "trading_style": {
    "day_trading": "minimal",
    "preferred_hold_days": "5-90",
    "note": "keep turnover low, favor swing and position trades"
  },

  "asset_classes": {
    "equities": true,
    "etfs": true,
    "options": true,
    "futures": true,
    "crypto": false,
    "leverage": false
  },

  "preferred_sectors": [
    "energy",
    "emerging_markets",
    "semiconductors",
    "defense"
  ],
  "sector_note": "agents may screen and invest in other sectors when signals are strong — these are starting bias, not exclusions",

  "portfolio_targets": {
    "max_single_position_pct": 10,
    "max_sector_concentration_pct": 35,
    "max_new_positions_per_day": 3,
    "target_cash_reserve_pct": 10
  },

  "options_preferences": {
    "allowed_strategies": [
      "covered_call", "cash_secured_put", "spreads",
      "iron_condor", "directional", "earnings_plays"
    ],
    "max_options_portfolio_pct": 20
  },

  "notes": "Free-form field. Update as your thesis evolves — agents read this on every run."
}
```

- [ ] **Step 3: Add log files to `.gitignore`**

Add to `.gitignore`:
```
# Agent logs (JSONL — tracked by directory, not content)
.trader/logs/*.jsonl
```

- [ ] **Step 4: Commit**

```bash
git add .trader/profile.json .trader/logs/.gitkeep .gitignore
git commit -m "feat: add portfolio profile and agent log directory"
```

---

### Task 2: JSONL log utility

**Files:**
- Create: `trader/agents/__init__.py`
- Create: `trader/agents/log.py`
- Create: `tests/agents/__init__.py`
- Create: `tests/agents/test_log.py`

- [ ] **Step 1: Write failing tests**

Create `tests/agents/__init__.py` (empty).

Create `tests/agents/test_log.py`:

```python
import json
import uuid
from pathlib import Path
import pytest
from trader.agents.log import AgentLog, LogEvent


@pytest.fixture
def log_file(tmp_path):
    return tmp_path / "agent.jsonl"


def test_write_single_event(log_file):
    log = AgentLog(log_file)
    log.write(LogEvent(
        run_id="run-1",
        agent="conductor",
        event="RUN_START",
        data={"time_slot": "pre-market"},
    ))
    lines = log_file.read_text().strip().split("\n")
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["run_id"] == "run-1"
    assert entry["agent"] == "conductor"
    assert entry["event"] == "RUN_START"
    assert entry["context"]["time_slot"] == "pre-market"
    assert "ts" in entry


def test_write_multiple_events(log_file):
    log = AgentLog(log_file)
    for i in range(3):
        log.write(LogEvent(run_id="run-1", agent="conductor", event=f"EVENT_{i}", data={}))
    lines = log_file.read_text().strip().split("\n")
    assert len(lines) == 3


def test_read_last_n(log_file):
    log = AgentLog(log_file)
    for i in range(10):
        log.write(LogEvent(run_id="r", agent="a", event=f"E{i}", data={"i": i}))
    last5 = log.read_last(5)
    assert len(last5) == 5
    assert last5[-1]["context"]["i"] == 9
    assert last5[0]["context"]["i"] == 5


def test_read_last_n_fewer_than_n_entries(log_file):
    log = AgentLog(log_file)
    log.write(LogEvent(run_id="r", agent="a", event="E0", data={}))
    result = log.read_last(50)
    assert len(result) == 1


def test_read_last_empty_file(log_file):
    log = AgentLog(log_file)
    result = log.read_last(10)
    assert result == []


def test_new_run_id_is_unique():
    id1 = AgentLog.new_run_id()
    id2 = AgentLog.new_run_id()
    assert id1 != id2
    assert len(id1) == 8  # short hex prefix
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/agents/test_log.py -v
```

Expected: `ModuleNotFoundError: No module named 'trader.agents'`

- [ ] **Step 3: Create package and implement `log.py`**

Create `trader/agents/__init__.py` (empty).

Create `trader/agents/log.py`:

```python
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_LOG_PATH = Path(".trader/logs/agent.jsonl")


@dataclass
class LogEvent:
    run_id: str
    agent: str
    event: str
    data: dict[str, Any] = field(default_factory=dict)


class AgentLog:
    def __init__(self, path: Path = DEFAULT_LOG_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: LogEvent) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": event.run_id,
            "agent": event.agent,
            "event": event.event,
            "context": event.data,
        }
        with self.path.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    def read_last(self, n: int) -> list[dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text().strip().splitlines()
        if not lines:
            return []
        tail = lines[-n:] if len(lines) >= n else lines
        return [json.loads(line) for line in tail]

    @staticmethod
    def new_run_id() -> str:
        return uuid.uuid4().hex[:8]
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/agents/test_log.py -v
```

Expected: all 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add trader/agents/ tests/agents/
git commit -m "feat: add JSONL agent log utility"
```

---

### Task 3: Context builder

**Files:**
- Create: `trader/agents/context.py`
- Create: `tests/agents/test_context.py`
- Modify: `trader/config.py`

- [ ] **Step 1: Add `AGENT_MODE` to config**

In `trader/config.py`, add to the `Config` dataclass:

```python
agent_mode: str = field(default_factory=lambda: os.getenv("AGENT_MODE", "supervised"))
agent_log_path: str = field(default_factory=lambda: os.getenv("AGENT_LOG_PATH", ".trader/logs/agent.jsonl"))
agent_profile_path: str = field(default_factory=lambda: os.getenv("AGENT_PROFILE_PATH", ".trader/profile.json"))
```

- [ ] **Step 2: Write failing tests**

Create `tests/agents/test_context.py`:

```python
import json
from pathlib import Path
import pytest
from trader.agents.context import build_context, load_profile, TimeSlot


@pytest.fixture
def profile_file(tmp_path):
    p = tmp_path / "profile.json"
    p.write_text(json.dumps({
        "risk_tolerance": "moderate",
        "preferred_sectors": ["energy", "semiconductors"],
        "portfolio_targets": {
            "max_single_position_pct": 10,
            "max_new_positions_per_day": 3,
            "target_cash_reserve_pct": 10,
        },
        "asset_classes": {"equities": True, "leverage": False},
    }))
    return p


def test_load_profile(profile_file):
    profile = load_profile(profile_file)
    assert profile["risk_tolerance"] == "moderate"
    assert "semiconductors" in profile["preferred_sectors"]


def test_load_profile_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_profile(tmp_path / "missing.json")


def test_build_context_structure(profile_file):
    ctx = build_context(
        run_id="abc123",
        time_slot=TimeSlot.PRE_MARKET,
        snapshot={"net_liquidation": 90000, "buying_power": 15000, "positions": [], "open_orders": []},
        recent_log=[],
        profile_path=profile_file,
    )
    assert ctx["run_id"] == "abc123"
    assert ctx["time_slot"] == "pre-market"
    assert ctx["snapshot"]["net_liquidation"] == 90000
    assert ctx["guardrails"]["cash_only"] is True
    assert ctx["guardrails"]["max_new_positions_per_day"] == 3
    assert ctx["profile"]["risk_tolerance"] == "moderate"


def test_guardrails_from_profile(profile_file):
    ctx = build_context(
        run_id="x",
        time_slot=TimeSlot.INTRADAY,
        snapshot={},
        recent_log=[],
        profile_path=profile_file,
    )
    assert ctx["guardrails"]["max_single_position_pct"] == 0.10
    assert ctx["guardrails"]["cash_only"] is True


def test_time_slot_values():
    assert TimeSlot.PRE_MARKET.value == "pre-market"
    assert TimeSlot.INTRADAY.value == "intraday"
    assert TimeSlot.WEEKLY.value == "weekly"
```

- [ ] **Step 3: Run tests — verify they fail**

```bash
uv run pytest tests/agents/test_context.py -v
```

Expected: `ModuleNotFoundError: No module named 'trader.agents.context'`

- [ ] **Step 4: Implement `context.py`**

Create `trader/agents/context.py`:

```python
from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any

DEFAULT_PROFILE_PATH = Path(".trader/profile.json")


class TimeSlot(Enum):
    PRE_MARKET = "pre-market"
    INTRADAY = "intraday"
    WEEKLY = "weekly"


def load_profile(path: Path = DEFAULT_PROFILE_PATH) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Portfolio profile not found: {p}")
    return json.loads(p.read_text())


def build_context(
    run_id: str,
    time_slot: TimeSlot,
    snapshot: dict[str, Any],
    recent_log: list[dict],
    profile_path: Path = DEFAULT_PROFILE_PATH,
) -> dict[str, Any]:
    profile = load_profile(profile_path)
    targets = profile.get("portfolio_targets", {})

    return {
        "run_id": run_id,
        "time_slot": time_slot.value,
        "snapshot": snapshot,
        "recent_log": recent_log,
        "profile": profile,
        "guardrails": {
            "cash_only": not profile.get("asset_classes", {}).get("leverage", False),
            "max_single_position_pct": targets.get("max_single_position_pct", 10) / 100,
            "max_new_positions_per_day": targets.get("max_new_positions_per_day", 3),
            "target_cash_reserve_pct": targets.get("target_cash_reserve_pct", 10) / 100,
        },
    }
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
uv run pytest tests/agents/test_context.py -v
```

Expected: all 5 tests PASS

- [ ] **Step 6: Run full test suite — no regressions**

```bash
uv run pytest -v
```

Expected: all tests PASS

- [ ] **Step 7: Commit**

```bash
git add trader/agents/context.py trader/config.py tests/agents/test_context.py
git commit -m "feat: add context builder and AGENT_MODE config"
```

---

## Chunk 2: Agent Files

These are Claude Code agent definitions. Each `.claude/agents/*.md` file defines one agent's identity, tools, and workflow. They are instruction documents, not code — but they must be precise.

### Task 4: `portfolio-conductor` agent

**Files:**
- Create: `.claude/agents/portfolio-conductor.md`

- [ ] **Step 1: Create conductor agent file**

Create `.claude/agents/portfolio-conductor.md`:

````markdown
---
name: portfolio-conductor
description: Autonomous portfolio orchestrator. Runs on cron schedule to assess market context, dispatch specialist agents, and execute approved trades via the trader CLI. Always reads live portfolio snapshot and JSONL history before acting. Only agent that places orders.
tools: Bash, Read, Write, Agent
---

# Portfolio Conductor

You are the autonomous portfolio orchestrator for this trading account. You run on a scheduled basis and your job is to assess the current situation, decide which analysis agents to run, collect their proposals, and execute approved orders.

**You are the only agent that places orders.** Specialists propose — you decide and execute.

## Every Run Follows This Sequence

### 1. Fetch live snapshot

```bash
uv run trader positions list
uv run trader positions pnl
uv run trader account summary
uv run trader orders list --status open
```

Parse the JSON output. Build a mental picture of: open positions, unrealized P&L, buying power, pending orders.

### 2. Read JSONL history

```bash
tail -50 .trader/logs/agent.jsonl 2>/dev/null || echo "[]"
```

Scan recent entries. What ran last? What was decided? Were orders placed recently for the same tickers? Avoid repeating the same trade within the same day unless a new signal is clearly different.

### 3. Read portfolio profile

```bash
cat .trader/profile.json
```

This is your north star. Preferred sectors, risk tolerance, asset class preferences, position limits. Guidance — not hard constraints.

### 4. Assess and decide workflow

Based on time context (what time is it? weekday? Sunday?), portfolio state, and recent log:

- **Always** run `risk-monitor` if there are open positions
- **Always** run `portfolio-health` (surfaces drift even when no action is needed)
- **Pre-market** → run `opportunity-finder` with full scan
- **Intraday** → run `opportunity-finder` only if no opportunity was found in the last 4 hours
- **Weekly (Sunday)** → run `portfolio-health` deep review + `strategy-optimizer`, skip `opportunity-finder`
- **"Do nothing" is always valid** — if the situation is calm, positions are healthy, and no strong signals exist, log it and exit cleanly

Log your workflow decision:

```bash
echo '{"ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","run_id":"RUN_ID","agent":"conductor","event":"WORKFLOW_DECISION","skills_invoked":["..."],"reason":"..."}' >> .trader/logs/agent.jsonl
```

### 5. Dispatch specialist agents

Use the Agent tool to invoke each specialist, passing the full context as part of the prompt. Include:
- The snapshot (positions, buying power, P&L)
- Recent JSONL entries
- The portfolio profile
- The guardrails

Collect each specialist's proposals as structured output.

### 6. Review proposals against guardrails

For each proposed trade:
- Cash only — no margin, no leverage
- Single position ≤ `max_single_position_pct` of net liquidation
- Daily new positions ≤ `max_new_positions_per_day` (check log for today's count)
- If a proposal would breach a guardrail, skip it and log the reason

### 7. Log intent before executing

For every approved trade, log ORDER_INTENT first:

```bash
echo '{"ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","run_id":"RUN_ID","agent":"conductor","event":"ORDER_INTENT","ticker":"TICKER","action":"buy","shares":N,"type":"limit","price":X,"reason":"..."}' >> .trader/logs/agent.jsonl
```

### 8. Execute orders

```bash
# Equity buy
uv run trader orders buy TICKER SHARES --type limit --price PRICE

# Options
uv run trader orders buy TICKER QTY --contract-type option --expiry DATE --strike PRICE --right call|put

# Stop loss on existing position
uv run trader orders stop TICKER --price PRICE

# Trim
uv run trader orders sell TICKER SHARES --type limit --price PRICE
```

### 9. Log run end

```bash
echo '{"ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","run_id":"RUN_ID","agent":"conductor","event":"RUN_END","orders_placed":N,"do_nothing":false,"duration_s":SECONDS}' >> .trader/logs/agent.jsonl
```

## Operating Mode

Check `AGENT_MODE` environment variable:
- `autonomous` (default) — execute orders automatically after logging intent
- `supervised` — log ORDER_INTENT entries but do NOT execute; halt and wait for human review

```bash
echo $AGENT_MODE
```

## What Good Looks Like

- A calm market day with healthy positions → `risk-monitor` clean, `portfolio-health` shows minor drift, `opportunity-finder` finds nothing strong → log "do nothing", exit
- A strong pre-market signal → `opportunity-finder` surfaces a VCP breakout in semiconductors (matching profile) → `position-sizer` sizes it → conductor logs intent → executes limit order
- A position down 22% → `risk-monitor` flags tail risk → conductor reviews → places stop or trims

## Skills Available to Dispatch

When invoking specialist agents, these skills are available in this project:
`portfolio-manager`, `market-top-detector`, `stanley-druckenmiller-investment`, `sector-analyst`, `technical-analyst`, `market-news-analyst`, `economic-calendar-fetcher`, `geopolitical-influence`, `stock-screener`, `vcp-screener`, `earnings-trade-analyzer`, `options-strategy-advisor`, `position-sizer`, `backtest-expert`, `trader-strategies`
````

- [ ] **Step 2: Commit**

```bash
git add .claude/agents/portfolio-conductor.md
git commit -m "feat: add portfolio-conductor agent"
```

---

### Task 5: `risk-monitor` agent

**Files:**
- Create: `.claude/agents/risk-monitor.md`

- [ ] **Step 1: Create risk-monitor agent file**

Create `.claude/agents/risk-monitor.md`:

````markdown
---
name: risk-monitor
description: Specialist agent invoked by portfolio-conductor to assess position-level health, drawdown risk, stop-loss triggers, and macro risk. Returns structured proposals for stops, trims, or no action. Never places orders directly.
tools: Bash, Read
---

# Risk Monitor

You are a specialist risk assessment agent. You receive a context object from the conductor containing the live portfolio snapshot, JSONL history, and portfolio profile. Your job is to assess risk and return structured proposals. You do not place orders.

## Input

You will receive a JSON context object with:
- `snapshot.positions` — open positions with avg_cost, market_price, unrealized_pnl_pct
- `snapshot.buying_power`
- `recent_log` — last N JSONL entries
- `profile` — portfolio preferences

## Assessment Checklist

Run through every open position:

### 1. Drawdown flags
- Position down > 10% from cost → flag as WARNING
- Position down > 20% from cost → flag as CRITICAL, propose stop-loss review
- Position down > 30% from cost → propose immediate trim or close

### 2. Macro context
Use your knowledge of these skills: `market-top-detector`, `stanley-druckenmiller-investment`

Assess:
- Is the broad market showing distribution signs?
- Is the Druckenmiller-style conviction low (< 40)?
- If yes, propose reducing exposure on weakest positions

### 3. Sector concentration
- Any single sector > 35% of portfolio → flag
- Propose trim on the largest position in that sector

### 4. Open stop-loss gaps
- Any position without a stop-loss order in `snapshot.open_orders` → flag as unprotected
- Propose `uv run trader orders stop TICKER --price PRICE` (suggest price = avg_cost × 0.92)

### 5. News check
For any CRITICAL position, note: conductor should run `uv run trader news sentiment TICKER --lookback 7d` before acting.

## Output Format

Return a JSON array of proposals:

```json
[
  {
    "type": "RISK_FLAG",
    "priority": "CRITICAL",
    "ticker": "XOM",
    "flag": "drawdown_22pct",
    "current_pnl_pct": -22.1,
    "recommendation": "review stop-loss",
    "proposed_command": "uv run trader orders stop XOM --price 85.00",
    "reason": "Position down 22% from avg_cost $110. No stop in open orders."
  }
]
```

If no risks found, return: `[]`
````

- [ ] **Step 2: Commit**

```bash
git add .claude/agents/risk-monitor.md
git commit -m "feat: add risk-monitor specialist agent"
```

---

### Task 6: `opportunity-finder` agent

**Files:**
- Create: `.claude/agents/opportunity-finder.md`

- [ ] **Step 1: Create opportunity-finder agent file**

Create `.claude/agents/opportunity-finder.md`:

````markdown
---
name: opportunity-finder
description: Specialist agent invoked by portfolio-conductor to surface new trade opportunities across equities, ETFs, options, and futures. Uses the full skill library to screen, analyze, and size ideas. Returns structured proposals. Never places orders directly.
tools: Bash, Read
---

# Opportunity Finder

You are a specialist opportunity identification agent. You receive a context object from the conductor and your job is to surface the best trade ideas right now — across any asset class the profile allows. You do not place orders. You propose.

## Input

You receive a JSON context containing:
- `snapshot` — positions, buying_power, net_liquidation
- `profile` — preferred sectors, asset classes, risk tolerance, time horizon
- `recent_log` — avoid re-proposing the same ticker traded in the last 24 hours
- `guardrails` — position sizing limits

## Philosophy

**The profile is a starting bias, not a constraint.** Begin your scan with preferred sectors (energy, emerging markets, semiconductors, defense) but follow strong signals wherever they lead. A high-conviction setup in healthcare beats a weak setup in defense.

**Match the time horizon.** The profile says mid-term (5-90 days). Avoid day trades. Favor setups with clear multi-week thesis.

**Options are not just hedges.** Consider covered calls for income on large positions, cash-secured puts on tickers you want to own, directional spreads on high-conviction moves, iron condors for range-bound high-IV situations.

## Workflow

### Step 1 — Macro filter
Assess market regime using your knowledge of `stanley-druckenmiller-investment` and `sector-analyst` skills:
- What sectors are leading?
- Is the regime risk-on or risk-off?
- Any upcoming economic events (use `economic-calendar-fetcher` knowledge) that should pause new entries?

### Step 2 — Screen for candidates
Apply relevant screeners based on regime:
- Trending / risk-on → `vcp-screener` (Minervini VCP setups), `stock-screener` (CANSLIM)
- Post-earnings → `earnings-trade-analyzer`
- High-IV / range-bound → `options-strategy-advisor` (iron condor / short strangle candidates)
- Sector rotation opportunity → `sector-analyst` + `technical-analyst`

Start with preferred sectors. Expand if no strong setups found there.

### Step 3 — Validate each candidate
For each candidate with initial interest:
- Run `uv run trader strategies signals --tickers TICKER --strategy rsi --with-news`
- Run `uv run trader news sentiment TICKER --lookback 7d`
- Assess: technical signal + sentiment alignment + macro context

Drop any candidate where:
- Technical signal is 0 (hold) AND sentiment is neutral (no catalyst)
- Already held and up > 30% (take-profit territory, not entry)
- Traded in the last 24 hours per JSONL log

### Step 4 — Size each opportunity
Apply profile guardrails:
- Max single position: `guardrails.max_single_position_pct × net_liquidation`
- For equity: use ATR-based sizing (1-2% account risk)
- For options: max loss ≤ 2% account

### Step 5 — Rank by conviction
Score each opportunity 0-100 on:
- Signal strength (RSI + MACD alignment)
- Sentiment score
- Sector regime fit
- Profile preference match

Return top 3 maximum. More is noise.

## Output Format

```json
[
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
    "reason": "VCP breakout in semiconductors (profile match). RSI 58 (not overbought). Sentiment +0.6 bullish. MACD crossover yesterday. Risk: $480 (1.6% account)."
  },
  {
    "type": "OPPORTUNITY",
    "priority": "MEDIUM",
    "ticker": "XLE",
    "asset_class": "options",
    "strategy": "cash_secured_put",
    "conviction": 71,
    "action": "sell_put",
    "contracts": 2,
    "strike": 85,
    "expiry": "2026-04-17",
    "premium": 1.80,
    "proposed_command": "uv run trader orders sell XLE 2 --contract-type option --expiry 2026-04-17 --strike 85 --right put",
    "reason": "Energy ETF (profile match). IV elevated post-pullback. Willing to own at $85 (support). Collect $360 premium. Max loss: $16,640 (cash-secured)."
  }
]
```

If no high-conviction opportunities exist, return: `[]`
````

- [ ] **Step 2: Commit**

```bash
git add .claude/agents/opportunity-finder.md
git commit -m "feat: add opportunity-finder specialist agent"
```

---

### Task 7: `portfolio-health` and `strategy-optimizer` agents

**Files:**
- Create: `.claude/agents/portfolio-health.md`
- Create: `.claude/agents/strategy-optimizer.md`

- [ ] **Step 1: Create portfolio-health agent**

Create `.claude/agents/portfolio-health.md`:

````markdown
---
name: portfolio-health
description: Specialist agent invoked by portfolio-conductor to assess portfolio allocation, concentration, diversification, and drift from profile targets. Returns drift flags and rebalance proposals. Never places orders directly.
tools: Bash, Read
---

# Portfolio Health

You are a portfolio health specialist. You assess allocation drift, concentration risk, and diversification quality. You do not place orders — you surface proposals for the conductor.

## Input

Context object with `snapshot`, `profile`, `recent_log`.

## Assessment

### 1. Allocation map
Group positions by:
- Sector (Technology, Energy, Healthcare, Financials, Consumer, Industrials, Materials, Utilities, Real Estate, Communication, Defense, Emerging Markets)
- Asset class (equity, ETF, options, futures)
- Market cap (Large >$10B, Mid $2-10B, Small <$2B)

Calculate each as % of `net_liquidation`.

### 2. Concentration flags

| Metric | Warning | Critical |
|--------|---------|----------|
| Single position | >10% | >15% |
| Single sector | >30% | >35% |
| Top 3 positions | >45% | >55% |
| Cash below target | <5% | <2% |

### 3. Drift from profile targets
Compare current allocation to `profile.portfolio_targets`.
Flag any metric outside target range.

### 4. Deep weekly review (weekly slot only)
If `time_slot == "weekly"`:
- Run `uv run trader positions list` and `uv run trader positions pnl`
- Calculate HHI (sum of squared weights) — flag if > 0.15
- Surface top 3 positions for per-ticker RSI + sentiment review

## Output Format

```json
{
  "health_score": 78,
  "flags": [
    {
      "type": "DRIFT",
      "severity": "WARNING",
      "metric": "sector_technology",
      "current_pct": 38,
      "target_max_pct": 35,
      "recommendation": "trim on next opportunity"
    }
  ],
  "rebalance_proposals": [
    {
      "ticker": "AAPL",
      "action": "TRIM",
      "current_pct": 16.2,
      "target_pct": 10,
      "trim_value_usd": 5600,
      "reason": "Single position > 15%. Technology sector already at 38%.",
      "proposed_command": "uv run trader orders sell AAPL 12 --type limit --price <current_bid>"
    }
  ],
  "summary": "Portfolio concentrated in Technology (38%). Consider trimming AAPL. Cash at 8% — near target. Otherwise healthy."
}
```
````

- [ ] **Step 2: Create strategy-optimizer agent**

Create `.claude/agents/strategy-optimizer.md`:

````markdown
---
name: strategy-optimizer
description: Specialist agent invoked by portfolio-conductor on weekly schedule to refresh strategy parameters via backtesting on recent data. Returns updated param recommendations. Never places orders.
tools: Bash, Read
---

# Strategy Optimizer

You are a weekly strategy maintenance specialist. You run backtests on recent data and recommend updated strategy parameters. You do not place orders.

## When You Run

Weekly slot only (Sunday). If invoked outside weekly context, return immediately with `{"skipped": true, "reason": "not weekly slot"}`.

## Workflow

For each active strategy used in the portfolio (default: rsi, macd, ma_cross):

### Step 1 — Backtest current params on active holdings
```bash
uv run trader strategies backtest TICKER --strategy STRATEGY_NAME
```

Run for the top 5 holdings by market value.

### Step 2 — Optimize params
```bash
uv run trader strategies optimize TICKER --strategy STRATEGY_NAME --metric sharpe
```

### Step 3 — Compare
If optimized Sharpe > current Sharpe by > 0.2, flag the param change as recommended.
If difference is marginal (< 0.1), keep current params — avoid over-fitting.

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
      "note": "Sharpe improvement +0.32. Consider updating default RSI period for semiconductors."
    }
  ],
  "summary": "RSI period 10 outperforms 14 on recent NVDA data. All other strategies within acceptable range."
}
```
````

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/portfolio-health.md .claude/agents/strategy-optimizer.md
git commit -m "feat: add portfolio-health and strategy-optimizer agents"
```

---

## Chunk 3: Cron Schedule & Integration

### Task 8: Configure cron schedules

**Files:**
- Modify: `.env.example` — add `AGENT_MODE`

- [ ] **Step 1: Add `AGENT_MODE` to `.env.example`**

Add to `.env.example`:
```bash
# Agent mode: autonomous (places orders) or supervised (logs intent only)
AGENT_MODE=supervised
AGENT_LOG_PATH=.trader/logs/agent.jsonl
AGENT_PROFILE_PATH=.trader/profile.json
```

- [ ] **Step 2: Set up pre-market cron (8am Mon–Fri)**

Use the CronCreate tool to schedule:
- **Schedule:** `0 8 * * 1-5`
- **Agent:** `portfolio-conductor`
- **Prompt:** `Run pre-market portfolio analysis. Time slot: pre-market. Read .trader/profile.json and .trader/logs/agent.jsonl for context. Fetch live snapshot, assess risk and opportunities, execute any approved trades.`

- [ ] **Step 3: Set up intraday cron (hourly 9am–4pm Mon–Fri)**

Use the CronCreate tool to schedule:
- **Schedule:** `0 9-16 * * 1-5`
- **Agent:** `portfolio-conductor`
- **Prompt:** `Run intraday portfolio check. Time slot: intraday. Read .trader/profile.json and .trader/logs/agent.jsonl for context. Assess risk and narrow opportunities. Do nothing if situation is calm.`

- [ ] **Step 4: Set up weekly cron (Sunday 6pm)**

Use the CronCreate tool to schedule:
- **Schedule:** `0 18 * * 0`
- **Agent:** `portfolio-conductor`
- **Prompt:** `Run weekly portfolio review. Time slot: weekly. Read .trader/profile.json and .trader/logs/agent.jsonl for context. Deep portfolio health review and strategy optimization. Skip opportunity finder.`

- [ ] **Step 5: Verify cron list**

Use CronList to confirm all 3 schedules are registered correctly.

- [ ] **Step 6: Commit**

```bash
git add .env.example
git commit -m "feat: configure agent cron schedules and AGENT_MODE env vars"
```

---

### Task 9: Smoke test — supervised mode end-to-end

- [ ] **Step 1: Set supervised mode**

```bash
export AGENT_MODE=supervised
```

- [ ] **Step 2: Manually invoke conductor**

In a Claude Code session, invoke the `portfolio-conductor` agent manually with a pre-market prompt. Verify it:
1. Fetches live portfolio (or handles empty portfolio gracefully)
2. Reads `.trader/logs/agent.jsonl` (empty file OK)
3. Reads `.trader/profile.json` successfully
4. Logs a `RUN_START` entry
5. Logs `WORKFLOW_DECISION`
6. Logs `RUN_END`
7. Does NOT place any orders (supervised mode)

- [ ] **Step 3: Inspect the log**

```bash
cat .trader/logs/agent.jsonl | python3 -c "import sys,json; [print(json.dumps(json.loads(l), indent=2)) for l in sys.stdin]"
```

Verify: valid JSON on every line, `ts`, `run_id`, `agent`, `event` present on all entries.

- [ ] **Step 4: Commit final state**

```bash
git add -u
git commit -m "feat: autonomous portfolio agents system complete"
```

---

## Summary

| Chunk | Deliverable | Tests |
|---|---|---|
| 1 | `profile.json`, `log.py`, `context.py` | 11 unit tests |
| 2 | 5 agent markdown files | Manual invocation |
| 3 | Cron schedules, env config, smoke test | End-to-end supervised run |

**Start in supervised mode** (`AGENT_MODE=supervised`). Review a few daily logs. Once you trust the conductor's decisions, flip to `AGENT_MODE=autonomous`.
