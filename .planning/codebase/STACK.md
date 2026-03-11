# Technology Stack

**Analysis Date:** 2026-03-11

## Languages
- **Primary:** Python >=3.10 — All application code in `trader/` package (CLI, broker adapters, strategies, models, agents)

## Runtime & Package Manager
- Python >=3.10 (tested on 3.12 via Homebrew `python3.12`, `.venv/` managed by uv)
- **Package Manager:** `uv` — Lockfile: `uv.lock` (present, pinned hashes). Install with `uv sync`, add deps with `uv add`.
- Virtual environment: `.venv/` at project root

## Frameworks
| Framework | Version | Purpose |
|-----------|---------|---------|
| click | >=8.1 | CLI framework — all commands, groups, options, `--help` generation |
| pydantic | >=2.9 | Data models and validation — all `trader/models/` dataclasses serialized via `model_dump()` |
| asyncio (stdlib) | built-in | Core async I/O — all broker adapter methods are `async def`; CLI runs via `asyncio.run()` |
| pytest | >=8 | Test runner — config in `pyproject.toml` `[tool.pytest.ini_options]` |
| pytest-asyncio | >=0.23 | Async test support — `asyncio_mode = "auto"` in pytest config |

## Key Dependencies
| Package | Version | Why Critical |
|---------|---------|--------------|
| httpx | >=0.27 | Async HTTP client used by `IBKRRestClient` and `BenzingaClient`; replaces requests for async support |
| ibeam | >=0.5.10 | IBKR Client Portal Gateway session keepalive — prevents auth timeout without manual browser interaction |
| pandas | >=2.2 | OHLCV DataFrames consumed by all strategy `signals()` methods in `trader/strategies/` |
| yfinance | >=0.2 | Historical price data fetching for strategy backtesting and signal generation |
| python-dotenv | >=1.0,<2 | Loads `.env` at startup in `trader/config.py` via `load_dotenv()` |
| ib_insync | >=0.9.86 (optional) | TWS adapter — only installed with `uv sync --extra tws`; used by `IBKRTWSAdapter` |
| respx | >=0.21 (dev) | httpx mock library for unit tests — mocks IBKR REST and Benzinga HTTP calls |
| pytest-mock | >=3.12 (dev) | Mocker fixture for unit tests |

## CLI Entry Point
- **Command:** `trader` (installed via `[project.scripts]` in `pyproject.toml`)
- **Entry:** `trader.cli.__main__:cli`
- **Root group:** `trader/cli/__main__.py` — registers 9 subcommand groups: `account`, `quotes`, `orders`, `positions`, `news`, `strategies`, `alerts`, `scan`, `watchlist`
- **Design contract:** All commands output JSON to stdout by default; `--save` writes to `outputs/{group}/{YYYY-MM-DD}/{HH-MM-SS}_{sub}.json`

## Strategy Modules
Pure-function strategies in `trader/strategies/` — each subclasses `BaseStrategy` (in `trader/strategies/base.py`) and implements `signals(ohlcv: pd.DataFrame) -> pd.Series`:
| Strategy | File | Signal Logic |
|----------|------|--------------|
| RSI | `trader/strategies/rsi.py` | Oversold (<30) → buy (+1), overbought (>70) → sell (-1) |
| MACD | `trader/strategies/macd.py` | MACD line / signal line crossover |
| MACross | `trader/strategies/ma_cross.py` | Moving average crossover |
| BNF | `trader/strategies/bnf.py` | BNF momentum strategy |

Strategy factory at `trader/strategies/factory.py`. Risk filter wrapper at `trader/strategies/risk_filter.py`. Parameter optimizer at `trader/strategies/optimizer.py`.

## Broker Adapter System
Abstract base at `trader/adapters/base.py` (`Adapter` ABC). Factory function at `trader/adapters/factory.py` (`get_adapter(broker, config)`). Two implementations:
- `ibkr-rest` → `trader/adapters/ibkr_rest/adapter.py` (`IBKRRestAdapter`) — primary, default
- `ibkr-tws` → `trader/adapters/ibkr_tws/adapter.py` (`IBKRTWSAdapter`) — optional, requires `[tws]` extra

