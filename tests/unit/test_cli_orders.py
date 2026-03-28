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

def test_buy_rejected_by_guard_when_guarded_mode():
    """When AGENT_MODE=guarded, OrderGuard blocks orders that breach limits."""
    from trader.models import Account, Balance, Margin, Position
    from trader.config import Config
    runner = CliRunner()
    acct = Account(
        account_id="U123",
        balance=Balance(cash=0, net_liquidation=1000, buying_power=0),
        margin=Margin(initial_margin=0, maintenance_margin=0, available_margin=0),
    )
    pos = Position(ticker="AAPL", qty=10, avg_cost=100.0, market_value=1000.0, unrealized_pnl=0.0)

    # Create a guarded config and patch it at the module level so cli() picks it up
    guarded_config = Config()
    guarded_config.agent_mode = "guarded"

    with patch("trader.cli.orders.get_adapter") as mock_get, \
         patch("trader.cli.__main__.config", guarded_config):
        mock_adapter = AsyncMock()
        mock_adapter.connect = AsyncMock()
        mock_adapter.disconnect = AsyncMock()
        mock_adapter.get_account = AsyncMock(return_value=acct)
        mock_adapter.list_positions = AsyncMock(return_value=[pos])
        mock_adapter.list_orders = AsyncMock(return_value=[])
        mock_get.return_value = mock_adapter

        result = runner.invoke(cli, ["orders", "buy", "MSFT", "10", "--type", "limit", "--price", "100"])
    assert result.exit_code == 1, f"Expected exit 1, got {result.exit_code}: {result.output}"
    data = json.loads(result.output)
    assert data["error"] == "Order rejected by OrderGuard"
    assert "reason" in data
