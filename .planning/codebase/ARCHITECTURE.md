# Architecture

**Analysis Date:** 2026-03-11

## Pattern Overview

- **Overall:** Agent-first autonomous trading system. A Python CLI package (`trader/`) provides all trading primitives; an autonomous multi-agent layer (`.claude/agents/`) orchestrates them on a cron schedule. All CLI output is JSON. All agent coordination is done through structured JSONL logs written to `.trader/logs/`.
- **Key characteristics:**
  - Adapter pattern: `Adapter` ABC in `trader/adapters/base.py` isolates broker communication; `IBKRRestAdapter` (default) and `IBKRTWSAdapter` (optional) are the two concrete implementations
  - Factory function (`get_adapter`) selects adapter at CLI startup based on `--broker` flag or `DEFAULT_BROKER` env var
  - Strategy pattern: `BaseStrategy` ABC in `trader/strategies/base.py`; `signals()` is the single entry point returning a `pd.Series` of `{-1, 0, 1}` per bar
  - All CLI commands call `output_json()` — stdout is always clean JSON; diagnostic text goes to stderr
  - Agent system is code-free: agents are markdown instruction files (`.claude/agents/*.md`), dispatched by the Claude AI runtime. No Python agent framework.
  - Specialist agents propose; `portfolio-conductor` is the only agent that executes orders

---

## Layers

**CLI Layer:**
- Purpose: User-facing and agent-facing interface; translates flags to async adapter calls and emits JSON
- Location: `trader/cli/`
- Contains: Click command groups — `account`, `quotes`, `orders`, `positions`, `news`, `strategies`, `alerts`, `scan`, `watchlist`
- Depends on: `trader/adapters/factory.py`, `trader/strategies/`, `trader/news/`, `trader/models/`
- Used by: Humans via `uv run trader …`; autonomous agents via `uv run trader …` in Bash tool calls

**Adapter Layer:**
- Purpose: Abstracts all broker I/O behind a uniform async interface
- Location: `trader/adapters/`
- Contains:
  - `base.py` — `Adapter` ABC with 15 abstract async methods (connect, disconnect, get_account, get_quotes, get_option_chain, place_order, modify_order, cancel_order, list_orders, list_positions, close_position, get_news, list_alerts, create_alert, delete_alert, scan, scan_params)
  - `factory.py` — `get_adapter(broker, config)` factory function
  - `ibkr_rest/adapter.py` — `IBKRRestAdapter`: full implementation via IBKR Client Portal Gateway REST API (port 5000/5001); handles IBKR reply-confirmation loop for orders, conid resolution, bracket order construction
  - `ibkr_rest/client.py` — `IBKRRestClient`: thin httpx wrapper with SSL verification disabled (self-signed gateway cert)
  - `ibkr_tws/adapter.py` — `IBKRTWSAdapter`: stub wrapping `ib_insync.IB`; requires optional install `trader[tws]`
- Depends on: `trader/config.py`, `trader/models/`, `httpx` (rest), `ib_insync` (tws, optional)
- Used by: `trader/cli/` commands

**Domain Models Layer:**
- Purpose: Typed DTOs shared across CLI, adapters, and strategies
- Location: `trader/models/`
- Contains: `Account`, `Balance`, `Margin` (`account.py`); `Order`, `OrderRequest` (`order.py`); `Position`, `PnL` (`position.py`); `Quote`, `OptionChain`, `OptionContract` (`quote.py`); `NewsItem`, `SentimentResult` (`news.py`); `Alert`, `AlertCondition` (`alert.py`); `ScanResult` (`scan.py`)
- Depends on: Pydantic (all models use `.model_dump()`)
- Used by: adapters, CLI commands, `trader/strategies/`

**Strategy Layer:**
- Purpose: Pure-function technical analysis strategies returning buy/sell/hold signals
- Location: `trader/strategies/`
- Contains:
  - `base.py` — `BaseStrategy` ABC: `signals(ohlcv: pd.DataFrame) -> pd.Series`, `default_params() -> dict`
  - `rsi.py` — `RSIStrategy`: RSI crossover (`period`, `oversold`, `overbought`)
  - `macd.py` — `MACDStrategy`: MACD signal line crossover (`fast`, `slow`, `signal`)
  - `ma_cross.py` — `MACrossStrategy`: fast/slow SMA crossover (`fast_window`, `slow_window`)
  - `bnf.py` — `BNFStrategy`: Bollinger Band + price action breakout (`lookback`, `breakout_pct`)
  - `factory.py` — `get_strategy(name, params)` and `list_strategies()`; registry dict maps name → class
  - `optimizer.py` — `Optimizer.grid_search()`: exhaustive grid search over param space, returns best params by Sharpe/returns/win_rate
  - `risk_filter.py` — `RiskFilter.filter()`: post-signal filter layer (sentiment gating, etc.)
