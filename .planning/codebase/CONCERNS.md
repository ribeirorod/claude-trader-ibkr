# Codebase Concerns

**Analysis Date:** 2026-03-10

---

## Tech Debt

| Area | Issue | Files | Impact | Fix Approach |
|------|-------|-------|--------|--------------|
| Venue abstraction | `Trader` hardcodes IBKR as the only venue (`# MVP: only IBKR`); no venue interface exists | `vibe/trader.py:15` | Adding any second broker requires rewriting `Trader` | Define a `BaseVenue` ABC; inject venue into `Trader.__init__` |
| History API ignores `start` param | `history()` silently ignores the `start` argument passed by callers; uses a fixed duration string instead | `vibe/venues/ibkr.py:570-571` | Callers pass `start="2024-01-01"` expecting filtered data; they get a full fixed-window period instead | Map `start` to an IBKR `durationStr` or use `endDateTime` + `durationStr` derived from the date gap |
| Duplicate client-ID counters | `IBKRDataFetcher` and `VibeTraderAdapter` each maintain their own global `_client_id_counter` (starting at 300 and 200 respectively); both mutate `os.environ['IB_CLIENT_ID']` as a side-effect | `volatility/composer/core/ibkr_data_fetcher.py:23-33`, `volatility/composer/tools/vibe_adapter.py:25-33` | Running both in the same process causes silent ID collisions or env-var overwrites that corrupt the default `IBKRAdapter` client ID | Centralise ID allocation in `vibe/utils.py`; pass `client_id` through `IBKRAdapter.__init__` rather than via env var mutation |
| `sys.path` manipulation everywhere | All integration points inject paths at module load time using `sys.path.insert(0, ...)` | `portfolio_run_strategy.py:23,28`, `portfolio_optimise_strategies.py:25,30`, `volatility/composer/core/ibkr_data_fetcher.py:14`, `volatility/composer/tools/vibe_adapter.py:15`, `volatility/composer/tools/manager.py:195` | Fragile; order-dependent; breaks if scripts are run from a different working directory | Install `vibe` as a proper package (add `pyproject.toml`/`setup.py`) and install in editable mode |
| Strategy serialisation uses `pickle` | `BaseStrategy.save/load` use `pd.to_pickle` / `pd.read_pickle` | `volatility/composer/strategies/base.py:103,111` | Pickle files are Python-version-sensitive and unreadable cross-environment; silently breaks after upgrades | Replace with JSON parameter export + reconstruct-from-class pattern |
| `DataPersistence` uses `pickle` for data cache | Market data snapshots persisted as raw pickle binaries | `volatility/composer/core/data_persistence.py:12-29` | Same version-sensitivity risk as strategy pickle; `.pkl` cache files become invalid silently | Switch to Parquet (already have pandas) for DataFrames; JSON for dicts |
| No `__all__` exports in `vibe/__init__.py` | Exports `IndicatorCalculator` and `calculate_indicators` which do not exist in the package | `vibe/__init__.py:7-8` | Any code doing `from vibe import IndicatorCalculator` will raise `ImportError` at runtime | Remove phantom exports; keep only `Trader` and `Scheduler` |
| `mailing.py` runs at import time | The module executes `Mailer(...)` and `mailer.send_daily_update(...)` at module level with a hardcoded absolute path and personal email address | `volatility/composer/tools/mailing.py:55-66` | Importing this module on any machine other than the original developer's will raise `FileNotFoundError` | Move usage code into a `__main__` guard; parameterise credentials path |
| Bare `except:` clause | `portfolio_run_strategy.py` contains a bare `except:` that silently swallows all exceptions including `KeyboardInterrupt` | `portfolio_run_strategy.py:105` | Impossible to interrupt the script; errors disappear silently | Replace with `except Exception as e:` and log |
| Indentation bug (syntax error) | `ibkr_data_fetcher.py` contains a `try:` block where the body (`df = self._format_for_volatility(...)`) is not indented inside the try, placing the next `logger.debug` inside the try but the assignment outside | `volatility/composer/core/ibkr_data_fetcher.py:109-116` | Python syntax error; `IBKRDataFetcher` cannot be imported without crashing | Fix indentation so `df = self._format_for_volatility(df, ticker)` is inside the `try:` block |

---

## Security Risks

