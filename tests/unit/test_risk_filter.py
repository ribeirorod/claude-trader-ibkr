from trader.strategies.risk_filter import RiskFilter
from trader.models import Quote, SentimentResult

def make_quote(last=100.0):
    return Quote(ticker="AAPL", last=last, bid=99.9, ask=100.1)

def make_sentiment(score=0.0):
    sig = "bullish" if score > 0.1 else "bearish" if score < -0.1 else "neutral"
    return SentimentResult(ticker="AAPL", score=score, signal=sig,
                           article_count=5, lookback_hours=24, top_headlines=[])

def test_buy_suppressed_on_bearish_news():
    rf = RiskFilter()
    result = rf.filter(signal=1, quote=make_quote(), position=None,
                       sentiment=make_sentiment(-0.5))
    assert result["signal"] == 0
    assert result["filtered"] is True
    assert "sentiment" in result["filter_reason"]

def test_buy_passes_on_neutral_news():
    rf = RiskFilter()
    result = rf.filter(signal=1, quote=make_quote(), position=None,
                       sentiment=make_sentiment(0.0))
    assert result["signal"] == 1
    assert result["filtered"] is False

def test_sell_never_suppressed():
    rf = RiskFilter()
    result = rf.filter(signal=-1, quote=make_quote(), position=None,
                       sentiment=make_sentiment(-0.9))
    assert result["signal"] == -1
    assert result["filtered"] is False

from trader.models import Position

def make_position(avg_cost=90.0, qty=10):
    return Position(
        ticker="AAPL", qty=qty, avg_cost=avg_cost,
        market_value=qty * 100.0, unrealized_pnl=(100.0 - avg_cost) * qty,
    )

def test_buy_suppressed_when_stop_breached():
    rf = RiskFilter()
    # avg_cost=110, stop_pct=0.05 → stop=104.5; current price=100 → breach
    pos = make_position(avg_cost=110.0)
    result = rf.filter(
        signal=1,
        quote=make_quote(last=100.0),
        position=pos,
        sentiment=None,
        stop_pct=0.05,
    )
    assert result["signal"] == 0
    assert result["filter_reason"] == "stop_breach"

def test_buy_passes_when_above_stop():
    rf = RiskFilter()
    pos = make_position(avg_cost=90.0)
    result = rf.filter(
        signal=1,
        quote=make_quote(last=100.0),
        position=pos,
        sentiment=None,
        stop_pct=0.05,
    )
    assert result["signal"] == 1

def test_buy_suppressed_near_ex_div():
    from unittest.mock import MagicMock
    rf = RiskFilter()
    mock_cal = MagicMock()
    mock_cal.is_near_ex_div.return_value = True
    result = rf.filter(
        signal=1, quote=make_quote(), position=None, sentiment=None,
        dividend_calendar=mock_cal, ticker="AAPL",
    )
    assert result["signal"] == 0
    assert result["filter_reason"] == "near_ex_div"

def test_buy_passes_when_not_near_ex_div():
    from unittest.mock import MagicMock
    rf = RiskFilter()
    mock_cal = MagicMock()
    mock_cal.is_near_ex_div.return_value = False
    result = rf.filter(
        signal=1, quote=make_quote(), position=None, sentiment=None,
        dividend_calendar=mock_cal, ticker="AAPL",
    )
    assert result["signal"] == 1

def test_buy_suppressed_in_earnings_blackout():
    from unittest.mock import MagicMock
    rf = RiskFilter()
    mock_ecal = MagicMock()
    mock_ecal.is_in_blackout.return_value = True
    result = rf.filter(
        signal=1, quote=make_quote(), position=None, sentiment=None,
        earnings_calendar=mock_ecal, ticker="AAPL",
    )
    assert result["signal"] == 0
    assert result["filter_reason"] == "earnings_blackout"

def test_buy_passes_outside_earnings_blackout():
    from unittest.mock import MagicMock
    rf = RiskFilter()
    mock_ecal = MagicMock()
    mock_ecal.is_in_blackout.return_value = False
    result = rf.filter(
        signal=1, quote=make_quote(), position=None, sentiment=None,
        earnings_calendar=mock_ecal, ticker="AAPL",
    )
    assert result["signal"] == 1

def test_buy_suppressed_on_fundamental_veto():
    from unittest.mock import MagicMock
    rf = RiskFilter()
    mock_screener = MagicMock()
    mock_screener.check.return_value = {"pass": False, "veto_reason": "pe_too_high", "pe": 250, "eps_growth": None}
    result = rf.filter(
        signal=1, quote=make_quote(), position=None, sentiment=None,
        fundamental_screener=mock_screener, ticker="XYZ",
    )
    assert result["signal"] == 0
    assert result["filter_reason"] == "fundamental_veto"

def test_buy_passes_fundamental_check():
    from unittest.mock import MagicMock
    rf = RiskFilter()
    mock_screener = MagicMock()
    mock_screener.check.return_value = {"pass": True, "veto_reason": None, "pe": 20, "eps_growth": 0.15}
    result = rf.filter(
        signal=1, quote=make_quote(), position=None, sentiment=None,
        fundamental_screener=mock_screener, ticker="AAPL",
    )
    assert result["signal"] == 1

def test_buy_suppressed_when_position_limit_reached():
    from trader.models import Position
    rf = RiskFilter()
    # position is 5% of 100k account at $100/share = $5000 = 50 shares
    # max_position_pct=0.05 means we're exactly at the limit → suppress
    pos = Position(
        ticker="AAPL", qty=50, avg_cost=100.0,
        market_value=5000.0, unrealized_pnl=0.0,
    )
    result = rf.filter(
        signal=1,
        quote=make_quote(last=100.0),
        position=pos,
        sentiment=None,
        account_value=100_000,
        max_position_pct=0.05,
    )
    assert result["signal"] == 0
    assert result["filter_reason"] == "position_limit"


def test_buy_allowed_in_bear_regime():
    """Bear regime no longer blocks longs — strategies assess conditions, regime adjusts sizing."""
    rf = RiskFilter()
    result = rf.filter(
        signal=1,
        quote=make_quote(),
        position=None,
        sentiment=None,
        regime="bear",
    )
    assert result["signal"] == 1
    assert result["filtered"] is False


def test_buy_passes_in_bull_regime():
    rf = RiskFilter()
    result = rf.filter(
        signal=1,
        quote=make_quote(),
        position=None,
        sentiment=None,
        regime="bull",
    )
    assert result["signal"] == 1
    assert result["filtered"] is False


def test_sell_not_blocked_in_bear_regime():
    rf = RiskFilter()
    result = rf.filter(
        signal=-1,
        quote=make_quote(),
        position=None,
        sentiment=None,
        regime="bear",
    )
    assert result["signal"] == -1
    assert result["filtered"] is False


def test_buy_passes_when_regime_is_none():
    rf = RiskFilter()
    result = rf.filter(
        signal=1,
        quote=make_quote(),
        position=None,
        sentiment=None,
        regime=None,
    )
    assert result["signal"] == 1
