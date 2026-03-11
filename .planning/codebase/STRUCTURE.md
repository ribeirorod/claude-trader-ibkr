# Codebase Structure

**Analysis Date:** 2026-03-11

## Directory Layout

```
trader/                                 ← project root
│
├── trader/                             ← Python package (installable as `trader`)
│   ├── __init__.py
│   ├── config.py                       ← Config dataclass; all env vars loaded here
│   ├── adapters/                       ← Broker adapter layer
│   │   ├── base.py                     ← Adapter ABC (15 abstract async methods)
│   │   ├── factory.py                  ← get_adapter(broker, config) factory
│   │   ├── ibkr_rest/                  ← Default: IBKR Client Portal Gateway (REST)
│   │   │   ├── adapter.py              ← IBKRRestAdapter (full implementation)
│   │   │   └── client.py               ← IBKRRestClient (httpx wrapper, SSL disabled)
│   │   └── ibkr_tws/                   ← Optional: ib_insync TWS adapter
│   │       └── adapter.py              ← IBKRTWSAdapter (requires trader[tws])
│   ├── agents/                         ← Python support types for the agent system
│   │   ├── context.py                  ← build_context(), TimeSlot enum, load_profile()
│   │   └── log.py                      ← AgentLog (JSONL writer), LogEvent dataclass
│   ├── cli/                            ← Click command groups
│   │   ├── __main__.py                 ← Root CLI group, output_json(), --broker/--save flags
│   │   ├── account.py                  ← `trader account` group
│   │   ├── alerts.py                   ← `trader alerts` group
│   │   ├── news.py                     ← `trader news` group
│   │   ├── orders.py                   ← `trader orders` group
│   │   ├── positions.py                ← `trader positions` group
│   │   ├── quotes.py                   ← `trader quotes` group
│   │   ├── scan.py                     ← `trader scan` group + curated scan/market/filter refs
│   │   ├── strategies.py               ← `trader strategies` group (signals, backtest, optimize)
│   │   └── watchlist.py                ← `trader watchlist` group (add/remove/list/from-scan)
│   ├── models/                         ← Pydantic DTOs
│   │   ├── __init__.py                 ← Re-exports all model types
│   │   ├── account.py                  ← Account, Balance, Margin
│   │   ├── alert.py                    ← Alert, AlertCondition
│   │   ├── news.py                     ← NewsItem, SentimentResult
│   │   ├── order.py                    ← Order, OrderRequest
│   │   ├── position.py                 ← Position, PnL
│   │   ├── quote.py                    ← Quote, OptionChain, OptionContract
│   │   └── scan.py                     ← ScanResult
│   ├── news/                           ← News fetch and sentiment scoring
│   │   ├── benzinga.py                 ← BenzingaClient (async httpx, Benzinga REST v2)
│   │   └── sentiment.py                ← SentimentScorer
│   └── strategies/                     ← Technical strategy implementations
│       ├── base.py                     ← BaseStrategy ABC (signals(), default_params())
│       ├── factory.py                  ← get_strategy(), list_strategies(), _REGISTRY dict
│       ├── optimizer.py                ← Optimizer.grid_search() (Sharpe/returns/win_rate)
│       ├── risk_filter.py              ← RiskFilter.filter() (post-signal sentiment gating)
│       ├── rsi.py                      ← RSIStrategy
│       ├── macd.py                     ← MACDStrategy
│       ├── ma_cross.py                 ← MACrossStrategy
│       └── bnf.py                      ← BNFStrategy (Bollinger + price action breakout)
│
├── .claude/                            ← Autonomous agent system (Claude AI runtime)
│   ├── agents/                         ← Agent instruction files (markdown)
│   │   ├── portfolio-conductor.md      ← Orchestrator; only agent that places orders
│   │   ├── risk-monitor.md             ← Position drawdown + stop-loss assessment
│   │   ├── portfolio-health.md         ← Allocation drift + concentration checks
│   │   ├── opportunity-finder.md       ← Universe cache + scan-based discovery
│   │   ├── order-alert-manager.md      ← Alert/order lifecycle + deduplication
│   │   ├── strategy-optimizer.md       ← Bi-weekly backtest + param optimization
│   │   ├── system-improver.md          ← Monthly self-improvement + profile updates
│   │   └── portfolio-manager.md        ← General portfolio management skill
│   ├── skills/                         ← Skill library (each a SKILL.md file)
│   │   ├── backtest-expert/
│   │   ├── earnings-trade-analyzer/
│   │   ├── economic-calendar-fetcher/
│   │   ├── etf-rotation/
│   │   ├── geopolitical-influence/
│   │   ├── market-news-analyst/
│   │   ├── market-top-detector/
│   │   ├── morning-routine/
│   │   ├── options-strategy-advisor/
│   │   ├── portfolio-manager/
│   │   ├── position-sizer/
│   │   ├── sector-analyst/
│   │   ├── stanley-druckenmiller-investment/
│   │   ├── stock-screener/
│   │   ├── technical-analyst/
│   │   ├── trader-cli/
│   │   ├── trader-strategies/
│   │   └── vcp-screener/
│   ├── agent-memory/                   ← Persistent agent-specific memory
│   │   └── portfolio-manager/
│   ├── crons.json                      ← 6 cron schedules (eu-pre-market, eu-market,
│   │                                       eu-us-overlap, us-market, weekly, monthly)
│   ├── settings.json                   ← Claude settings
│   └── scheduled_tasks.lock            ← Lock file for scheduled task runner
│
├── .trader/                            ← Runtime agent data (gitignored)
│   ├── profile.json                    ← Portfolio profile: risk tolerance, sectors,
│   │                                       targets, guardrails (human-editable)
│   ├── universe.json                   ← Opportunity-finder universe cache
│   │                                       (eu/us/etf/options_candidates segments)
│   └── logs/
│       ├── agent.jsonl                 ← Append-only agent event log (all agents)
│       ├── portfolio_evolution.jsonl   ← Per-run portfolio snapshots (NLV, cash, positions)
│       └── improvement_proposals.jsonl ← System-improver proposals (supervised mode only)
│
├── outputs/                            ← CLI --save outputs (gitignored)
│   ├── watchlists.json                 ← Named watchlists: {"default": [...], "momentum": [...]}
│   ├── news/                           ← Saved news command outputs
│   ├── scan/                           ← Saved scan outputs (YYYY-MM-DD/)
│   ├── signals/                        ← Saved signal outputs
│   ├── strategies/                     ← Saved strategy outputs (YYYY-MM-DD/)
│   └── watchlist/                      ← Saved watchlist outputs (YYYY-MM-DD/)
│
├── tests/                              ← Test suite
│   ├── unit/                           ← Unit tests
│   ├── integration/                    ← Integration tests
│   └── agents/                         ← Agent-specific tests
│
├── scripts/
│   └── setup-crons.sh                  ← Installs launchd plists from crons.json
│
├── docs/
│   └── plans/                          ← Design documents and implementation plans
│
├── clientportal.gw/                    ← IBKR Client Portal Gateway (binary, gitignored)
├── pyproject.toml                      ← Package config; entry point: trader = trader.cli.__main__:cli
├── .env.example                        ← Environment variable template
└── README.md
```

