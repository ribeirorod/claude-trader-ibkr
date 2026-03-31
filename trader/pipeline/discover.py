"""Discovery engine — loads watchlists, runs regime-aware scans, deduplicates,
enriches with news, and writes candidates.json."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Callable

from trader.models import ScanResult
from trader.news.sentiment import SentimentScorer, _score_item
from trader.pipeline.models import Candidate, CandidateNews, CandidateSet, GeoContext


# ---------------------------------------------------------------------------
# Scan configurations per regime
# ---------------------------------------------------------------------------

_COMMON_FILTERS: list[dict] = [
    {"code": "priceAbove", "value": 5},
    {"code": "volumeAbove", "value": 200_000},
    {"code": "marketCapAbove1e6", "value": 300},  # IBKR uses millions
]

_ETF_FILTERS: list[dict] = [
    {"code": "volumeAbove", "value": 500_000},
]

_BULL_SCANS: list[dict] = [
    {"scan_type": "HIGH_VS_52W_HL", "location": "STK.US.MAJOR", "filters": _COMMON_FILTERS, "limit": 25},
    {"scan_type": "TOP_PERC_GAIN", "location": "STK.US.MAJOR", "filters": _COMMON_FILTERS, "limit": 25},
    {"scan_type": "MOST_ACTIVE", "location": "STK.US.MAJOR", "filters": _COMMON_FILTERS, "limit": 25},
]

_BEARISH_SCANS: list[dict] = [
    {"scan_type": "TOP_PERC_LOSE", "location": "STK.US.MAJOR", "filters": _COMMON_FILTERS, "limit": 25},
    {"scan_type": "HIGH_OPT_IMP_VOLAT", "location": "STK.US.MAJOR", "filters": _COMMON_FILTERS, "limit": 25},
    {"scan_type": "HIGH_OPT_VOLUME_PUT_CALL_RATIO", "location": "STK.US.MAJOR", "filters": _COMMON_FILTERS, "limit": 25},
]

# EU equity scans — Frankfurt (IBIS), Amsterdam (AEB), London (LSE)
_EU_BULL_SCANS: list[dict] = [
    {"scan_type": "TOP_PERC_GAIN", "location": "STK.EU.IBIS", "filters": _COMMON_FILTERS, "limit": 20},
    {"scan_type": "MOST_ACTIVE", "location": "STK.EU.IBIS", "filters": _COMMON_FILTERS, "limit": 20},
    {"scan_type": "TOP_PERC_GAIN", "location": "STK.EU.AEB", "filters": _COMMON_FILTERS, "limit": 15},
    {"scan_type": "MOST_ACTIVE", "location": "STK.EU.LSE", "filters": _COMMON_FILTERS, "limit": 15},
]

_EU_BEARISH_SCANS: list[dict] = [
    {"scan_type": "TOP_PERC_LOSE", "location": "STK.EU.IBIS", "filters": _COMMON_FILTERS, "limit": 20},
    {"scan_type": "TOP_PERC_LOSE", "location": "STK.EU.AEB", "filters": _COMMON_FILTERS, "limit": 15},
    {"scan_type": "TOP_PERC_LOSE", "location": "STK.EU.LSE", "filters": _COMMON_FILTERS, "limit": 15},
]

_ETF_SCANS: list[dict] = [
    {"scan_type": "MOST_ACTIVE", "location": "ETF.EQ.US", "filters": _ETF_FILTERS, "limit": 15},
    {"scan_type": "TOP_PERC_GAIN", "location": "ETF.EQ.US", "filters": _ETF_FILTERS, "limit": 15},
]

_REGIME_SCAN_MAP: dict[str, list[dict]] = {
    "bull": _BULL_SCANS + _EU_BULL_SCANS + [_BEARISH_SCANS[1]] + _ETF_SCANS,
    "caution": _BULL_SCANS + _EU_BULL_SCANS + _BEARISH_SCANS + _EU_BEARISH_SCANS + _ETF_SCANS,
    "bear": [_BULL_SCANS[2]] + _BEARISH_SCANS + _EU_BEARISH_SCANS + _ETF_SCANS,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_watchlist(watchlist_path: Path) -> dict[str, str]:
    """Return {ticker: sector} from all watchlists."""
    if not watchlist_path.exists():
        return {}
    data = json.loads(watchlist_path.read_text())
    ticker_sector: dict[str, str] = {}
    for _name, wl in data.items():
        tickers = wl.get("tickers", [])
        sectors = wl.get("sectors", {})
        for t in tickers:
            if t not in ticker_sector:
                ticker_sector[t] = sectors.get(t, "")
    return ticker_sector


def _scan_results_to_candidates(results: list[ScanResult], scan_type: str, market: str) -> list[Candidate]:
    """Convert scan results into Candidate objects."""
    asset_class = "etf" if "ETF" in market else "stock"
    candidates: list[Candidate] = []
    for r in results:
        candidates.append(Candidate(
            ticker=r.symbol,
            source="discovery",
            priority="normal",
            asset_class=asset_class,
            sector=r.sector or "",
            scan_sources=[scan_type],
            scan_score=1,
        ))
    return candidates


async def _run_all_scans(
    regime: str,
    scan_fn: Callable,
) -> list[Candidate]:
    """Run all scans for the given regime and return flat list of candidates."""
    scans = _REGIME_SCAN_MAP.get(regime, _REGIME_SCAN_MAP["caution"])
    tasks = [
        scan_fn(
            scan_type=s["scan_type"],
            location=s["location"],
            filters=s["filters"],
            limit=s["limit"],
        )
        for s in scans
    ]
    results_per_scan = await asyncio.gather(*tasks, return_exceptions=True)

    all_candidates: list[Candidate] = []
    for scan_cfg, results in zip(scans, results_per_scan):
        if isinstance(results, BaseException):
            continue
        all_candidates.extend(
            _scan_results_to_candidates(results, scan_cfg["scan_type"], scan_cfg["location"])
        )
    return all_candidates


def _merge_candidates(
    watchlist_candidates: list[Candidate],
    scan_candidates: list[Candidate],
) -> dict[str, list[Candidate]]:
    """Merge watchlist and scan candidates, deduplicating (watchlist wins).
    Returns sectors dict."""
    seen: dict[str, Candidate] = {}

    # Watchlist first — they always win
    for c in watchlist_candidates:
        seen[c.ticker] = c

    # Scan candidates — merge scan_sources if already seen, skip if watchlist
    for c in scan_candidates:
        if c.ticker in seen:
            existing = seen[c.ticker]
            if existing.source == "watchlist":
                # Add scan info but keep watchlist priority
                merged_sources = list(set(existing.scan_sources + c.scan_sources))
                seen[c.ticker] = existing.model_copy(update={
                    "scan_sources": merged_sources,
                    "scan_score": existing.scan_score + c.scan_score,
                })
            else:
                # Both discovery — merge scan sources
                merged_sources = list(set(existing.scan_sources + c.scan_sources))
                seen[c.ticker] = existing.model_copy(update={
                    "scan_sources": merged_sources,
                    "scan_score": existing.scan_score + c.scan_score,
                })
        else:
            seen[c.ticker] = c

    # Group by sector
    sectors: dict[str, list[Candidate]] = {}
    for candidate in seen.values():
        sector = candidate.sector or "Unknown"
        sectors.setdefault(sector, []).append(candidate)

    return sectors


async def _enrich_with_news(
    sectors: dict[str, list[Candidate]],
    news_fn: Callable,
    top_n: int = 20,
    cache_path: Path | None = None,
    cache_ttl_hours: float = 4.0,
) -> tuple[dict[str, list[Candidate]], dict[str, float]]:
    """Enrich top candidates with news and compute per-ticker sentiment."""
    # Flatten, sort by priority then scan_score
    all_candidates = [c for cands in sectors.values() for c in cands]
    all_candidates.sort(
        key=lambda c: (0 if c.priority == "high" else 1, -c.scan_score)
    )
    top_tickers = [c.ticker for c in all_candidates[:top_n]]

    if not top_tickers:
        return sectors, {}

    # Try cache first, then live API for misses
    all_news_items: list = []
    cache_misses: list[str] = []

    if cache_path:
        from trader.news.cache import read_cache
        for ticker in top_tickers:
            cached = read_cache(cache_path, ticker, ttl_hours=cache_ttl_hours)
            if cached:
                all_news_items.extend(cached)
            else:
                cache_misses.append(ticker)
    else:
        cache_misses = top_tickers

    # Fetch remaining from live API
    if cache_misses:
        try:
            live_items = await news_fn(tickers=cache_misses, limit=5 * len(cache_misses))
            all_news_items.extend(live_items)
        except Exception:
            pass

    news_items = all_news_items

    if not news_items:
        return sectors, {}

    # Group raw NewsItems by ticker for SentimentScorer
    from trader.models import NewsItem
    raw_by_ticker: dict[str, list[NewsItem]] = {}
    for item in news_items:
        ticker = getattr(item, "ticker", None)
        if ticker:
            raw_by_ticker.setdefault(ticker, []).append(item)

    # Compute per-ticker aggregate sentiment
    scorer = SentimentScorer()
    ticker_sentiment: dict[str, float] = {}
    for ticker, items in raw_by_ticker.items():
        result = scorer.score(ticker=ticker, items=items)
        ticker_sentiment[ticker] = result.score

    # Build per-headline CandidateNews with real sentiment scores
    news_by_ticker: dict[str, list[CandidateNews]] = {}
    for ticker, items in raw_by_ticker.items():
        for item in items:
            raw_score = _score_item(item)
            clamped = max(-1.0, min(1.0, raw_score * 10))
            news_by_ticker.setdefault(ticker, []).append(
                CandidateNews(headline=item.headline, sentiment=clamped)
            )

    # Apply news to candidates
    for sector_candidates in sectors.values():
        for i, c in enumerate(sector_candidates):
            if c.ticker in news_by_ticker:
                sector_candidates[i] = c.model_copy(update={
                    "news": news_by_ticker[c.ticker],
                })

    return sectors, ticker_sentiment


# ---------------------------------------------------------------------------
# Geopolitical / macro context
# ---------------------------------------------------------------------------

_GEO_TICKERS = ["SPY", "QQQ", "GLD", "TLT", "VIX", "DXY"]
_GEO_KEYWORDS_HIGH = ["war", "invasion", "sanctions", "nuclear", "default", "crash", "collapse"]
_GEO_KEYWORDS_MEDIUM = ["tariff", "trade war", "fed rate", "recession", "geopolitical", "conflict",
                         "escalation", "embargo", "crisis", "shutdown"]
_SECTOR_KEYWORDS = {
    "energy": ["oil", "opec", "energy", "crude", "gas", "pipeline"],
    "semiconductors": ["chip", "semiconductor", "tsmc", "nvidia", "export ban"],
    "defense": ["defense", "military", "nato", "missile", "arms"],
    "finance": ["bank", "fed", "rate", "yield", "treasury", "credit"],
    "technology": ["tech", "ai", "regulation", "antitrust", "big tech"],
}


async def _scan_geo_context(news_fn: Callable) -> GeoContext:
    """Scan macro/geopolitical news headlines and return a GeoContext."""
    try:
        items = await news_fn(tickers=_GEO_TICKERS, limit=10)
    except Exception:
        return GeoContext()

    if not items:
        return GeoContext()

    events: list[str] = []
    affected: set[str] = set()
    high_count = 0
    medium_count = 0

    for item in items:
        text = (item.headline + " " + getattr(item, "summary", "")).lower()
        for kw in _GEO_KEYWORDS_HIGH:
            if kw in text:
                high_count += 1
                events.append(item.headline)
                break
        else:
            for kw in _GEO_KEYWORDS_MEDIUM:
                if kw in text:
                    medium_count += 1
                    events.append(item.headline)
                    break

        for sector, keywords in _SECTOR_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                affected.add(sector)

    # Deduplicate events
    seen: set[str] = set()
    unique_events: list[str] = []
    for e in events:
        if e not in seen:
            seen.add(e)
            unique_events.append(e)

    if high_count >= 2:
        severity = "high"
    elif high_count >= 1 or medium_count >= 3:
        severity = "medium"
    elif medium_count >= 1:
        severity = "low"
    else:
        severity = "none"

    return GeoContext(
        severity=severity,
        events=unique_events[:5],
        affected_sectors=sorted(affected),
        block_new_longs=severity == "high",
        hedge_suggested=severity in ("high", "medium"),
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def run_discover(
    regime: str,
    watchlist_path: Path,
    pipeline_dir: Path,
    scan_fn: Callable,
    news_fn: Callable,
) -> CandidateSet:
    """Run the full discovery pipeline.

    Parameters
    ----------
    regime : str
        Market regime: "bull", "caution", or "bear".
    watchlist_path : Path
        Path to watchlists.json.
    pipeline_dir : Path
        Directory to write candidates.json into.
    scan_fn : Callable
        async (scan_type, location, filters, limit) -> list[ScanResult]
    news_fn : Callable
        async (tickers, limit) -> list[NewsItem]
    """
    run_id = uuid.uuid4().hex[:12]

    # 1. Load watchlist tickers as high-priority candidates
    wl_tickers = _load_watchlist(watchlist_path)
    watchlist_candidates = [
        Candidate(
            ticker=ticker,
            source="watchlist",
            priority="high",
            sector=sector,
        )
        for ticker, sector in wl_tickers.items()
    ]

    # 2. Run regime-aware scans + geo context in parallel
    scan_candidates, geo_context = await asyncio.gather(
        _run_all_scans(regime, scan_fn),
        _scan_geo_context(news_fn),
    )
    sectors = _merge_candidates(watchlist_candidates, scan_candidates)
    cache_path = pipeline_dir / "news-cache.json"
    sectors, ticker_sentiment = await _enrich_with_news(
        sectors, news_fn, cache_path=cache_path,
    )

    # 3. Build CandidateSet
    candidate_set = CandidateSet(
        run_id=run_id,
        regime=regime,
        sectors=sectors,
        geo_context=geo_context,
        ticker_sentiment=ticker_sentiment,
    )

    # 4. Write candidates.json
    pipeline_dir.mkdir(parents=True, exist_ok=True)
    out_path = pipeline_dir / "candidates.json"
    out_path.write_text(candidate_set.model_dump_json(indent=2))

    return candidate_set