- Depends on: `pandas`, `numpy`, `yfinance` (OHLCV fetch in CLI commands)
- Used by: `trader/cli/strategies.py`

**News Layer:**
- Purpose: Fetch financial news and score sentiment
- Location: `trader/news/`
- Contains:
  - `benzinga.py` — `BenzingaClient`: async httpx client for Benzinga REST v2 API; uses `token` query param + `Accept: application/json` header
  - `sentiment.py` — `SentimentScorer`: scores a list of `NewsItem` objects into a `SentimentResult`
- Depends on: `httpx`, `trader/config.py`
- Used by: `trader/cli/strategies.py` (`--with-news` flag), `trader/cli/watchlist.py` (`--signals` flag), `trader/cli/news.py`

**Configuration Layer:**
- Purpose: Single source of truth for all environment-driven settings
- Location: `trader/config.py`
- Contains: `Config` dataclass — loads all env vars via `dotenv`; properties: `ib_host`, `ib_port`, `ib_account`, `ibkr_username`, `ibkr_password`, `benzinga_api_key`, `max_position_pct`, `default_strategy`, `default_broker`, `agent_mode`, `agent_log_path`, `agent_profile_path`; computed property `ibkr_rest_base_url`
- Depends on: `python-dotenv`
- Used by: `trader/cli/__main__.py` (singleton `config = Config()` at module load)

**Agent Infrastructure Layer:**
- Purpose: Python support types for the autonomous agent system
- Location: `trader/agents/`
- Contains:
  - `context.py` — `build_context()`: assembles run context dict from snapshot + profile + recent log; `TimeSlot` enum; `load_profile()` reader for `.trader/profile.json`
  - `log.py` — `AgentLog`: append-only JSONL writer to `.trader/logs/agent.jsonl`; `LogEvent` dataclass; `read_last(n)` tail reader; `new_run_id()` 8-char hex generator
- Depends on: stdlib only
- Used by: autonomous agents (indirectly via CLI) and potentially by conductor scripts

**Autonomous Agent Layer:**
- Purpose: AI-driven portfolio management; runs on cron schedule, dispatches specialist agents, executes trades
- Location: `.claude/agents/`
- Contains (all markdown instruction files):
  - `portfolio-conductor.md` — orchestrator; only agent that places orders; dispatches all specialists
  - `risk-monitor.md` — position drawdown, stop-loss gaps, sector concentration assessment
  - `portfolio-health.md` — allocation drift, HHI concentration, cash floor checks
  - `opportunity-finder.md` — universe cache management (`universe.json`), scan-based discovery, candidate validation, proposal generation
  - `order-alert-manager.md` — alert/order lifecycle management; deduplication; triggered-alert-to-bracket conversion
  - `strategy-optimizer.md` — bi-weekly backtest runner; recommends parameter updates; emits `ALERT_PROPOSAL`
  - `system-improver.md` — monthly self-improvement; audits decision quality; applies profile/agent-file changes in autonomous mode
  - `portfolio-manager.md` — general portfolio management skill
- Depends on: Claude AI runtime (Agent tool dispatch), `uv run trader …` CLI commands via Bash tool
- Used by: `.claude/crons.json` schedule → triggers `portfolio-conductor` which dispatches the rest

**Skill Library:**
- Purpose: Reusable analysis capabilities that agents invoke via the Agent tool
- Location: `.claude/skills/`
- Contains (each a `SKILL.md` instruction file): `backtest-expert`, `earnings-trade-analyzer`, `economic-calendar-fetcher`, `etf-rotation`, `geopolitical-influence`, `market-news-analyst`, `market-top-detector`, `morning-routine`, `options-strategy-advisor`, `portfolio-manager`, `position-sizer`, `sector-analyst`, `stanley-druckenmiller-investment`, `stock-screener`, `technical-analyst`, `trader-cli`, `trader-strategies`, `vcp-screener`
- Used by: `portfolio-conductor.md` (dispatches skills by name from its "Skills Available" list)

---

## Data Flow

