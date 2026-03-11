# Coding Conventions

**Analysis Date:** 2026-03-11

## Naming

- **Files:** `snake_case.py` — Examples: `ibkr_rest_adapter.py`, `risk_filter.py`, `benzinga.py`
- **Directories/Packages:** `snake_case` — Examples: `trader/adapters/ibkr_rest/`, `trader/cli/`
- **Classes:** `PascalCase` — Examples: `IBKRRestAdapter`, `IBKRTWSAdapter`, `BaseStrategy`, `BenzingaClient`, `Config`
- **Functions/Methods:** `snake_case` — Examples: `get_quotes`, `place_order`, `resolve_conid`, `output_json`
- **Variables:** `snake_case` — Examples: `order_type`, `alert_id`, `conid_map`
- **Constants / module-level config:** `UPPER_SNAKE_CASE` — Examples: `_ORDER_TYPE_MAP`, `_STATUS_MAP`, `_QUOTE_FIELDS`, `OUTPUT_DIR`
- **Private members:** Leading underscore — Examples: `self._client`, `self._config`, `self._account_id`, `_confirm_replies`
- **Type aliases:** Descriptive PascalCase — Example: `Literal["buy", "sell"]` used inline rather than aliased

## Style & Linting

- **Formatter:** Not explicitly configured (no `ruff.toml`, `.flake8`, or `[tool.ruff]` in `pyproject.toml`). Code follows PEP 8 manually.
- **Linter:** Not configured. No Ruff, Flake8, or Pylint configuration detected.
- **Python version target:** `>=3.10` (declared in `pyproject.toml`). The `|` union syntax (`str | None`, `dict | list`) is used throughout — prefer this over `Optional[X]` in new code.
- **`from __future__ import annotations`:** Used in all `trader/` modules (adapters, CLI, models, news, config, strategies). Always include this at the top of new `.py` files.
- **Type hints:** All public method signatures in `trader/adapters/`, `trader/models/`, and `trader/strategies/` are fully annotated. CLI command functions are annotated for parameters but not return types (Click pattern).

## Import Organization

1. Standard library (`asyncio`, `json`, `sys`, `os`, `datetime`, `pathlib`, `inspect`, `dataclasses`)
2. Third-party packages (`click`, `pydantic`, `httpx`, `pandas`, `respx`)
3. Internal project imports — always absolute from package root: `from trader.adapters.factory import get_adapter`, `from trader.models import OrderRequest`

- **No relative imports** in `trader/` package modules. All internal imports use `from trader.X import Y`.
- **Deferred CLI imports:** `trader/cli/__main__.py` imports subcommand modules at the bottom of the file (after `cli` group is defined) to avoid circular imports:
  ```python
  from trader.cli import account, quotes, orders, positions, news, strategies, alerts, scan, watchlist
  cli.add_command(account.account)
  ```

## All-JSON Output Pattern (CLI)

**All CLI commands output JSON to stdout.** The `output_json()` function in `trader/cli/__main__.py` is the single output sink — always call it instead of `print()` or `click.echo()` directly.

```python
# trader/cli/__main__.py
def _serialize(data) -> str:
    if hasattr(data, "model_dump"):
        return json.dumps(data.model_dump(), indent=2)
    elif isinstance(data, list):
        return json.dumps(
            [d.model_dump() if hasattr(d, "model_dump") else d for d in data],
            indent=2
        )
    return json.dumps(data, indent=2)

def output_json(data) -> None:
    text = _serialize(data)
    click.echo(text)
    # If --save flag set, also writes to outputs/{group}/{date}/{time}_{leaf}.json
    ...
```

**Error output pattern for CLI commands** — errors go to stdout as JSON (not stderr), and the command exits with code 1:
```python
try:
    output_json(asyncio.run(run()))
except Exception as e:
    import sys
    click.echo(json.dumps({"error": str(e), "code": type(e).__name__}))
    sys.exit(1)
```

**Save-to-file notices** go to stderr so stdout stays clean for piping:
```python
click.echo(f"  → saved: {out_path}", err=True)
```

## Async/Await Pattern in Adapters

All broker I/O is `async`. CLI commands are synchronous entry points that call `asyncio.run()` around a local `async def run()` closure:

```python
# Standard CLI command async bridge pattern (trader/cli/orders.py)
@orders.command()
@click.pass_context
def cancel(ctx, order_id):
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    async def run():
        await adapter.connect()
        try:
            ok = await adapter.cancel_order(order_id)
        finally:
            await adapter.disconnect()
        return {"cancelled": ok, "order_id": order_id}
    try:
        output_json(asyncio.run(run()))
    except Exception as e:
        click.echo(json.dumps({"error": str(e), "code": type(e).__name__}))
        sys.exit(1)
```

Rules:
- Always `await adapter.connect()` before using the adapter.
- Always `await adapter.disconnect()` in a `finally` block.
- Use `asyncio.gather()` for concurrent per-ticker operations (see `get_quotes`, `get_news` in `trader/adapters/ibkr_rest/adapter.py`).

