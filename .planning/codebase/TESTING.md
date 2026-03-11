# Testing Patterns

**Analysis Date:** 2026-03-11

## Framework

- **Runner:** `pytest` >= 8 — Config in `pyproject.toml` under `[tool.pytest.ini_options]`
- **Async support:** `pytest-asyncio` >= 0.23 with `asyncio_mode = "auto"` — all `async` test functions run automatically without `@pytest.mark.asyncio` decorator (though some files still include it explicitly)
- **HTTP mocking:** `respx` >= 0.21 — used to mock `httpx` requests in transport-layer tests
- **Mock/patch:** `unittest.mock` (`AsyncMock`, `patch`) — built-in, no additional library needed
- **CLI testing:** `click.testing.CliRunner` — invokes CLI commands without subprocess, captures stdout
- **Test data generation:** `pytest` `monkeypatch` fixture for env vars; `tmp_path` for temporary files
- **Commands:**
  - Run all tests: `uv run pytest`
  - Run unit tests only: `uv run pytest tests/unit/`
  - Run agent tests: `uv run pytest tests/agents/`
  - Run with coverage: `uv run pytest --cov=trader tests/`

## Organization

```
tests/
├── __init__.py
├── test_imports.py          # Package importability smoke test
├── test_packaging.py        # Entry point / packaging validation
├── tests_manual_mvp_smoke.py  # Live broker smoke test (manual only)
├── agents/
│   ├── __init__.py
│   ├── test_context.py      # Agent context builder tests
│   └── test_log.py          # Agent log JSONL writer tests
├── integration/
│   └── __init__.py          # Empty — integration tests not yet implemented
└── unit/
    ├── __init__.py
    ├── test_adapter_base.py       # Adapter ABC contract tests
    ├── test_benzinga.py           # BenzingaClient with respx HTTP mocking
    ├── test_cli_account.py        # CLI account commands via CliRunner
    ├── test_cli_orders.py         # CLI order commands via CliRunner
    ├── test_cli_root.py           # CLI root group (--help, unknown command)
    ├── test_cli_strategies.py     # CLI strategies commands via CliRunner
    ├── test_config.py             # Config dataclass env var loading
    ├── test_ibkr_rest_adapter.py  # IBKRRestAdapter with AsyncMock patches
    ├── test_ibkr_rest_client.py   # IBKRRestClient HTTP layer with respx
    ├── test_ibkr_tws_adapter.py   # IBKRTWSAdapter tests
    ├── test_models.py             # Pydantic model field/validation tests
    ├── test_optimizer.py          # Strategy optimizer unit tests
    ├── test_risk_filter.py        # Risk filter logic tests
    ├── test_sentiment.py          # Sentiment analyzer tests
    └── test_strategies.py         # Strategy signal shape/value tests
```

- **Location:** All automated tests in `tests/` — not co-located with source.
- **Naming:** `test_{module_or_concern}.py`. Test functions always `test_` prefixed. Test grouping by CLI command group or package module.
- **`tests/manual_mvp_smoke.py`:** Requires live IBKR connection — do not run in CI.

## Patterns

### Pattern 1 — Pydantic model validation tests (no I/O)

```python
# tests/unit/test_models.py
def test_order_request_stock():
    req = OrderRequest(ticker="AAPL", qty=10, side="buy", order_type="market")
    assert req.contract_type == "stock"
    assert req.price is None

def test_sentiment_result_signal():
    r = SentimentResult(ticker="AAPL", score=0.5, signal="bullish",
                        article_count=5, lookback_hours=24, top_headlines=[])
    data = r.model_dump()
    assert "score" in data
```

### Pattern 2 — Strategy signal tests (pure function, generated fixture data)

```python
# tests/unit/test_strategies.py
def make_ohlcv(n=100) -> pd.DataFrame:
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    return pd.DataFrame({
        "open": close * 0.99, "high": close * 1.01,
        "low": close * 0.98, "close": close, "volume": 1000000,
    })

def test_rsi_signals_shape():
    strat = RSIStrategy({"period": 14, "oversold": 30, "overbought": 70})
    df = make_ohlcv()
    signals = strat.signals(df)
    assert len(signals) == len(df)
    assert set(signals.unique()).issubset({-1, 0, 1})
```

Strategies return a `pd.Series` of `{-1, 0, 1}`. Always assert shape and value set.

### Pattern 3 — Adapter tests with `patch.object` + `AsyncMock`

```python
# tests/unit/test_ibkr_rest_adapter.py
@pytest.fixture
def adapter():
    config = Config()
    config.ib_account = "DU123456"
    return IBKRRestAdapter(config)

@pytest.mark.asyncio
async def test_list_positions(adapter):
    mock_data = [{"conid": 265598, "ticker": "AAPL", "position": 10,
                  "avgCost": 190.0, "mktValue": 1950.0, "unrealizedPnl": 50.0}]
    with patch.object(adapter._client, "get", new=AsyncMock(return_value=mock_data)):
        positions = await adapter.list_positions()
    assert len(positions) == 1
    assert positions[0].ticker == "AAPL"
```

Patch `adapter._client.get` / `adapter._client.post` using `patch.object(..., new=AsyncMock(...))`.

### Pattern 4 — HTTP transport tests with `respx`

