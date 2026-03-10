import pytest
from unittest.mock import AsyncMock, patch
from trader.adapters.ibkr_rest.adapter import IBKRRestAdapter
from trader.models import OrderRequest
from trader.config import Config

@pytest.fixture
def adapter():
    config = Config()
    config.ib_account = "DU123456"
    return IBKRRestAdapter(config)

@pytest.mark.asyncio
async def test_list_positions(adapter):
    mock_data = [{"conid": 265598, "ticker": "AAPL", "position": 10,
                  "avgCost": 190.0, "mktValue": 1950.0, "unrealizedPnl": 50.0}]
    with patch.object(adapter._client, "get", new=AsyncMock(return_value=mock_data)):
        positions = await adapter.list_positions()
    assert len(positions) == 1
    assert positions[0].ticker == "AAPL"
    assert positions[0].qty == 10

@pytest.mark.asyncio
async def test_place_market_order(adapter):
    mock_response = [{"order_id": "ord_001", "order_status": "PreSubmitted"}]
    mock_conid = [{"conid": 265598}]
    with patch.object(adapter._client, "get", new=AsyncMock(return_value=mock_conid)), \
         patch.object(adapter._client, "post", new=AsyncMock(return_value=mock_response)):
        req = OrderRequest(ticker="AAPL", qty=10, side="buy", order_type="market")
        order = await adapter.place_order(req)
    assert order.order_id == "ord_001"
    assert order.status == "open"
