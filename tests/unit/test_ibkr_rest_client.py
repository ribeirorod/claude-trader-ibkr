import pytest, respx, httpx
from trader.adapters.ibkr_rest.client import IBKRRestClient
from trader.config import Config

@pytest.fixture
def client():
    config = Config()
    config.ib_host = "localhost"
    config.ib_port = 5000
    return IBKRRestClient(config)

@pytest.mark.asyncio
async def test_get_request(client):
    with respx.mock:
        respx.get("https://localhost:5000/v1/api/test").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        result = await client.get("/test")
        assert result == {"ok": True}

@pytest.mark.asyncio
async def test_post_request(client):
    with respx.mock:
        respx.post("https://localhost:5000/v1/api/orders").mock(
            return_value=httpx.Response(200, json={"order_id": "123"})
        )
        result = await client.post("/orders", json={"ticker": "AAPL"})
        assert result["order_id"] == "123"
