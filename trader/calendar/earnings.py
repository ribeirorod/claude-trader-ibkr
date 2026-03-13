from __future__ import annotations
from datetime import date
import pandas as pd
import yfinance as yf

class EarningsCalendar:
    def _fetch_calendar(self, ticker: str) -> pd.DataFrame:
        """
        Normalise yfinance calendar to a DataFrame.
        yfinance 0.2.x returns a dict like {"Earnings Date": [Timestamp(...)]}.
        Older versions return a DataFrame. We handle both.
        """
        raw = yf.Ticker(ticker).calendar
        if raw is None:
            return pd.DataFrame()
        if isinstance(raw, dict):
            return pd.DataFrame(raw)
        return raw  # already a DataFrame

    def next_earnings(self, ticker: str) -> date | None:
        """Return the next earnings date, or None if unknown/past."""
        cal = self._fetch_calendar(ticker)
        if cal is None or cal.empty or "Earnings Date" not in cal.columns:
            return None
        today = date.today()
        dates = pd.to_datetime(cal["Earnings Date"]).dt.date
        future = [d for d in dates if d >= today]
        return min(future) if future else None

    def days_to_earnings(self, ticker: str) -> int | None:
        nxt = self.next_earnings(ticker)
        if nxt is None:
            return None
        return (nxt - date.today()).days

    def is_in_blackout(self, ticker: str, blackout_days: int = 3) -> bool:
        """True if earnings is within `blackout_days` from today."""
        days = self.days_to_earnings(ticker)
        if days is None:
            return False
        return 0 <= days <= blackout_days
