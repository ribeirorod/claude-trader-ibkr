from trader.strategies.rsi import RSIStrategy
from trader.strategies.macd import MACDStrategy
from trader.strategies.ma_cross import MACrossStrategy
from trader.strategies.bnf import BNFStrategy
from trader.strategies.base import BaseStrategy

_REGISTRY = {
    "rsi": RSIStrategy,
    "macd": MACDStrategy,
    "ma_cross": MACrossStrategy,
    "bnf": BNFStrategy,
}

def get_strategy(name: str, params: dict | None = None) -> BaseStrategy:
    cls = _REGISTRY.get(name.lower())
    if not cls:
        raise ValueError(f"Unknown strategy '{name}'. Available: {list(_REGISTRY)}")
    return cls(params)

def list_strategies() -> list[str]:
    return list(_REGISTRY)