---

## Directory Purposes

| Directory | Purpose | Contains | Key Files |
|-----------|---------|----------|-----------|
| `trader/` | Python package — all trading primitives | Adapters, CLI, models, strategies, news, agents | `config.py`, `adapters/base.py` |
| `trader/adapters/` | Broker adapter layer | `Adapter` ABC, factory, two concrete adapters | `base.py`, `factory.py` |
| `trader/adapters/ibkr_rest/` | Default broker: IBKR Client Portal Gateway | REST adapter + httpx client | `adapter.py`, `client.py` |
| `trader/adapters/ibkr_tws/` | Optional broker: TWS via ib_insync | TWS adapter stub | `adapter.py` |
| `trader/agents/` | Python support for the agent system | JSONL log writer, context builder | `log.py`, `context.py` |
| `trader/cli/` | Click CLI — user and agent interface | 9 command groups, JSON output helper | `__main__.py`, all group files |
| `trader/models/` | Typed DTOs (Pydantic) | All domain data types | `__init__.py` |
| `trader/news/` | Financial news and sentiment | Benzinga client, sentiment scorer | `benzinga.py`, `sentiment.py` |
| `trader/strategies/` | Technical analysis strategies | BaseStrategy, 4 concrete strategies, optimizer | `base.py`, `factory.py` |
| `.claude/agents/` | Autonomous agent instructions (markdown) | 8 agent files; all use Bash to call `uv run trader` | `portfolio-conductor.md` |
| `.claude/skills/` | Reusable analysis skills (markdown) | 18 skill files dispatched by agents via Agent tool | `*/SKILL.md` |
| `.claude/agent-memory/` | Persistent cross-run agent memory | Agent-specific memory directories | — |
| `.trader/` | Runtime agent data store | Profile, universe cache, JSONL event logs | `profile.json`, `universe.json`, `logs/agent.jsonl` |
| `outputs/` | CLI `--save` outputs + watchlists | JSON files organized by command/date | `watchlists.json` |
| `scripts/` | Setup and maintenance scripts | Cron installer | `setup-crons.sh` |
| `tests/` | Test suite | unit/, integration/, agents/ | — |

