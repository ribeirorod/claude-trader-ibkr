from __future__ import annotations
from typing import Literal
from pydantic import BaseModel


class NewsItem(BaseModel):
    id: str
    ticker: str | None = None
    headline: str
    summary: str = ""
    published_at: str
    source: str = ""
    url: str = ""


class SentimentResult(BaseModel):
    ticker: str
    score: float
    signal: Literal["bullish", "bearish", "neutral"]
    article_count: int
    lookback_hours: int
    top_headlines: list[str]
