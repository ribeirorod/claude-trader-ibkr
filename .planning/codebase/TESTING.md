# Testing Patterns

**Analysis Date:** 2026-03-10

## Framework

- **Runner:** No automated test runner configured. No `pytest.ini`, `setup.cfg [tool:pytest]`, `pyproject.toml [tool.pytest]`, or `vitest.config.*` detected.
- **Assertions:** Python built-in `assert` and manual `if/else` result checks (no assertion library like `pytest` or `unittest` is actively configured).
- **Commands:**
  - Import validation: `python tests/test_imports.py`
  - MVP smoke test: `python tests/tests_manual_mvp_smoke.py`
  - Integration test: `bash run_test.sh` (runs `examples/simple_integration_test.py`)
  - IBKR asset scan test: `python test_ibkr_all_assets.py`
  - Strategy optimizer test: `python volatility/composer/test_optimiser.py`

## Organization

- **Location:** Test files live in three places:
  - `tests/` — formal test directory, 2 files
  - Project root — `test_ibkr_all_assets.py` (integration/exploratory, lives at root)
  - `volatility/composer/test_optimiser.py` — strategy-level test, co-located with the module it exercises
- **Naming:** Files are prefixed with `test_` (e.g., `test_imports.py`, `test_ibkr_all_assets.py`). One exception: `tests/tests_manual_mvp_smoke.py` uses plural prefix. Use `test_` prefix consistently for new test files.

## Patterns

There are two distinct testing patterns in use:

**Pattern 1 — Import validation (no live connection):**
```python
# tests/test_imports.py
def test_imports():
    try:
        from vibe import Trader, Scheduler
        print("✓ vibe.Trader imported")
    except Exception as e:
        print(f"✗ Failed to import vibe: {e}")
        return False
    return True

if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)
```
This pattern tests that the module graph is importable without credentials or live services. It is the only test that can run in CI without a broker connection.

**Pattern 2 — Manual smoke test (requires live IBKR connection):**
```python
# tests/tests_manual_mvp_smoke.py
async def main():
    load_dotenv()
    trader = Trader()
    try:
        r1 = await trader.buy("AAPL", quantity=1, order_type="market")
        results["market_buy"] = r1.status
        # ... additional calls
        print("SMOKE_RESULTS:", results)
    finally:
        await trader.close()

if __name__ == "__main__":
    asyncio.run(main())
```
This pattern exercises the full happy path against a paper-trading IBKR account. There is no assertion framework — results are printed and inspected manually.

**Pattern 3 — Numbered integration tests with structlog output:**
```python
# examples/simple_integration_test.py
async def test_data_fetching():
    """Test 1: Fetch historical data from IBKR."""
    log.info("test_started", test="Data Fetching from IBKR", test_number=1)
    try:
        df = await fetcher.fetch_data_async('AAPL', start_date='2024-01-01', interval='1d')
        if not df.empty:
            log.info("data_fetched_success", rows=len(df))
            return True
        return False
    except Exception as e:
        log.error("data_fetch_error", error=str(e))
        return False
    finally:
        await fetcher.close()
```
Each test function returns `True`/`False`. Results are collected in a list and summarised at the end. Not compatible with pytest (no `assert`, no fixture injection).

## Mocking

- **Framework:** None configured. No `unittest.mock`, `pytest-mock`, or similar library is used.
- **What to mock:** IBKR connection (`IB().connectAsync`) is the primary candidate for mocking in unit tests. The `TTLIdempotencyMap` in `vibe/utils.py` and `_build_order` in `vibe/venues/ibkr.py` are pure/sync and can be unit-tested without mocking.
- **What NOT to mock:** Strategy execution (`volatility/composer/strategies/`) operates on DataFrames and requires no external services — test these with real fixture data directly.
- **Current reality:** No mocking exists. All tests require either a paper-trading IBKR connection on `127.0.0.1:7497` or skip broker tests entirely.

## Fixtures & Test Data

- **Location:** No dedicated fixtures directory. Test data is fetched live from IBKR or yFinance during test execution.
- **CSV outputs used as inputs:** Portfolio scripts read from `outputs/portfolio.csv` and `outputs/history.csv`. These CSVs serve as implicit test fixtures for `portfolio_run_strategy.py` and `portfolio_optimise_strategies.py`.
- **Strategy optimizer test uses live yFinance data:**
  ```python
  # volatility/composer/test_optimiser.py
  fetcher = YFinanceDataFetcher(tickers=["AAPL"])
  stock_data = fetcher.fetch_stock_data(start_date, end_date)
  ```
  No caching or recorded responses — each run hits the network.

## Coverage

- **Target:** None enforced. No coverage configuration detected.
- **Command:** Not configured. To run with coverage manually: `python -m pytest tests/ --cov=vibe`

## Test Types

- **Unit:** Not formally implemented. `tests/test_imports.py` is the closest — it validates module structure without I/O.
- **Integration (manual smoke):** `tests/tests_manual_mvp_smoke.py` and `examples/simple_integration_test.py` — require live paper-trading IBKR on localhost.
- **Strategy backtest / optimizer test:** `volatility/composer/test_optimiser.py` — exercises the optimization loop against yFinance data. Requires internet access. Not a pytest test.
- **Asset discovery / exploratory:** `test_ibkr_all_assets.py` — long-running IBKR scanner test. Saves results to `outputs/ibkr_assets/`. Not repeatable without a connection.
- **E2E:** Not implemented as a dedicated suite. The `examples/simple_integration_test.py` effectively covers E2E flows but requires manual gate (`input("Press ENTER to continue")`).

## Running Tests Without IBKR

The only test that runs without a live broker connection is:

```bash
source .venv/bin/activate
python tests/test_imports.py
```

All other tests require IBKR TWS or IB Gateway running locally on the port configured in `.env` (default `IB_PORT=7497`).

## Environment Setup for Tests

Tests read credentials from `.env` via `python-dotenv`. Copy `.env.example` and populate before running any broker-connected test:

```bash
cp .env.example .env
# Set IB_HOST, IB_PORT, IB_CLIENT_ID, IB_ACCOUNT
source .venv/bin/activate
```