---

## Where to Add New Code

| What | Location | Tests | Notes |
|------|----------|-------|-------|
| New broker adapter | `trader/adapters/{broker}/adapter.py` | `tests/unit/` | Subclass `Adapter` in `trader/adapters/base.py`; register in `trader/adapters/factory.py` |
| New strategy | `trader/strategies/{name}.py` | `tests/unit/` | Subclass `BaseStrategy`; implement `signals(ohlcv)` and `default_params()`; register in `trader/strategies/factory.py` `_REGISTRY` dict; add param grid to `_grids` in `trader/cli/strategies.py` `optimize` command |
| New CLI command group | `trader/cli/{group}.py` | `tests/unit/` | Create `@click.group()`; import and `cli.add_command()` in `trader/cli/__main__.py` |
| New domain model | `trader/models/{name}.py` | — | Pydantic model; export from `trader/models/__init__.py` |
| New news data source | `trader/news/{provider}.py` | `tests/unit/` | Async httpx client; return `list[NewsItem]`; wire into `trader/cli/news.py` |
| New specialist agent | `.claude/agents/{name}.md` | `tests/agents/` | Add YAML frontmatter (`name`, `description`, `tools`); follow propose-only pattern (no order execution); add to conductor's dispatch list in `portfolio-conductor.md` |
| New skill | `.claude/skills/{name}/SKILL.md` | — | Self-contained markdown; agents dispatch via Agent tool by skill name |
| New cron slot | `.claude/crons.json` | — | Add entry with `id`, `cron` (crontab format), `agent`, `slot`, `prompt`; run `scripts/setup-crons.sh` to install |

---

## Naming Conventions

- **Python files:** `snake_case.py` — Example: `ibkr_rest/adapter.py`, `ma_cross.py`
- **Python directories:** `snake_case` — Example: `ibkr_rest/`, `ibkr_tws/`
- **Python classes:** `PascalCase` — Example: `IBKRRestAdapter`, `BaseStrategy`, `BenzingaClient`
- **Python functions/methods:** `snake_case` — Example: `get_adapter`, `default_params`, `grid_search`
- **Click command names:** `kebab-case` (slugs) — Example: `from-scan`, `run-scan`; registered as group subcommands
- **Agent/skill files:** `kebab-case.md` — Example: `portfolio-conductor.md`, `vcp-screener/SKILL.md`
- **JSONL event types:** `UPPER_SNAKE_CASE` — Example: `ORDER_INTENT`, `RUN_END`, `UNIVERSE_REFRESHED`, `CASH_FLOOR_BLOCK`
- **Cron slot names:** `kebab-case` — Example: `eu-pre-market`, `eu-us-overlap`
- **Output files (--save):** `{HH-MM-SS}_{subcommand}.json` inside `outputs/{group}/{YYYY-MM-DD}/`

---

## Special Directories

| Directory | Purpose | Generated | Committed |
|-----------|---------|-----------|-----------|
| `outputs/` | CLI `--save` outputs; also stores `watchlists.json` | Yes | No (gitignored) |
| `.trader/` | Agent runtime data: profile, universe cache, event logs | Partially (logs generated; `profile.json` and `universe.json` are human/agent-maintained) | `profile.json` committed; logs gitignored |
| `.trader/logs/` | Append-only JSONL event logs for all agent runs | Yes | No |
| `.claude/agent-memory/` | Per-agent persistent memory across Claude sessions | Yes | Yes (sparse) |
| `clientportal.gw/` | IBKR Client Portal Gateway binary distribution | No | No (gitignored) |
| `.venv/` | Python virtual environment (`uv`) | Yes | No |
| `__pycache__/` | Python bytecode cache | Yes | No |
| `trader.egg-info/` | Editable install metadata | Yes | No |
