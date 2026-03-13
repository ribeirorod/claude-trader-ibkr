import pandas as pd
import pytest
from datetime import date, timedelta
from unittest.mock import patch
from trader.calendar.dividends import DividendCalendar

def _make_dividends(dates: list) -> pd.Series:
    idx = pd.to_datetime(dates).tz_localize("UTC")
    return pd.Series([0.25] * len(dates), index=idx, name="Dividends")

def test_next_ex_div_returns_date():
    cal = DividendCalendar()
    future = date.today() + timedelta(days=10)
    with patch.object(cal, "_fetch_dividends", return_value=_make_dividends([future])):
        result = cal.next_ex_div("AAPL")
    assert result == future

def test_next_ex_div_returns_none_when_no_future():
    cal = DividendCalendar()
    past = date.today() - timedelta(days=5)
    with patch.object(cal, "_fetch_dividends", return_value=_make_dividends([past])):
        result = cal.next_ex_div("AAPL")
    assert result is None

def test_days_to_ex_div_positive():
    cal = DividendCalendar()
    future = date.today() + timedelta(days=7)
    with patch.object(cal, "_fetch_dividends", return_value=_make_dividends([future])):
        result = cal.days_to_ex_div("AAPL")
    assert result == 7

def test_days_to_ex_div_none_when_no_upcoming():
    cal = DividendCalendar()
    with patch.object(cal, "_fetch_dividends", return_value=pd.Series([], dtype=float)):
        result = cal.days_to_ex_div("AAPL")
    assert result is None

def test_is_near_ex_div_true():
    cal = DividendCalendar()
    future = date.today() + timedelta(days=3)
    with patch.object(cal, "_fetch_dividends", return_value=_make_dividends([future])):
        assert cal.is_near_ex_div("AAPL", within_days=5) is True

def test_is_near_ex_div_false():
    cal = DividendCalendar()
    future = date.today() + timedelta(days=20)
    with patch.object(cal, "_fetch_dividends", return_value=_make_dividends([future])):
        assert cal.is_near_ex_div("AAPL", within_days=5) is False
