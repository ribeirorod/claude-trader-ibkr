import json
from unittest.mock import AsyncMock, patch
from click.testing import CliRunner
from trader.cli.__main__ import cli
from trader.models import Order

def mock_order(**kwargs):
    return Order(order_id="ord_1", ticker="AAPL", qty=10, side="buy",
                 order_type="market", status="open", **kwargs)

def test_buy_market_order():
    runner = CliRunner()
    with patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.connect", new=AsyncMock()), \
         patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.place_order",
               new=AsyncMock(return_value=mock_order())), \
         patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.disconnect", new=AsyncMock()):
        result = runner.invoke(cli, ["orders", "buy", "AAPL", "10"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["order_id"] == "ord_1"

def test_orders_list():
    runner = CliRunner()
    with patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.connect", new=AsyncMock()), \
         patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.list_orders",
               new=AsyncMock(return_value=[mock_order()])), \
         patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.disconnect", new=AsyncMock()):
        result = runner.invoke(cli, ["orders", "list"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert isinstance(data, list)
