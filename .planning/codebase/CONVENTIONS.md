# Coding Conventions

**Analysis Date:** 2026-03-10

## Naming

- **Files:** `snake_case.py` — Examples: `portfolio_run_strategy.py`, `ibkr_data_fetcher.py`, `strategy_factory.py`
- **Directories/Packages:** `snake_case` — Examples: `vibe/venues/`, `volatility/composer/core/`
- **Classes:** `PascalCase` — Examples: `IBKRAdapter`, `TTLIdempotencyMap`, `BaseStrategy`, `StrategyOptimizer`
- **Functions/Methods:** `snake_case` — Examples: `retry_async`, `normalize_symbol_ibkr`, `load_portfolio`
- **Variables:** `snake_case` — Examples: `order_type`, `client_order_id`, `all_assets`
- **Constants / module-level config:** `UPPER_SNAKE_CASE` — Examples: `STRATEGY_PARAM_RANGES`, `STRATEGY_CLASSES`, `OUTPUT_DIR`
- **Private members:** Leading underscore — Examples: `self._venue`, `self._ib`, `self._idemp`, `_TaskSpec`
- **Type aliases:** `PascalCase` or descriptive — Example: `ScheduledFunc = Callable[[], Awaitable[None]]`

## Style & Linting

- **Formatter:** Not detected (no `.prettierrc`, `ruff.toml`, `.flake8`, or `pyproject.toml` present). Code follows PEP 8 conventions manually.
- **Linter:** Not detected. No ESLint, Ruff, Flake8, or Pylint configuration files present.
- **Type hints:** Used consistently throughout `vibe/` module. All public method signatures are fully annotated. Top-level scripts use `from typing import Dict, List, Optional, Any`.
- **`from __future__ import annotations`:** Used in all `vibe/` core modules (`trader.py`, `models.py`, `utils.py`, `scheduler.py`, `vibe/venues/ibkr.py`) to enable forward-reference string annotations.

## Import Organization

1. Standard library (`asyncio`, `os`, `datetime`, `typing`, `pathlib`, `json`, `logging`)
2. Third-party packages (`pandas`, `ib_insync`, `structlog`, `dotenv`)
3. Internal/project imports (relative: `from .models import ...`, `from ..utils import ...`)

- **Path manipulation:** Top-level scripts that are not inside a package use `sys.path.insert(0, str(Path(__file__).parent))` to resolve sibling packages at runtime. Avoid this pattern inside `vibe/` package modules — use relative imports there.
- **Lazy/deferred imports:** Used inside loop bodies or function bodies when conditionally needed (e.g., `from ib_insync import Stock, Contract` inside `enrich_contract_details`). This is an existing pattern, not a convention to replicate.

## Error Handling Patterns

The codebase uses two distinct error-handling styles by layer:

**`vibe/` core library — re-raise or typed exceptions:**
```python
# Raise ValueError for bad caller input
if limit_price is None:
    raise ValueError("limit_price required for limit order")

# Best-effort silently swallow for non-critical paths
try:
    self._ib.client.cancelOrder(oid)
    return
except Exception:
    return
```

**Portfolio scripts and examples — broad except with logging:**
```python
try:
    df = pd.read_csv(csv_path)
    ...
except Exception as e:
    logger.error(f"Error loading portfolio: {e}")
    return pd.DataFrame()
```

**Async retry via utility:**
```python
# Use retry_async for transient failures (e.g., connect)
await retry_async(_do_connect, retries=3)
```

**`asyncio.TimeoutError` is the default `retry_on` exception.** Use `with_timeout()` for all IBKR async calls that may hang.

## Logging

- **`vibe/` core library:** No logging in core; errors surface as exceptions.
- **Portfolio scripts (`portfolio_*.py`):** `logging.basicConfig(level=logging.INFO)` + module-level `logger = logging.getLogger(__name__)`. Uses f-string messages in `logger.info/warning/error`.
- **Examples (`examples/`):** `structlog` with `ConsoleRenderer`. Uses keyword arguments: `log.info("event_name", key=value)`.
- **Test scripts (`test_ibkr_all_assets.py`):** Mix of `print()` for progress and `logging.getLogger(__name__)` inside helper functions.
- **`volatility/composer/` strategies:** `logging.getLogger(__name__)` at module level with f-string messages.

**Pattern:** Use `structlog` in example/integration harnesses; use `logging` in portfolio scripts and strategy modules; raise exceptions (don't log) inside the `vibe/` library.

## Function Design

- **Async by default** for any I/O-touching operation (IBKR calls, data fetches). All `IBKRAdapter` and `Trader` methods are `async`.
- **Keyword-only parameters** enforced with `*` for multi-argument methods to prevent positional confusion:
  ```python
  async def buy(self, symbol: str, *, quantity: float, order_type: str = "market", ...) -> OrderResponse:
  ```
- **Optional parameters typed explicitly:** `Optional[float] = None` rather than `float | None` (the codebase predates Python 3.10 union syntax in most files).
- **Return type annotations:** All `vibe/` public methods declare return types. Portfolio scripts omit them.
- **Docstrings:** Present on complex or public-facing methods using plain-text Args/Returns sections (Google-style, informal). Single-line docstrings used for simpler helpers.

## Module Design

- **Exports:** `vibe/__init__.py` uses explicit `__all__` to declare the public API: `["Trader", "Scheduler", "IndicatorCalculator", "calculate_indicators"]`.
- **Barrel files:** `vibe/__init__.py` re-exports `Trader` and `Scheduler`. `volatility/composer/strategies/__init__.py` re-exports strategy classes. Use barrel `__init__.py` files to define the package surface; do not import implementation details directly.
- **Adapter pattern:** All broker interaction goes through `IBKRAdapter` (`vibe/venues/ibkr.py`). `Trader` is a thin facade that delegates to `self._venue`. New venues should implement the same interface and be assigned to `self._venue`.
- **Dataclasses with slots:** `OrderResponse` and `_TaskSpec` use `@dataclass(slots=True)` for efficiency. Use this pattern for simple data-carrying objects.
- **Enums as str subclasses:** All enums inherit from `(str, Enum)` to allow direct string comparison without `.value`:
  ```python
  class OrderStatus(str, Enum):
      PENDING = "pending"
  ```

## Path Handling

- Use `pathlib.Path` for file paths in scripts. Example: `OUTPUT_DIR = Path(__file__).parent / "outputs" / "ibkr_assets"`.
- Use `Path.mkdir(parents=True, exist_ok=True)` to create output directories before writing.
- Do not hardcode absolute paths (the `run_test.sh` script has a hardcoded path — this is a known anti-pattern to avoid).
