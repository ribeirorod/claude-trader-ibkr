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