```python
# tests/unit/test_ibkr_rest_client.py
@pytest.mark.asyncio
async def test_get_request(client):
    with respx.mock:
        respx.get("https://localhost:5000/v1/api/test").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        result = await client.get("/test")
        assert result == {"ok": True}
```

Use `respx.mock` as a context manager. Always provide the full URL (scheme + host + port + path).

### Pattern 5 — CLI tests with `CliRunner` + `patch`

```python
# tests/unit/test_cli_orders.py
def test_buy_market_order():
    runner = CliRunner()
    with patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.connect", new=AsyncMock()), \
         patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.place_order",
               new=AsyncMock(return_value=mock_order())), \
         patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.disconnect", new=AsyncMock()):
        result = runner.invoke(cli, ["orders", "buy", "AAPL", "10"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["order_id"] == "ord_1"
```

Always:
1. Mock `connect`, the relevant adapter method, and `disconnect` as `AsyncMock`.
2. `assert result.exit_code == 0, result.output` — include `result.output` in the failure message.
3. `json.loads(result.output)` — verify stdout is valid JSON and assert on fields.

### Pattern 6 — Config tests with `monkeypatch`

```python
# tests/unit/test_config.py
def test_config_defaults(monkeypatch):
    monkeypatch.delenv("IB_PORT", raising=False)
    c = Config()
    assert c.ib_port == 5000

def test_config_from_env(monkeypatch):
    monkeypatch.setenv("IB_PORT", "7497")
    c = Config()
    assert c.ib_port == 7497
```

Always `delenv` with `raising=False` to handle missing keys. Never read env directly in tests — use `monkeypatch`.

### Pattern 7 — Agent tests with `tmp_path` fixture

```python
# tests/agents/test_context.py
@pytest.fixture
def profile_file(tmp_path):
    p = tmp_path / "profile.json"
    p.write_text(json.dumps({...}))
    return p

def test_load_profile(profile_file):
    profile = load_profile(profile_file)
    assert profile["risk_tolerance"] == "moderate"
```

Use `tmp_path` for any test that reads/writes files. Never use hardcoded paths in tests.

## Mocking

- **Framework:** `unittest.mock` — `AsyncMock` for all async methods, `MagicMock` for sync.
- **HTTP layer:** `respx` for `httpx`-based clients (`BenzingaClient`, `IBKRRestClient`). Use `respx.mock` context manager.
- **Adapter layer:** `patch.object(adapter._client, "get", new=AsyncMock(...))` — patch the internal `_client` methods, not the adapter methods themselves, for adapter-level tests.
- **CLI layer:** Patch at the fully-qualified class path `"trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.method_name"` when testing CLI commands.
- **What to mock:** IBKR gateway HTTP calls, Benzinga HTTP calls, `connect`/`disconnect` lifecycle.
- **What NOT to mock:** Pydantic model construction, strategy signal computation on DataFrames, `Config` dataclass field access, `click` CLI routing.

## Fixtures & Test Data

- **Location:** Inline within test files (no shared `conftest.py` fixtures across directories; each subdirectory has its own `__init__.py`).
- **OHLCV data:** Generated inline using `numpy` with `np.random.seed(42)` for reproducibility (see `tests/unit/test_strategies.py`).
- **Model fixtures:** Inline factory functions like `mock_order(**kwargs)` that construct Pydantic models.
- **File fixtures:** `tmp_path` pytest built-in — used in `tests/agents/test_context.py` for profile JSON files.
- **No recorded HTTP responses:** `respx` mocks are defined inline per test. No cassette/VCR-style fixtures.

## Coverage

- **Target:** None enforced. No `[tool.coverage]` configuration in `pyproject.toml`.
- **Command:** `uv run pytest --cov=trader tests/`
- **Dev deps:** `pytest`, `pytest-asyncio`, `respx`, `pytest-mock` declared under `[project.optional-dependencies] dev` in `pyproject.toml`.

## Test Types

- **Unit (automated):** `tests/unit/` — 15 test files. Covers models, config, adapters (mocked), CLI commands (mocked), strategies (DataFrame fixture), HTTP clients (respx).
- **Agent (automated):** `tests/agents/` — covers `build_context` and agent log writer with `tmp_path` fixtures.
- **Integration (stub):** `tests/integration/` — directory exists with `__init__.py` only; no tests implemented yet.
- **Manual smoke:** `tests/tests_manual_mvp_smoke.py` — requires live IBKR paper trading connection. Not run by pytest automatically; run directly with `uv run python tests/tests_manual_mvp_smoke.py`.
- **E2E:** Not implemented as an automated suite.

## pytest Configuration (`pyproject.toml`)

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

`asyncio_mode = "auto"` means `async def test_*` functions run automatically. The `@pytest.mark.asyncio` decorator is redundant but harmless when included.

## Running Tests

```bash
# All automated tests (no broker required)
uv run pytest

# Unit tests only
uv run pytest tests/unit/

# Agent tests
uv run pytest tests/agents/

# Specific test file
uv run pytest tests/unit/test_cli_orders.py -v

# With coverage report
uv run pytest --cov=trader --cov-report=term-missing tests/
```

No live IBKR connection is required for any test in `tests/unit/` or `tests/agents/`. All broker I/O is mocked.
