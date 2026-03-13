from datetime import datetime, timezone, timedelta
from trader.news.sentiment import SentimentScorer
from trader.models import NewsItem

def make_item(headline: str, summary: str = "") -> NewsItem:
    return NewsItem(id="1", ticker="AAPL", headline=headline,
                    summary=summary, published_at=datetime.now(timezone.utc).isoformat())

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


_counter = [0]  # simple counter for unique item ids

def _make_item(headline: str, hours_ago: float, ticker="AAPL", item_id: str = "1") -> NewsItem:
    pub = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    # NewsItem.id is required (no default) — always pass it
    return NewsItem(id=item_id, ticker=ticker, headline=headline, summary="", published_at=pub)

def _item(headline: str, hours_ago: float, ticker="AAPL") -> NewsItem:
    _counter[0] += 1
    return _make_item(headline, hours_ago, ticker, item_id=str(_counter[0]))

def test_velocity_high_when_recent_spike():
    """10 articles in last 2h vs 2 in prior 22h → high velocity."""
    scorer = SentimentScorer()
    # 10 items in last 2h: hours_ago in [0.1, 0.2, ..., 1.0]
    recent = [_item(f"Stock surges {i}", hours_ago=i * 0.1) for i in range(1, 11)]
    # 2 items far in the past
    old = [_item(f"Old news {i}", hours_ago=5 + i) for i in range(2)]
    result = scorer.score("AAPL", recent + old, lookback_hours=24)
    assert result.article_velocity > 1.0  # recent rate >> baseline rate

def test_velocity_low_when_evenly_spaced():
    """12 articles spaced 2h apart → velocity ≈ 1.0 (recent rate ≈ baseline rate)."""
    scorer = SentimentScorer()
    # hours_ago: 2, 4, 6, ..., 24 — evenly spread across 24h window
    # ~2 items fall in last 4h; ~10 in prior 20h → rate ≈ 0.5/hr vs 0.5/hr → velocity ≈ 1.0
    items = [_item(f"News {i}", hours_ago=i * 2.0) for i in range(1, 13)]
    result = scorer.score("AAPL", items, lookback_hours=24)
    # velocity should be near 1.0 baseline, not a dramatic spike
    assert 0.3 <= result.article_velocity <= 2.0

def test_velocity_zero_when_no_articles():
    scorer = SentimentScorer()
    result = scorer.score("AAPL", [], lookback_hours=24)
    assert result.article_velocity == 0.0