| Area | Risk | Files | Mitigation | Recommendation |
|------|------|-------|------------|----------------|
| Hardcoded personal paths and email | `mailing.py` contains an absolute path to a private credentials file (`/Users/rribeiro/private/...`) and a personal Gmail address at module scope | `volatility/composer/tools/mailing.py:55` | None | Move to env vars (`GMAIL_CREDENTIALS_PATH`, `GMAIL_RECIPIENT`); add path to `.gitignore` |
| `os.environ` mutation for IBKR client ID | `IBKRDataFetcher` and `VibeTraderAdapter` overwrite the process-wide `IB_CLIENT_ID` env var as a side-effect of instantiation | `volatility/composer/core/ibkr_data_fetcher.py:49-50`, `volatility/composer/tools/vibe_adapter.py:51-52` | None | Pass `client_id` directly to `IBKRAdapter.__init__`; remove env-var mutation |
| No validation of bracket order price relationships | `bracket()` explicitly documents it does not validate that TP/SL prices make sense for the trade direction | `vibe/venues/ibkr.py:189-192` | None | Add pre-submission validation: long → TP > entry > SL; short → SL > entry > TP |
| No position-size guard | `execute_signal` and `execute_bracket_from_strategy` accept arbitrary `quantity` with no position-size or account-balance check | `volatility/composer/tools/vibe_adapter.py:58-181` | None | Add a max-position guard; check account balance before submitting |
| FMP API key in plain env var without validation | `FMPDataFetcher` raises `ValueError` if key missing, but the key is never validated for format and is passed directly in query-string params | `volatility/composer/core/data_fetchers.py:200-201` | Raises if absent | Validate key format; log a warning if key appears to be a placeholder |

---

## Performance Bottlenecks

| Operation | Problem | Files | Cause | Fix |
|-----------|---------|-------|-------|-----|
| Sector screener fetches data twice per ticker | `YFinanceDataFetcher.fetch_stock_data` makes two sequential `yf.Ticker(ticker).history()` calls per ticker (current + prior 100 days) then concatenates | `volatility/composer/core/data_fetchers.py:38-43` | Simple implementation; prior data fetched as a separate request | Pass a single earlier `start_date` to the first `history()` call and trim afterward |
| Parallel process pool in optimiser uses max 8 workers with no CPU guard | `StrategyOptimizer.optimize` spawns `ProcessPoolExecutor(max_workers=8)` unconditionally | `volatility/composer/tools/optimiser.py:84` | Hardcoded worker count | Use `min(8, os.cpu_count() or 4)` |
| In-memory cache in `IBKRDataFetcher` is per-instance | Each `IBKRDataFetcher` instance has its own `_cache` dict; creating a new instance (which happens on every script run) gets no cache benefit | `volatility/composer/core/ibkr_data_fetcher.py:54` | Instance-level cache dict | Use a shared on-disk cache (e.g., the existing `outputs/ibkr_cache/` directory) keyed by ticker+date+interval |
| `_qualified_cache` in `IBKRAdapter` is also per-instance | Contract qualification cache is lost when `IBKRAdapter` is recreated | `vibe/venues/ibkr.py:26` | Same pattern as above | Accept the constraint for now but document lifetime; alternatively promote to module-level dict |
| `portfolio_dataframe()` fetches portfolio and all open orders synchronously, then does O(n×m) symbol matching in pure Python | Nested loops over portfolio items and orders | `vibe/venues/ibkr.py:390-420` | Simple loop; fine for small portfolios | Not critical unless portfolio exceeds ~500 positions; document the assumption |

---

## Fragile Areas

| Component | Files | Why Fragile | Safe Modification | Test Gaps |
|-----------|-------|-------------|-------------------|-----------|
| Scheduler cron support | `vibe/scheduler.py:75-88` | Only supports `"*/N * * * *"` minute-step pattern; all other cron expressions are silently converted to `step=1` (every-minute fallback via `except Exception`) | Never pass non-minute-step cron expressions; use `every(minutes=N)` instead | No tests for cron parsing edge cases |
| `Scheduler._run_task` silently swallows all task exceptions | `vibe/scheduler.py:53-56` | Scheduled task failures are completely invisible; no logging, no counter, no re-raise option | Add a configurable `on_error` callback or at minimum log the exception with `structlog` | No tests for error propagation |
| `get_order` returns a hollow `OrderResponse` for unknown order IDs | `vibe/venues/ibkr.py:527-538` | Returns a fake response with empty symbol/side/quantity and `status=PENDING` instead of raising; callers cannot distinguish "order exists but pending" from "order not found" | Always cancel an order before assuming it's gone; check `symbol != ""` as a proxy for "found" | No test for the not-found path |
| `modify_order` silently no-ops incompatible field updates | `vibe/venues/ibkr.py:480-501` | e.g. calling `modify_order(order_id=x, limit_price=1.0)` on a MARKET order does nothing and returns the unchanged order | Check `order_type` before calling `modify_order`; treat the return value as authoritative | No tests for modify on wrong order type |
| `BaseStrategy.execute()` is abstract but `backtest()` calls `self.execute()` with no arguments | `volatility/composer/strategies/base.py:39-43` | The abstract signature declares `execute(self, data: pd.DataFrame)` but `backtest()` calls `self.execute()` with no `data` argument; concrete strategies override with zero-arg `execute()` creating an interface mismatch | Always call `strategy.backtest()` not `strategy.execute()` | No tests verify the interface contract |
| `stop_loss()` and `take_profit()` on `BaseStrategy` are stub `pass` returns | `volatility/composer/strategies/base.py:32-36` | Callers that invoke these methods receive `None`; no strategy currently implements them despite a TODO comment | Do not call these methods; they are non-functional | Entirely untested |
| `PortfolioManager._fetch_news_for_tickers` and `_send_email_report` are placeholders | `volatility/composer/tools/manager.py:354-357, 501-502` | Both methods log "not yet implemented" and return empty/None; the manager's `run()` flow calls them unconditionally | Safe to call; they silently no-op | No tests |
| Config manager crashes on missing config file | `volatility/composer/core/config.py:8-10` | `ConfigManager.__init__` opens `config/settings.yaml` with no existence check; also `setup_logging()` is called at module import time | Ensure config files exist before importing any `volatility/composer/core` module | No tests |
| `strategy_executor.py` uses broken relative imports | `volatility/composer/tools/strategy_executor.py:6` | `from strategies.base import BaseStrategy` is a bare relative import that only works when cwd is `volatility/composer` | Always run `cli.py` from `volatility/composer/` directory | No isolation tests |

