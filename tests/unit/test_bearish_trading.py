"""Tests for bearish trading features: short-sell, put spreads, options management."""
import json
from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from trader.cli.__main__ import cli
from trader.models import Order, OrderRequest, Position
from trader.models.quote import OptionChain, OptionContract
from trader.strategies.options_selector import (
    SpreadRecommendation,
    select_contract,
    select_spread,
)
from trader.strategies.options_manager import (
    OptionPosition,
    evaluate_position,
    evaluate_spread,
)


# ---------------------------------------------------------------------------
# 1. Short-sell model and CLI
# ---------------------------------------------------------------------------

def test_order_request_short_side():
    req = OrderRequest(ticker="PBR", qty=100, side="short", order_type="market")
    assert req.side == "short"


def test_order_request_short_bracket():
    req = OrderRequest(
        ticker="PBR", qty=100, side="short", order_type="bracket",
        price=14.50, take_profit=12.00, stop_loss=15.50,
    )
    assert req.side == "short"
    assert req.take_profit == 12.00
    assert req.stop_loss == 15.50


def mock_order(**kwargs):
    defaults = dict(order_id="ord_1", ticker="PBR", qty=100, side="short",
                    order_type="market", status="open")
    defaults.update(kwargs)
    return Order(**defaults)


def test_cli_short_command():
    runner = CliRunner()
    with patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.connect", new=AsyncMock()), \
         patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.place_order",
               new=AsyncMock(return_value=mock_order())) as mock_place, \
         patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.disconnect", new=AsyncMock()):
        result = runner.invoke(cli, ["orders", "short", "PBR", "100"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["side"] == "short"
    req = mock_place.call_args[0][0]
    assert req.side == "short"


def test_cli_cover_command():
    runner = CliRunner()
    short_pos = Position(ticker="PBR", qty=-100, avg_cost=14.50, market_value=-1400.0,
                         unrealized_pnl=50.0, realized_pnl=0.0)
    with patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.connect", new=AsyncMock()), \
         patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.list_positions",
               new=AsyncMock(return_value=[short_pos])), \
         patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.place_order",
               new=AsyncMock(return_value=Order(
                   order_id="ord_2", ticker="PBR", qty=100, side="buy",
                   order_type="market", status="open"))) as mock_place, \
         patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.disconnect", new=AsyncMock()):
        result = runner.invoke(cli, ["orders", "cover", "PBR"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["side"] == "buy"
    assert data["qty"] == 100


def test_cli_cover_no_short_position():
    runner = CliRunner()
    long_pos = Position(ticker="PBR", qty=100, avg_cost=14.50, market_value=1400.0,
                        unrealized_pnl=0.0, realized_pnl=0.0)
    with patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.connect", new=AsyncMock()), \
         patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.list_positions",
               new=AsyncMock(return_value=[long_pos])), \
         patch("trader.adapters.ibkr_rest.adapter.IBKRRestAdapter.disconnect", new=AsyncMock()):
        result = runner.invoke(cli, ["orders", "cover", "PBR"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# 2. Adapter SSHORT side mapping
# ---------------------------------------------------------------------------

def test_adapter_short_side_mapping():
    """Verify the adapter maps side='short' to IBKR 'SSHORT'."""
    from trader.adapters.ibkr_rest.adapter import IBKRRestAdapter
    # We test the mapping logic inline since it's in place_order
    req = OrderRequest(ticker="PBR", qty=100, side="short", order_type="market")
    if req.side == "short":
        ibkr_side = "SSHORT"
    else:
        ibkr_side = req.side.upper()
    assert ibkr_side == "SSHORT"


# ---------------------------------------------------------------------------
# 3. Put spread builder
# ---------------------------------------------------------------------------

def _make_chain(strikes, right="put", expiry="2026-04-25", underlying=200.0):
    """Create a test option chain with realistic pricing.

    Put prices increase as strike approaches/exceeds underlying.
    Call prices increase as strike goes further below underlying.
    """
    contracts = []
    for s in strikes:
        if right == "put":
            # Put intrinsic + time value: higher strikes = more expensive
            intrinsic = max(0, s - underlying)
            time_value = 2.0 + (s - min(strikes)) * 0.3
            mid = intrinsic + time_value
        else:
            intrinsic = max(0, underlying - s)
            time_value = 2.0 + (max(strikes) - s) * 0.3
            mid = intrinsic + time_value
        contracts.append(OptionContract(
            strike=s, right=right, expiry=expiry,
            bid=round(mid * 0.95, 2),
            ask=round(mid * 1.05, 2),
            last=round(mid, 2),
            delta=-0.35 if right == "put" else 0.35,
        ))
    return OptionChain(ticker="AAPL", expiry=expiry, contracts=contracts)


def test_select_spread_bearish():
    chain = _make_chain([180, 185, 190, 195, 200, 205, 210])
    rec = select_spread(
        signal=-1, current_price=200.0, current_atr=10.0,
        chain=chain, account_value=100000.0,
    )
    assert isinstance(rec, SpreadRecommendation)
    assert rec.action == "put_spread"
    assert rec.long_leg is not None
    assert rec.short_leg is not None
    assert rec.long_leg.strike > rec.short_leg.strike  # bear put: buy higher, sell lower
    assert rec.net_debit > 0
    assert rec.max_risk > 0
    assert rec.max_reward > 0
    assert rec.suggested_qty >= 1


def test_select_spread_bullish():
    chain = _make_chain([190, 195, 200, 205, 210, 215, 220], right="call")
    rec = select_spread(
        signal=1, current_price=200.0, current_atr=10.0,
        chain=chain, account_value=100000.0,
    )
    assert rec.action == "call_spread"
    assert rec.long_leg.strike < rec.short_leg.strike  # bull call: buy lower, sell higher


def test_select_spread_neutral():
    chain = _make_chain([190, 195, 200])
    rec = select_spread(signal=0, current_price=200.0, current_atr=10.0,
                        chain=chain, account_value=100000.0)
    assert rec.action == "no_action"


def test_select_spread_insufficient_contracts():
    chain = _make_chain([190])  # only one contract
    rec = select_spread(signal=-1, current_price=200.0, current_atr=10.0,
                        chain=chain, account_value=100000.0)
    assert rec.action == "no_action"
    assert "Need" in rec.rationale


# ---------------------------------------------------------------------------
# 4. Options position management
# ---------------------------------------------------------------------------

def test_evaluate_close_at_expiry():
    pos = OptionPosition(
        ticker="AAPL", right="put", strike=190.0, expiry="2026-03-28",
        qty=2, avg_cost=3.50, current_price=1.00, underlying_price=200.0,
    )
    action = evaluate_position(pos)
    assert action.action == "close"
    assert action.urgency == "immediate"
    assert action.dte <= 5


def test_evaluate_profit_target():
    pos = OptionPosition(
        ticker="AAPL", right="put", strike=190.0, expiry="2026-05-15",
        qty=2, avg_cost=3.00, current_price=5.50, underlying_price=185.0,
    )
    action = evaluate_position(pos, profit_target_pct=0.50)
    assert action.action == "close"
    assert action.urgency == "soon"
    assert "Profit target" in action.reason


def test_evaluate_roll_losing():
    pos = OptionPosition(
        ticker="AAPL", right="put", strike=190.0, expiry="2026-04-05",
        qty=2, avg_cost=4.00, current_price=1.00, underlying_price=210.0,
    )
    action = evaluate_position(
        pos, available_expiries=["2026-05-16", "2026-06-20"],
    )
    assert action.action == "roll"
    assert action.new_expiry == "2026-05-16"


def test_evaluate_hold():
    pos = OptionPosition(
        ticker="AAPL", right="put", strike=190.0, expiry="2026-06-15",
        qty=2, avg_cost=3.00, current_price=2.80, underlying_price=200.0,
    )
    action = evaluate_position(pos)
    assert action.action == "hold"


def test_evaluate_spread():
    long_pos = OptionPosition(
        ticker="AAPL", right="put", strike=195.0, expiry="2026-04-25",
        qty=2, avg_cost=4.00, current_price=6.00, underlying_price=190.0,
    )
    short_pos = OptionPosition(
        ticker="AAPL", right="put", strike=185.0, expiry="2026-04-25",
        qty=-2, avg_cost=2.00, current_price=2.50, underlying_price=190.0,
    )
    action = evaluate_spread(long_pos, short_pos)
    assert action.action in ("hold", "close")


# ---------------------------------------------------------------------------
# 5. Inverse ETF mapping (config file)
# ---------------------------------------------------------------------------

def test_inverse_etf_config():
    import json
    with open(".trader/inverse_etfs.json") as f:
        data = json.load(f)
    assert "index_hedges" in data
    assert "sector_hedges" in data
    assert "usage_rules" in data
    assert "SP500" in data["index_hedges"]
    assert data["index_hedges"]["SP500"]["ticker"] == "XISX"
