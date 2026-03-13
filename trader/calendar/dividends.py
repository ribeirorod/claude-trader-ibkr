from __future__ import annotations
from datetime import date
import pandas as pd
import yfinance as yf

class DividendCalendar:
    def _fetch_dividends(self, ticker: str) -> pd.Series:
        return yf.Ticker(ticker).dividends

    def next_ex_div(self, ticker: str) -> date | None:
        """Return the next ex-dividend date, or None if none upcoming."""
        divs = self._fetch_dividends(ticker)
        if divs.empty:
            return None
        today = pd.Timestamp.today(tz="UTC").normalize()
        future = divs[divs.index >= today]
        if future.empty:
            return None
        return future.index[0].date()

    def days_to_ex_div(self, ticker: str) -> int | None:
        """Return calendar days until next ex-div, or None."""
        nxt = self.next_ex_div(ticker)
        if nxt is None:
            return None
        return (nxt - date.today()).days

    def is_near_ex_div(self, ticker: str, within_days: int = 5) -> bool:
        """True if ex-div date is within `within_days` calendar days."""
        days = self.days_to_ex_div(ticker)
        if days is None:
            return False
        return 0 <= days <= within_days
