"""Discovery engine — loads watchlists, runs regime-aware scans, deduplicates,
enriches with news, and writes candidates.json."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Callable

from trader.models import ScanResult
from trader.pipeline.models import Candidate, CandidateNews, CandidateSet


# ---------------------------------------------------------------------------
# Scan configurations per regime
# ---------------------------------------------------------------------------

_COMMON_FILTERS = {
    "price_above": 5,
    "vol_above": 200_000,
    "mktcap_above": 300_000_000,
}

_BULL_SCANS: list[dict] = [
    {"scan_type": "HIGH_VS_52W_HL", "market": "STK.US.MAJOR", "filters": {**_COMMON_FILTERS, "ema200_above": True}, "limit": 25},
    {"scan_type": "TOP_PERC_GAIN", "market": "STK.US.MAJOR", "filters": _COMMON_FILTERS, "limit": 25},
    {"scan_type": "MOST_ACTIVE", "market": "STK.US.MAJOR", "filters": _COMMON_FILTERS, "limit": 25},
]

_BEARISH_SCANS: list[dict] = [
    {"scan_type": "TOP_PERC_LOSE", "market": "STK.US.MAJOR", "filters": _COMMON_FILTERS, "limit": 25},
    {"scan_type": "HIGH_OPT_IMP_VOLAT", "market": "STK.US.MAJOR", "filters": _COMMON_FILTERS, "limit": 25},
    {"scan_type": "HIGH_PUT_CALL_RATIO", "market": "STK.US.MAJOR", "filters": _COMMON_FILTERS, "limit": 25},
]

_ETF_SCANS: list[dict] = [
    {"scan_type": "MOST_ACTIVE", "market": "ETF.US", "filters": {"vol_above": 500_000}, "limit": 15},
    {"scan_type": "TOP_PERC_GAIN", "market": "ETF.US", "filters": {"vol_above": 500_000}, "limit": 15},
]

_REGIME_SCAN_MAP: dict[str, list[dict]] = {
    "bull": _BULL_SCANS + [_BEARISH_SCANS[1]] + _ETF_SCANS,  # high IV for hedging
    "caution": _BULL_SCANS + _BEARISH_SCANS + _ETF_SCANS,
    "bear": [_BULL_SCANS[2]] + _BEARISH_SCANS + _ETF_SCANS,  # most active only
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
            market=s["market"],
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
            _scan_results_to_candidates(results, scan_cfg["scan_type"], scan_cfg["market"])
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
) -> dict[str, list[Candidate]]:
    """Enrich top candidates with news."""
    # Flatten, sort by priority then scan_score
    all_candidates = [c for cands in sectors.values() for c in cands]
    all_candidates.sort(
        key=lambda c: (0 if c.priority == "high" else 1, -c.scan_score)
    )
    top_tickers = [c.ticker for c in all_candidates[:top_n]]

    if not top_tickers:
        return sectors

    try:
        news_items = await news_fn(tickers=top_tickers, limit=3)
    except Exception:
        return sectors

    # Index news by ticker
    news_by_ticker: dict[str, list[CandidateNews]] = {}
    for item in news_items:
        ticker = getattr(item, "ticker", None)
        if ticker:
            news_by_ticker.setdefault(ticker, []).append(
                CandidateNews(headline=item.headline, sentiment=0.0)
            )

    # Apply news to candidates
    for sector_candidates in sectors.values():
        for i, c in enumerate(sector_candidates):
            if c.ticker in news_by_ticker:
                sector_candidates[i] = c.model_copy(update={
                    "news": news_by_ticker[c.ticker],
                })

    return sectors


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_discover(
    regime: str,
    watchlist_path: Path,
    pipeline_dir: Path,
    scan_fn: Callable,
    news_fn: Callable,
) -> CandidateSet:
    """Run the full discovery pipeline synchronously.

    Parameters
    ----------
    regime : str
        Market regime: "bull", "caution", or "bear".
    watchlist_path : Path
        Path to watchlists.json.
    pipeline_dir : Path
        Directory to write candidates.json into.
    scan_fn : Callable
        async (scan_type, market, filters, limit) -> list[ScanResult]
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

    # 2. Run regime-aware scans (async under the hood)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    async def _async_pipeline() -> dict[str, list[Candidate]]:
        scan_candidates = await _run_all_scans(regime, scan_fn)
        sectors = _merge_candidates(watchlist_candidates, scan_candidates)
        sectors = await _enrich_with_news(sectors, news_fn)
        return sectors

    if loop and loop.is_running():
        # Already in an async context — use nest_asyncio or run in thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            sectors = pool.submit(lambda: asyncio.run(_async_pipeline())).result()
    else:
        sectors = asyncio.run(_async_pipeline())

    # 3. Build CandidateSet
    candidate_set = CandidateSet(
        run_id=run_id,
        regime=regime,
        sectors=sectors,
    )

    # 4. Write candidates.json
    pipeline_dir.mkdir(parents=True, exist_ok=True)
    out_path = pipeline_dir / "candidates.json"
    out_path.write_text(candidate_set.model_dump_json(indent=2))

    return candidate_set
