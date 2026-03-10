from __future__ import annotations
import itertools
import pandas as pd
import numpy as np
from typing import Literal

class Optimizer:
    def grid_search(
        self,
        strategy_cls,
        ohlcv: pd.DataFrame,
        param_grid: dict,
        metric: Literal["sharpe", "returns", "win_rate"] = "sharpe",
    ) -> dict:
        keys = list(param_grid.keys())
        best_score = float("-inf")
        best_params = {}
        for combo in itertools.product(*param_grid.values()):
            params = dict(zip(keys, combo))
            try:
                strat = strategy_cls(params)
                signals = strat.signals(ohlcv)
                score = self._score(ohlcv["close"], signals, metric)
                if score > best_score:
                    best_score = score
                    best_params = params
            except Exception:
                continue
        return best_params

    def _score(self, close: pd.Series, signals: pd.Series, metric: str) -> float:
        returns = close.pct_change().shift(-1)
        strategy_returns = returns * signals
        if metric == "returns":
            return float(strategy_returns.sum())
        elif metric == "win_rate":
            trades = strategy_returns[signals != 0]
            return float((trades > 0).mean()) if len(trades) > 0 else 0.0
        else:  # sharpe
            if strategy_returns.std() == 0:
                return 0.0
            return float(strategy_returns.mean() / strategy_returns.std() * np.sqrt(252))
