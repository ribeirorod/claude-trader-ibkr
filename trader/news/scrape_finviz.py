# trader/news/scrape_finviz.py
"""Scrape news headlines from Finviz quote pages."""
from __future__ import annotations

import datetime as dt
import hashlib
import logging
import re

import httpx
from selectolax.parser import HTMLParser

from trader.models import NewsItem

logger = logging.getLogger(__name__)

_FINVIZ_URL = "https://finviz.com/quote.ashx"
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Matches "Apr-03-26 03:56PM" or "Apr-03-26" (no time)
_DATE_RE = re.compile(
    r"([A-Z][a-z]{2})-(\d{2})-(\d{2})\s*(\d{1,2}:\d{2}(?:AM|PM))?"
)
# Matches "Today 08:07AM" or "Yesterday 03:56PM"
_RELATIVE_RE = re.compile(r"(Today|Yesterday)\s+(\d{1,2}:\d{2}(?:AM|PM))")


def _parse_finviz_date(raw: str) -> str:
    """Convert Finviz date string to ISO 8601."""
    raw = raw.strip()

    m = _RELATIVE_RE.match(raw)
    if m:
        today = dt.date.today()
        if m.group(1) == "Yesterday":
            today -= dt.timedelta(days=1)
        time_part = dt.datetime.strptime(m.group(2), "%I:%M%p").time()
        return dt.datetime.combine(today, time_part).isoformat()

    m = _DATE_RE.match(raw)
    if m:
        month_str, day_str, year_str = m.group(1), m.group(2), m.group(3)
        year = 2000 + int(year_str)
        month = dt.datetime.strptime(month_str, "%b").month
        day = int(day_str)
        date = dt.date(year, month, day)
        if m.group(4):
            time_part = dt.datetime.strptime(m.group(4), "%I:%M%p").time()
            return dt.datetime.combine(date, time_part).isoformat()
        return dt.datetime.combine(date, dt.time()).isoformat()

    return dt.datetime.now().isoformat()


def _make_id(url: str, headline: str) -> str:
    """Deterministic ID from URL + headline."""
    return hashlib.md5((url + headline).encode()).hexdigest()[:12]


def parse_finviz_news(
    ticker: str, html: str, *, limit: int = 20
) -> list[NewsItem]:
    """Parse Finviz news table HTML into NewsItem list."""
    tree = HTMLParser(html)
    table = tree.css_first("#news-table, .news-table")
    if table is None:
        return []

    items: list[NewsItem] = []
    for row in table.css("tr"):
        if len(items) >= limit:
            break

        tds = row.css("td")
        if len(tds) < 2:
            continue

        date_text = tds[0].text(strip=True)
        link_node = tds[1].css_first("a.tab-link-news")
        if link_node is None:
            continue

        headline = link_node.text(strip=True)
        url = link_node.attributes.get("href", "")

        source_node = tds[1].css_first(".news-link-right span")
        source = ""
        if source_node:
            source = source_node.text(strip=True).strip("()")

        items.append(
            NewsItem(
                id=_make_id(url, headline),
                ticker=ticker,
                headline=headline,
                summary="",
                published_at=_parse_finviz_date(date_text),
                source=source or "finviz",
                url=url,
            )
        )

    return items


async def fetch_finviz_news(
    client: httpx.AsyncClient,
    ticker: str,
    *,
    limit: int = 20,
) -> list[NewsItem]:
    """Fetch and parse Finviz news for a single ticker."""
    try:
        r = await client.get(
            _FINVIZ_URL,
            params={"t": ticker},
            headers={"User-Agent": _USER_AGENT},
        )
        r.raise_for_status()
    except Exception as exc:
        logger.warning("finviz scrape failed for %s: %s", ticker, exc)
        return []

    return parse_finviz_news(ticker, r.text, limit=limit)