---

## Dependencies at Risk

| Package | Risk | Impact | Migration Plan |
|---------|------|--------|----------------|
| `ib_insync==0.9.86` (pinned) | Pinned to an old version; `ib_insync` has had breaking API changes and the project already works around missing attributes (`hasattr` / `AttributeError` fallbacks for `placeOrderAsync`, `reqNewsProvidersAsync`, etc.) | Core order submission, history, news, and bracket orders | Evaluate upgrading to latest `ib_insync`; test all `hasattr` fallback paths; consider migrating to `ibapi` directly |
| `yfinance==0.2.43` (pinned) | yfinance is known for silent breaking changes in minor versions; pinned version may not reflect Yahoo's current API | Sector screener and all `PyTickerSymbolsFetcher` usage will silently return empty DataFrames | Add a runtime check that `yf.Ticker('AAPL').history(period='5d')` returns non-empty data on startup |
| `google-auth` + `google-api-python-client` | Listed as dependencies but only used in `mailing.py` which runs broken code at import time | Any environment that imports `mailing.py` fails | Either fix `mailing.py` or move Google deps to an optional extras group |
| No `pyproject.toml` or `setup.py` | The project is not installable as a package; all integration relies on `sys.path` manipulation | Any refactor that changes directory depth silently breaks all cross-module imports | Add `pyproject.toml` with `[project]` and `[tool.setuptools.packages.find]`; install with `pip install -e .` |
| `google-auth-oauthlib` | Required by `mailing.py` but not listed in `requirements.txt` | Silent `ImportError` when mailing is invoked | Either add to `requirements.txt` or remove the mailing feature from the requirements |

---

## Missing Infrastructure

| Gap | Impact | Recommendation |
|-----|--------|----------------|
| No automated test suite with a test runner | Only two test files exist (`tests/test_imports.py` is a manual script; `tests/tests_manual_mvp_smoke.py` requires a live IBKR connection); zero unit or integration tests run without infrastructure | Regressions go undetected | Add `pytest` to requirements; write unit tests using `unittest.mock` to mock `ib_insync.IB` |
| No order fill confirmation loop | After `submit()`, the code reads `orderStatus` immediately from the returned `Trade` object; for market orders this may still show `"Submitted"` before the fill arrives | Callers cannot reliably detect fills without polling | Add an optional `await_fill(timeout_ms)` helper that waits on `orderStatus.status == "Filled"` |
| No position reconciliation at startup | `VibeTraderAdapter._position_tracker` starts empty on every instantiation; no sync with actual IBKR positions at init time | Signals and bracket orders may be duplicated for already-open positions | Call `sync_positions_with_ibkr()` automatically in `VibeTraderAdapter.__init__` |
| No rate-limit handling for external APIs | `FMPDataFetcher` and `YFinanceDataFetcher` make sequential per-ticker HTTP requests with no backoff or rate-limit awareness | Bulk screener runs will hit API rate limits and silently return empty DataFrames for many tickers | Add exponential backoff with jitter around each request; honour `Retry-After` headers |
| `outputs/` directory committed to git | The `outputs/` directory (containing CSV/JSON results, signals, and IBKR cache files) is tracked as an untracked addition in the repo | Sensitive portfolio data and large data files accumulate in the repo history | Add `outputs/` to `.gitignore`; only commit schema/example files |
