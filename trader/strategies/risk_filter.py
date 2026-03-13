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
        stop_pct: float | None = None,
        dividend_calendar=None,
        ticker: str | None = None,
        ex_div_within_days: int = 5,
    ) -> dict:
        if signal != 1:
            return {"signal": signal, "filtered": False, "filter_reason": None}

        # Stop-breach
        if stop_pct is not None and position is not None and quote is not None and quote.last and position.avg_cost is not None:
            if quote.last < position.avg_cost * (1 - stop_pct):
                return {"signal": 0, "filtered": True, "filter_reason": "stop_breach"}

        # Ex-dividend proximity
        if dividend_calendar is not None and ticker:
            if dividend_calendar.is_near_ex_div(ticker, within_days=ex_div_within_days):
                return {"signal": 0, "filtered": True, "filter_reason": "near_ex_div"}

        # Bearish sentiment gate
        if sentiment and sentiment.score < min_sentiment:
            return {"signal": 0, "filtered": True, "filter_reason": "sentiment_bearish"}

        # Position limit
        if position is not None and account_value and quote is not None and quote.last:
            if abs(position.qty) * quote.last / account_value >= max_position_pct:
                return {"signal": 0, "filtered": True, "filter_reason": "position_limit"}

        return {"signal": signal, "filtered": False, "filter_reason": None}