**Scheduled Cron Run (typical intraday slot):**
1. `crons.json` triggers `portfolio-conductor` Claude agent with a slot-specific prompt
2. Conductor runs `uv run trader positions list`, `uv run trader positions pnl`, `uv run trader account summary`, `uv run trader orders list --status open` → IBKR live snapshot
3. Appends compact JSON snapshot to `.trader/logs/portfolio_evolution.jsonl`
4. Reads `.trader/logs/agent.jsonl` (last 50 lines) for recent decision history
5. Reads `.trader/profile.json` for portfolio profile and guardrails
6. Dispatches specialist agents via Claude Agent tool (each specialist runs CLI commands internally):
   - `economic-calendar-fetcher` → sets `risk_mode`
   - `market-news-analyst` on held tickers + watchlist → produces `news_context`
   - `risk-monitor` → receives `news_context` + snapshot → emits `RISK_FLAG` proposals
   - `portfolio-health` → emits `DRIFT` flags + `TRIM` proposals
   - `opportunity-finder` → checks `.trader/universe.json` cache staleness → runs IBKR scans → validates candidates → emits `OPPORTUNITY` + `ALERT_PROPOSAL` proposals
   - `order-alert-manager` → reads `uv run trader alerts list` + `uv run trader orders list` → deduplicates proposals → emits action list
7. Conductor reviews proposals against guardrails (cash floor, position sizing, daily limit)
8. In `autonomous` mode: logs `ORDER_INTENT` to `agent.jsonl`, executes `uv run trader orders buy/sell/stop …`
9. Logs `RUN_END` event to `agent.jsonl`

**CLI Signal Generation (agent-invoked):**
1. `uv run trader strategies signals --tickers TICKER --strategy rsi`
2. `trader/cli/strategies.py` → `get_strategy("rsi")` → `RSIStrategy`
3. `yf.download(ticker, period=lookback)` → OHLCV DataFrame
4. `strat.signals(df)` → `pd.Series` of `{-1, 0, 1}`
5. Optional: `BenzingaClient.get_news()` → `SentimentScorer.score()` → `SentimentResult`
6. `RiskFilter.filter(signal, sentiment)` → filtered signal
7. `output_json([{ticker, signal, signal_label, filtered, filter_reason, sentiment_score}])` → stdout

**CLI Order Execution:**
1. `uv run trader orders buy TICKER QTY --type limit --price PRICE`
2. `trader/cli/orders.py` → `get_adapter(broker, config)` → `IBKRRestAdapter`
3. `adapter.connect()` → POST `/tickle` + GET `/iserver/auth/status` (up to 8 retries, 3s delay)
4. `adapter.place_order(OrderRequest)` → `_resolve_conid(ticker)` → POST `/iserver/account/{id}/orders`
5. `_confirm_replies()` loop — handles IBKR warning confirmation messages
6. For bracket orders: POST child stop/take-profit orders linked by `parentId`
7. Returns `Order` dataclass → `output_json()` → stdout

**Universe Discovery (opportunity-finder):**
1. Agent reads `.trader/universe.json` — checks `last_refreshed_eu` / `last_refreshed_us` staleness (20h threshold)
2. If stale: runs `uv run trader scan run HIGH_VS_52W_HL --market STK.EU.LSE …` etc. across multiple scan types and markets
3. Merges and scores results (3+ scans=100, 2 scans=70, 1 scan=40, watchlist bonus=+15)
4. Writes updated segments back to `.trader/universe.json`
5. Top candidates validated via `uv run trader strategies signals` + `uv run trader news sentiment`

**State Management:**
- No in-process state store between runs; every run starts from live broker + JSONL history
- `IBKRRestAdapter` holds no persistent state (conid resolution is re-fetched each call — no cache currently)
- Agent state is encoded in `.trader/logs/agent.jsonl` (append-only JSONL)
- Portfolio evolution is tracked in `.trader/logs/portfolio_evolution.jsonl` (one snapshot object per line)
- Universe cache lives in `.trader/universe.json` (overwritten on refresh)
- Watchlists live in `outputs/watchlists.json` (named JSON object, keys=list names)
- Improvement proposals (supervised mode) written to `.trader/logs/improvement_proposals.jsonl`

---

## Key Abstractions

