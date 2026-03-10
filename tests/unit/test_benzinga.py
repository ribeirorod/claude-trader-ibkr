import pytest, respx, httpx
from trader.news.benzinga import BenzingaClient
from trader.config import Config

@pytest.fixture
def client():
    config = Config()
    config.benzinga_api_key = "test_key"
    return BenzingaClient(config)

@pytest.mark.asyncio
async def test_get_news_returns_items(client):
    mock_response = [
        {"id": "1", "title": "Apple beats earnings", "teaser": "AAPL up 5%",
         "created": "2026-03-10T10:00:00Z", "author": "Benzinga",
         "url": "http://example.com",
         "stocks": [{"name": "AAPL"}]}
    ]
    with respx.mock:
        respx.get("https://api.benzinga.com/api/v2/news").mock(
            return_value=httpx.Response(200, json=mock_response)
        )
        items = await client.get_news(["AAPL"], limit=5)
    assert len(items) == 1
    assert items[0].headline == "Apple beats earnings"
    assert items[0].ticker == "AAPL"

@pytest.mark.asyncio
async def test_get_news_empty_response(client):
    with respx.mock:
        respx.get("https://api.benzinga.com/api/v2/news").mock(
            return_value=httpx.Response(200, json=[])
        )
        items = await client.get_news(["AAPL"])
    assert items == []
