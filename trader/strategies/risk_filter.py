from __future__ import annotations
from trader.models import Quote, Position, SentimentResult

class RiskFilter:
    def filter(
        self,
        signal: int,
        quote: Quote | None,
        position: Position | None,
        sentiment: SentimentResult | None,
        max_position_pct: float = 0.05,
        min_sentiment: float = -0.2,
        account_value: float | None = None,
    ) -> dict:
        # Sells are never suppressed
        if signal != 1:
            return {"signal": signal, "filtered": False, "filter_reason": None}

        # Suppress buy on bearish news
        if sentiment and sentiment.score < min_sentiment:
            return {"signal": 0, "filtered": True, "filter_reason": "sentiment_bearish"}

        # Suppress buy if position too large
        if position and account_value and quote and quote.last:
            position_value = abs(position.qty) * quote.last
            if position_value / account_value >= max_position_pct:
                return {"signal": 0, "filtered": True, "filter_reason": "position_limit"}

        return {"signal": signal, "filtered": False, "filter_reason": None}
