from __future__ import annotations
import re
from trader.models import NewsItem, SentimentResult

_BULLISH = {
    "beat", "beats", "surge", "surges", "surging", "rally", "rallies",
    "upgrade", "upgraded", "strong", "growth", "record", "positive",
    "outperform", "raise", "raised", "exceed", "exceeds", "profit",
    "buy", "bullish", "gain", "gains", "high", "higher", "rise", "rises",
}
_BEARISH = {
    "miss", "misses", "missed", "decline", "declines", "declining",
    "downgrade", "downgraded", "weak", "loss", "losses", "cut", "cuts",
    "risk", "negative", "recall", "lawsuit", "sell", "bearish", "low",
    "lower", "fall", "falls", "drop", "drops", "concern", "warning",
}

def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z]+", text.lower())

def _score_item(item: NewsItem) -> float:
    tokens = _tokenize(item.headline + " " + item.summary)
    if not tokens:
        return 0.0
    bull = sum(1 for t in tokens if t in _BULLISH)
    bear = sum(1 for t in tokens if t in _BEARISH)
    return (bull - bear) / len(tokens)

class SentimentScorer:
    def score(
        self,
        ticker: str,
        items: list[NewsItem],
        lookback_hours: int = 24,
    ) -> SentimentResult:
        if not items:
            return SentimentResult(
                ticker=ticker, score=0.0, signal="neutral",
                article_count=0, lookback_hours=lookback_hours, top_headlines=[]
            )

        scored = sorted(
            [(item, _score_item(item)) for item in items],
            key=lambda x: abs(x[1]),
            reverse=True,
        )
        avg_score = sum(s for _, s in scored) / len(scored)
        clamped = max(-1.0, min(1.0, avg_score * 10))

        if clamped > 0.1:
            signal = "bullish"
        elif clamped < -0.1:
            signal = "bearish"
        else:
            signal = "neutral"

        return SentimentResult(
            ticker=ticker,
            score=round(clamped, 3),
            signal=signal,
            article_count=len(items),
            lookback_hours=lookback_hours,
            top_headlines=[item.headline for item, _ in scored[:3]],
        )
