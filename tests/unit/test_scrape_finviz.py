# tests/unit/test_scrape_finviz.py
from __future__ import annotations
import pytest
from trader.models import NewsItem


SAMPLE_HTML = """
<html><body>
<table id="news-table" class="fullview-news-outer news-table" data-ticker="AAPL">
  <tr class="cursor-pointer has-label">
    <td width="130" align="right">Apr-03-26 03:56PM</td>
    <td align="left">
      <div class="news-link-container">
        <div class="news-link-left">
          <a class="tab-link-news" href="https://example.com/article1" target="_blank">
            Apple beats Q2 earnings estimates
          </a>
        </div>
        <div class="news-link-right"><span>(Reuters)</span></div>
      </div>
    </td>
  </tr>
  <tr class="cursor-pointer has-label">
    <td width="130" align="right">Apr-02-26</td>
    <td align="left">
      <div class="news-link-container">
        <div class="news-link-left">
          <a class="tab-link-news" href="https://example.com/article2" target="_blank">
            iPhone sales surge in China
          </a>
        </div>
        <div class="news-link-right"><span>(Bloomberg)</span></div>
      </div>
    </td>
  </tr>
</table>
</body></html>
"""


def test_parse_finviz_news_extracts_articles():
    from trader.news.scrape_finviz import parse_finviz_news

    items = parse_finviz_news("AAPL", SAMPLE_HTML)
    assert len(items) == 2

    assert items[0].ticker == "AAPL"
    assert items[0].headline == "Apple beats Q2 earnings estimates"
    assert items[0].source == "Reuters"
    assert items[0].url == "https://example.com/article1"
    assert "2026-04-03" in items[0].published_at

    assert items[1].headline == "iPhone sales surge in China"
    assert items[1].source == "Bloomberg"
    assert "2026-04-02" in items[1].published_at


def test_parse_finviz_news_handles_empty_html():
    from trader.news.scrape_finviz import parse_finviz_news

    items = parse_finviz_news("AAPL", "<html><body></body></html>")
    assert items == []


def test_parse_finviz_news_handles_today_date():
    from trader.news.scrape_finviz import parse_finviz_news
    import datetime as dt

    html = """
    <table id="news-table">
      <tr class="cursor-pointer">
        <td width="130" align="right">Today 08:07AM</td>
        <td align="left">
          <div class="news-link-container">
            <div class="news-link-left">
              <a class="tab-link-news" href="https://example.com/a">Some headline</a>
            </div>
            <div class="news-link-right"><span>(CNBC)</span></div>
          </div>
        </td>
      </tr>
    </table>
    """
    items = parse_finviz_news("AAPL", html)
    assert len(items) == 1
    today_str = dt.date.today().isoformat()
    assert today_str in items[0].published_at


def test_parse_finviz_news_respects_limit():
    from trader.news.scrape_finviz import parse_finviz_news

    items = parse_finviz_news("AAPL", SAMPLE_HTML, limit=1)
    assert len(items) == 1
