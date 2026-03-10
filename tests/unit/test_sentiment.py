from trader.news.sentiment import SentimentScorer
from trader.models import NewsItem

def make_item(headline: str, summary: str = "") -> NewsItem:
    return NewsItem(id="1", ticker="AAPL", headline=headline,
                    summary=summary, published_at="2026-03-10T10:00:00Z")

def test_bullish_signal():
    scorer = SentimentScorer()
    items = [make_item("Apple surges after record earnings beat analyst estimates")]
    result = scorer.score("AAPL", items, lookback_hours=24)
    assert result.signal == "bullish"
    assert result.score > 0

def test_bearish_signal():
    scorer = SentimentScorer()
    items = [make_item("Apple misses earnings, stock declines on weak guidance cut")]
    result = scorer.score("AAPL", items, lookback_hours=24)
    assert result.signal == "bearish"
    assert result.score < 0

def test_neutral_signal():
    scorer = SentimentScorer()
    items = [make_item("Apple announces quarterly results in line with expectations")]
    result = scorer.score("AAPL", items, lookback_hours=24)
    assert result.signal == "neutral"

def test_empty_returns_neutral():
    scorer = SentimentScorer()
    result = scorer.score("AAPL", [], lookback_hours=24)
    assert result.signal == "neutral"
    assert result.score == 0.0
    assert result.article_count == 0

def test_top_headlines_capped_at_3():
    scorer = SentimentScorer()
    items = [make_item(f"Apple beats estimate {i}") for i in range(10)]
    result = scorer.score("AAPL", items, lookback_hours=24)
    assert len(result.top_headlines) <= 3
