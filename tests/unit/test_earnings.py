import pandas as pd
import pytest
from datetime import date, timedelta
from unittest.mock import patch
from trader.calendar.earnings import EarningsCalendar

def _make_calendar(earnings_date: date):
    idx = pd.to_datetime([earnings_date])
    return pd.DataFrame({"Earnings Date": idx})

def test_next_earnings_returns_date():
    cal = EarningsCalendar()
    future = date.today() + timedelta(days=5)
    with patch.object(cal, "_fetch_calendar", return_value=_make_calendar(future)):
        result = cal.next_earnings("AAPL")
    assert result == future

def test_next_earnings_returns_none_for_past():
    cal = EarningsCalendar()
    past = date.today() - timedelta(days=2)
    with patch.object(cal, "_fetch_calendar", return_value=_make_calendar(past)):
        result = cal.next_earnings("AAPL")
    assert result is None

def test_days_to_earnings_positive():
    cal = EarningsCalendar()
    future = date.today() + timedelta(days=4)
    with patch.object(cal, "_fetch_calendar", return_value=_make_calendar(future)):
        result = cal.days_to_earnings("AAPL")
    assert result == 4

def test_is_in_blackout_true():
    cal = EarningsCalendar()
    future = date.today() + timedelta(days=2)
    with patch.object(cal, "_fetch_calendar", return_value=_make_calendar(future)):
        assert cal.is_in_blackout("AAPL", blackout_days=3) is True

def test_is_in_blackout_false():
    cal = EarningsCalendar()
    future = date.today() + timedelta(days=10)
    with patch.object(cal, "_fetch_calendar", return_value=_make_calendar(future)):
        assert cal.is_in_blackout("AAPL", blackout_days=3) is False

def test_is_in_blackout_handles_empty():
    cal = EarningsCalendar()
    with patch.object(cal, "_fetch_calendar", return_value=pd.DataFrame()):
        assert cal.is_in_blackout("AAPL", blackout_days=3) is False
