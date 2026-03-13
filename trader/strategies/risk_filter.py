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
        earnings_calendar=None,
        fundamental_screener=None,
        ticker: str | None = None,
        ex_div_within_days: int = 5,
        earnings_blackout_days: int = 3,
    ) -> dict:
        if signal != 1:
            return {"signal": signal, "filtered": False, "filter_reason": None}

        if stop_pct is not None and position is not None and quote is not None and quote.last and position.avg_cost is not None:
            if quote.last < position.avg_cost * (1 - stop_pct):
                return {"signal": 0, "filtered": True, "filter_reason": "stop_breach"}

        if dividend_calendar is not None and ticker:
            if dividend_calendar.is_near_ex_div(ticker, within_days=ex_div_within_days):
                return {"signal": 0, "filtered": True, "filter_reason": "near_ex_div"}

        if earnings_calendar is not None and ticker:
            if earnings_calendar.is_in_blackout(ticker, blackout_days=earnings_blackout_days):
                return {"signal": 0, "filtered": True, "filter_reason": "earnings_blackout"}

        if fundamental_screener is not None and ticker:
            check = fundamental_screener.check(ticker)
            if not check["pass"]:
                return {"signal": 0, "filtered": True, "filter_reason": "fundamental_veto"}

        if sentiment and sentiment.score < min_sentiment:
            return {"signal": 0, "filtered": True, "filter_reason": "sentiment_bearish"}

        if position is not None and account_value and quote is not None and quote.last:
            if abs(position.qty) * quote.last / account_value >= max_position_pct:
                return {"signal": 0, "filtered": True, "filter_reason": "position_limit"}

        return {"signal": signal, "filtered": False, "filter_reason": None}
