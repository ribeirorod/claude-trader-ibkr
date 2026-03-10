import json
from unittest.mock import AsyncMock, patch
from click.testing import CliRunner
from trader.cli.__main__ import cli
from trader.models import Account, Balance, Margin

def mock_account():
    return Account(
        account_id="DU123",
        balance=Balance(cash=10000, net_liquidation=12000, buying_power=20000),
        margin=Margin(initial_margin=500, maintenance_margin=400, available_margin=9500),
    )

def test_account_summary():
    runner = CliRunner()
    with patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.connect", new=AsyncMock()), \
         patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.get_account",
               new=AsyncMock(return_value=mock_account())), \
         patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.disconnect", new=AsyncMock()):
        result = runner.invoke(cli, ["account", "summary"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["account_id"] == "DU123"
    assert "balance" in data
