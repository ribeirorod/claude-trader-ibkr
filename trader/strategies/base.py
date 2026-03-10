from __future__ import annotations
from abc import ABC, abstractmethod
import pandas as pd

class BaseStrategy(ABC):
    def __init__(self, params: dict | None = None):
        self._params = {**self.default_params(), **(params or {})}

    @abstractmethod
    def signals(self, ohlcv: pd.DataFrame) -> pd.Series: ...

    @abstractmethod
    def default_params(self) -> dict: ...

    @property
    def params(self) -> dict:
        return self._params