## Pydantic Models

All domain models in `trader/models/` are `pydantic.BaseModel` subclasses. Use `Literal` for constrained string fields instead of enums:

```python
# trader/models/order.py
from pydantic import BaseModel
from typing import Literal

class OrderRequest(BaseModel):
    ticker: str
    qty: float
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit", "stop", "trailing_stop", "bracket"]
    price: float | None = None
    contract_type: Literal["stock", "etf", "option"] = "stock"
```

- All optional fields default to `None` with `float | None = None` syntax.
- Serialize with `.model_dump()` — not `.dict()` (Pydantic v2).
- `models/__init__.py` re-exports all public models via `__all__`. Import from `trader.models`, not from submodules.

## Config Pattern

`trader/config.py` uses a plain `@dataclass` (not Pydantic) with `field(default_factory=lambda: os.getenv(...))`. This allows mutation in tests (`config.ib_account = "DU123456"`).

```python
@dataclass
class Config:
    ib_host: str = field(default_factory=lambda: os.getenv("IB_HOST", "127.0.0.1"))
    ib_port: int = field(default_factory=lambda: int(os.getenv("IB_PORT", "5000")))
    ...
```

Always pass `Config()` into adapters/clients. Never read `os.getenv()` directly in adapter or CLI code.

## Error Handling Patterns

**Adapter layer — raise typed exceptions:**
```python
# ValueError for bad input or rejected operations
raise ValueError(f"Unsupported order_type '{req.order_type}'. Supported: {list(_ORDER_TYPE_MAP)}")
raise ValueError(f"Order {order_id} not found")
raise ValueError(f"IBKR rejected order: {r['error']}")

# RuntimeError for unrecoverable infrastructure failures
raise RuntimeError("IBKR Client Portal Gateway not authenticated after retries. ...")

# PermissionError for explicit permission denials
raise PermissionError("IBKR denied alert creation (403). Enable 'Trading Access'...")
```

**Retry loop pattern** (used in `connect()` for IBKR gateway):
```python
_RETRIES = 8
_DELAY = 3.0
last_exc: Exception | None = None
for attempt in range(_RETRIES):
    try:
        ...
        return
    except Exception as exc:
        last_exc = exc
    if attempt < _RETRIES - 1:
        await asyncio.sleep(_DELAY)
raise RuntimeError("...") from last_exc
```

**Per-ticker best-effort swallow** (used in `get_quotes`, `get_news`):
```python
async def fetch(ticker: str) -> list[NewsItem]:
    try:
        ...
    except Exception:
        return []  # Silently skip failed tickers
```

**403 re-raise with user-friendly message:**
```python
try:
    resp = await self._client.post(...)
except Exception as exc:
    if "403" in str(exc):
        raise PermissionError("...actionable message...") from exc
    raise
```

## Logging

No logging framework is used in `trader/` package code. Errors surface as exceptions. CLI commands surface errors as JSON to stdout. Use `click.echo(..., err=True)` only for non-data notices (e.g., save confirmations).

## Function Design

- **Async by default** for all methods on `Adapter` subclasses and HTTP clients.
- **ABC abstract methods** use `...` (ellipsis body) — not `pass` or `raise NotImplementedError`.
- **Private helpers prefixed with `_`:** `_confirm_replies`, `_resolve_conid`, `_resolve_qty`, `_serialize`.
- **Strategy functions are sync and pure:** `signals(ohlcv: pd.DataFrame) -> pd.Series` takes a DataFrame and returns a Series of `-1`, `0`, `1` signals with no side effects.
- **Keyword-only `**kwargs`** used for `modify_order` to allow partial updates without hardcoding all fields.

## Module Design

- **Barrel `__init__.py`** at `trader/models/__init__.py` re-exports all public models with explicit `__all__`. Import models from `trader.models`, not submodules.
- **Adapter factory** at `trader/adapters/factory.py` — new adapters register here. CLI passes `broker` string to `get_adapter(broker, config)`.
- **Abstract base classes:** `trader/adapters/base.py` defines `Adapter` ABC. `trader/strategies/base.py` defines `BaseStrategy` ABC. All concrete implementations must implement the full interface.
- **Subpackages for adapter variants:** `trader/adapters/ibkr_rest/` and `trader/adapters/ibkr_tws/` each contain `adapter.py` (implements `Adapter`) and supporting modules.

## Path Handling

- Use `pathlib.Path` for all file paths. Example: `output_dir / group / now.strftime("%Y-%m-%d")`.
- Use `Path.mkdir(parents=True, exist_ok=True)` before writing output files.
- Output files land in `outputs/{command_group}/{YYYY-MM-DD}/{HH-MM-SS}_{subcommand}.json` when `--save` is set.
- Agent state files use `.trader/logs/` and `.trader/profile.json` (configured via `Config`).