## Agent & Skill System
Claude Code agent/skill system in `.claude/` (not Python code — Markdown prompt files):
- **Agents** (`.claude/agents/*.md`): `portfolio-manager`, `portfolio-conductor`, `portfolio-health`, `risk-monitor`, `strategy-optimizer`, `opportunity-finder`, `order-alert-manager`, `system-improver`
- **Skills** (`.claude/skills/*/`): `trader-cli`, `morning-routine`, `market-news-analyst`, `technical-analyst`, `options-strategy-advisor`, `position-sizer`, `sector-analyst`, `backtest-expert`, `portfolio-manager`, and more (18 total)
- **Scheduling:** `.claude/crons.json` defines recurring agent runs; `scripts/setup-crons.sh` registers them at session start via Claude Code's `CronCreate` tool
- **Agent runtime support (Python):** `trader/agents/log.py` (`AgentLog` — JSONL event log at `.trader/logs/agent.jsonl`) and `trader/agents/context.py` (`build_context`, `TimeSlot` enum, `load_profile`)
- **Execution modes:** `AGENT_MODE=supervised` (log intents only) vs `AGENT_MODE=autonomous` (execute orders)

## Pydantic Models
All in `trader/models/` — used for JSON serialization via `model_dump()`:
| Model | File | Purpose |
|-------|------|---------|
| `Account`, `Balance`, `Margin` | `trader/models/account.py` | Account summary |
| `Order`, `OrderRequest` | `trader/models/order.py` | Order placement and state |
| `Position`, `PnL` | `trader/models/position.py` | Open positions |
| `Quote`, `OptionChain`, `OptionContract` | `trader/models/quote.py` | Market data |
| `NewsItem`, `SentimentResult` | `trader/models/news.py` | News and sentiment |
| `Alert`, `AlertCondition` | `trader/models/alert.py` | Price alerts |
| `ScanResult` | `trader/models/scan.py` | Market scanner results |

## Configuration
- **Config class:** `trader/config.py` — `@dataclass Config` loaded at CLI startup; all fields read from env via `os.getenv()`
- **Environment:** `.env` loaded via `python-dotenv`. See `.env.example` for all variables.
- **Key env vars:**
  - `IB_HOST` (default: `127.0.0.1`) — IBKR gateway host
  - `IB_PORT` (default: `5000`, production: `5001`) — IBKR Client Portal HTTPS port
  - `IB_ACCOUNT` — IBKR account ID (paper: `DU...`, live: `U...`)
  - `BENZINGA_API_KEY` — Benzinga news REST API token
  - `DEFAULT_BROKER` (default: `ibkr-rest`) — broker adapter selector
  - `DEFAULT_STRATEGY` (default: `rsi`) — default strategy for signal commands
  - `MAX_POSITION_PCT` (default: `0.05`) — max single-position sizing
  - `AGENT_MODE` (`supervised` | `autonomous`) — agent order execution mode
  - `AGENT_LOG_PATH` (default: `.trader/logs/agent.jsonl`) — agent JSONL event log
  - `AGENT_PROFILE_PATH` (default: `.trader/profile.json`) — portfolio profile for agents
  - `IBEAM_ACCOUNT`, `IBEAM_PASSWORD`, `IBEAM_GATEWAY_BASE_URL`, `IBEAM_AUTHENTICATE`, `IBEAM_KEY` — ibeam keepalive config
  - `FM_API_KEY` — Financial Modeling Prep (optional, for fundamental screening)
- **Build system:** setuptools (`pyproject.toml`), package discovery via `[tool.setuptools.packages.find]` targeting `trader*`

## Output Structure
- `outputs/` — Runtime outputs organized by command group and date
  - `outputs/{group}/{YYYY-MM-DD}/{HH-MM-SS}_{sub}.json`
- `.trader/logs/agent.jsonl` — JSONL agent event log (one JSON object per line)
- `.trader/profile.json` — Portfolio profile consumed by agents

## Platform Requirements
- **Development:** macOS (darwin), Python >=3.10, `uv` installed, IBKR Client Portal Gateway running at `https://localhost:5001`
- **Production:** Single-machine execution. No containerization or cloud deployment manifests detected. ibeam (Python package) keeps the gateway session alive. Manual browser login required once unless `IBEAM_AUTHENTICATE=True` with `IBEAM_KEY` set.
- **Tests:** `pytest` with `asyncio_mode = "auto"`, test paths in `tests/` (unit, integration, agents subdirs)
