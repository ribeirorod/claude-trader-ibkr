from trader.models import OrderRequest, Order, Position, Quote, NewsItem, SentimentResult


def test_order_request_stock():
    req = OrderRequest(ticker="AAPL", qty=10, side="buy", order_type="market")
    assert req.contract_type == "stock"
    assert req.price is None


def test_order_request_option():
    req = OrderRequest(
        ticker="AAPL", qty=1, side="buy", order_type="limit",
        price=5.50, contract_type="option",
        expiry="2026-04-17", strike=200.0, right="call"
    )
    assert req.right == "call"


def test_order_request_bracket():
    req = OrderRequest(
        ticker="AAPL", qty=10, side="buy", order_type="bracket",
        price=195.0, take_profit=210.0, stop_loss=185.0
    )
    assert req.take_profit == 210.0


def test_sentiment_result_signal():
    r = SentimentResult(ticker="AAPL", score=0.5, signal="bullish",
                        article_count=5, lookback_hours=24, top_headlines=[])
    assert r.signal == "bullish"
    data = r.model_dump()
    assert "score" in data