| Abstraction | Purpose | Location | Pattern |
|-------------|---------|----------|---------|
| `Adapter` | Broker-agnostic async trading interface | `trader/adapters/base.py` | Abstract Base Class |
| `IBKRRestAdapter` | IBKR Client Portal Gateway implementation | `trader/adapters/ibkr_rest/adapter.py` | Concrete Adapter |
| `IBKRTWSAdapter` | ib_insync TWS implementation (optional) | `trader/adapters/ibkr_tws/adapter.py` | Concrete Adapter |
| `get_adapter` | Broker selection factory | `trader/adapters/factory.py` | Factory function |
| `Config` | Env-driven configuration dataclass | `trader/config.py` | Dataclass + dotenv |
| `BaseStrategy` | Strategy signal contract | `trader/strategies/base.py` | Abstract Base Class |
| `get_strategy` | Strategy name→class registry | `trader/strategies/factory.py` | Registry + factory |
| `Optimizer` | Grid-search parameter tuner | `trader/strategies/optimizer.py` | Grid search |
| `RiskFilter` | Post-signal gating layer | `trader/strategies/risk_filter.py` | Filter |
| `BenzingaClient` | News fetch from Benzinga REST v2 | `trader/news/benzinga.py` | Async HTTP client |
| `AgentLog` | Append-only JSONL event log | `trader/agents/log.py` | Event log |
| `build_context` | Assembles agent run context | `trader/agents/context.py` | Context builder |
| `output_json` | CLI JSON serialization + optional file save | `trader/cli/__main__.py` | Output helper |
| `portfolio-conductor` | Autonomous orchestrator; sole order executor | `.claude/agents/portfolio-conductor.md` | Orchestrator agent |

---

## Entry Points

| Entry Point | Location | Triggers |
|-------------|----------|----------|
| CLI (all commands) | `trader/cli/__main__.py` — `cli` Click group | `uv run trader …` |
| Cron scheduler | `.claude/crons.json` (6 schedules) | launchd/cron via `scripts/setup-crons.sh` |
| Portfolio conductor | `.claude/agents/portfolio-conductor.md` | Each cron slot: eu-pre-market (8:03 CET), eu-market (9:07–15:07 CET hourly), eu-us-overlap (15:03 CET), us-market (17:07–21:07 CET hourly), weekly (Sun 18:03 CET), monthly (1st Sun 18:03 CET) |

---

## Error Handling

- **CLI commands:** All broker-facing commands wrap the async call in try/except; on error, `{"error": str(e), "code": type(e).__name__}` is emitted to stdout and the process exits with code 1
- **Adapter connect:** `IBKRRestAdapter.connect()` retries up to 8 times with 3s delay; raises `RuntimeError` if still unauthenticated
- **IBKR order confirmation:** `_confirm_replies()` handles warning-message reply loop (up to 5 iterations); raises `ValueError` on `"error"` in response
- **Strategy signals:** Per-ticker exceptions in `signals` command are caught; `{"ticker": …, "error": str(e)}` is included in the result array (partial success)
- **Agent errors:** If `trader alerts list` or `trader orders list` fails, `order-alert-manager` returns `{"error": "could not fetch live state", "proposals_deferred": true}` — conductor retries next cycle
- **News fetch:** Benzinga client propagates `httpx` exceptions; callers (CLI) catch and degrade gracefully

---

## Cross-Cutting Concerns

- **Logging:** Agent events logged as newline-delimited JSON to `.trader/logs/agent.jsonl`; standard Python `logging` not used in agent layer — all agent observability goes through the JSONL log; CLI uses `click.echo(err=True)` for diagnostic messages
- **Validation:** `OrderRequest` uses Pydantic; `Config` uses dataclass with env-var defaults; strategy params are merged dicts (no schema validation)
- **Authentication:** IBKR REST — session is managed by the Client Portal Gateway; CLI calls `POST /tickle` to keep session alive on connect; TWS — `ib_insync` handles auth; Benzinga — `token` query parameter (not Authorization header)
- **Concurrency:** CLI adapter calls use `asyncio.run()` per command invocation (no shared event loop); strategy compute is synchronous CPU-bound (pandas); multiple quotes resolved via `asyncio.gather()` inside the adapter
- **Agent mode:** `AGENT_MODE=autonomous` (default) — conductor executes orders; `AGENT_MODE=supervised` — logs `ORDER_INTENT` but does not execute; checked from env var at each run
- **EU account constraint:** MiFID II KID restriction prevents trading US-listed ETFs (SPY, QQQ, IWM, etc.) from this account; agents use UCITS equivalents (CSPX, IWDA, EQQQ, etc.) and `opportunity-finder` enforces this in proposal logic
