from __future__ import annotations
import yfinance as yf

class FundamentalScreener:
    def _fetch_info(self, ticker: str) -> dict:
        return yf.Ticker(ticker).info

    def check(
        self,
        ticker: str,
        max_pe: float = 100.0,
        min_eps_growth: float = -0.10,
    ) -> dict:
        """
        Returns {"pass": bool, "veto_reason": str | None, "pe": ..., "eps_growth": ...}
        If data is unavailable, the rule does not fire (safe default).
        """
        info = self._fetch_info(ticker)
        pe = info.get("trailingPE")
        eps_growth = info.get("earningsGrowth")

        if pe is not None and pe > max_pe:
            return {"pass": False, "veto_reason": "pe_too_high", "pe": pe, "eps_growth": eps_growth}

        if eps_growth is not None and eps_growth < min_eps_growth:
            return {"pass": False, "veto_reason": "earnings_declining", "pe": pe, "eps_growth": eps_growth}

        return {"pass": True, "veto_reason": None, "pe": pe, "eps_growth": eps_growth}
