# tests/unit/test_cli_news_scrape.py
from __future__ import annotations
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from click.testing import CliRunner
from trader.cli.__main__ import cli
from trader.models import NewsItem


FAKE_ITEMS = [
    NewsItem(
        id="abc123",
        ticker="AAPL",
        headline="Apple beats estimates",
        summary="",
        published_at="2026-04-03T15:56:00",
        source="Reuters",
        url="https://example.com/article1",
    )
]


def test_scrape_command_outputs_json():
    runner = CliRunner()

    with patch(
        "trader.cli.news.WebScrapeProvider"
    ) as MockProvider:
        instance = MockProvider.return_value
        instance.get_news = AsyncMock(return_value=FAKE_ITEMS)
        instance.aclose = AsyncMock()

        result = runner.invoke(
            cli, ["news", "scrape", "AAPL", "--limit", "5"],
        )

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["headline"] == "Apple beats estimates"


def test_scrape_command_accepts_multiple_tickers():
    runner = CliRunner()

    with patch(
        "trader.cli.news.WebScrapeProvider"
    ) as MockProvider:
        instance = MockProvider.return_value
        instance.get_news = AsyncMock(return_value=FAKE_ITEMS * 2)
        instance.aclose = AsyncMock()

        result = runner.invoke(
            cli, ["news", "scrape", "AAPL,MSFT", "--limit", "3"],
        )

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert len(data) == 2
