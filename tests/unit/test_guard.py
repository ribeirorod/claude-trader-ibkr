from trader.guard import OrderGuard, GuardResult
from trader.models import OrderRequest, Account, Balance, Margin, Position, Order

def make_account(nlv=100_000.0, cash=50_000.0):
    return Account(
        account_id="U123",
        balance=Balance(cash=cash, net_liquidation=nlv, buying_power=cash),
        margin=Margin(initial_margin=0.0, maintenance_margin=0.0, available_margin=cash),
    )

def make_order(ticker="AAPL", qty=10, side="buy", order_type="market", price=None):
    return OrderRequest(ticker=ticker, qty=qty, side=side, order_type=order_type, price=price)

def make_position(ticker="AAPL", qty=10, avg_cost=100.0):
    return Position(
        ticker=ticker, qty=qty, avg_cost=avg_cost,
        market_value=qty * avg_cost, unrealized_pnl=0.0,
    )

def make_open_order(ticker="AAPL", side="buy"):
    return Order(
        order_id="ord_1", ticker=ticker, qty=10, side=side,
        order_type="limit", status="open", price=100.0,
    )


def test_order_allowed_when_within_limits():
    guard = OrderGuard()
    result = guard.validate(
        order=make_order(qty=10, price=100.0, order_type="limit"),
        account=make_account(nlv=100_000, cash=50_000),
        positions=[],
        open_orders=[],
        max_single_position_pct=0.10,
        cash_reserve_pct=0.10,
        max_new_positions_per_day=3,
        today_new_position_count=0,
    )
    assert result.allowed is True
    assert result.reason is None


def test_cash_floor_breach():
    guard = OrderGuard()
    result = guard.validate(
        order=make_order(qty=100, price=100.0, order_type="limit"),
        account=make_account(nlv=100_000, cash=50_000),
        positions=[make_position(qty=600, avg_cost=100.0)],
        open_orders=[],
        max_single_position_pct=0.10,
        cash_reserve_pct=0.40,
        max_new_positions_per_day=3,
        today_new_position_count=0,
    )
    assert result.allowed is False
    assert result.reason == "cash_floor_breach"


def test_position_limit_breach():
    guard = OrderGuard()
    result = guard.validate(
        order=make_order(ticker="AAPL", qty=50, price=100.0, order_type="limit"),
        account=make_account(nlv=100_000),
        positions=[make_position(ticker="AAPL", qty=80, avg_cost=100.0)],
        open_orders=[],
        max_single_position_pct=0.10,
        cash_reserve_pct=0.10,
        max_new_positions_per_day=3,
        today_new_position_count=0,
    )
    assert result.allowed is False
    assert result.reason == "position_limit"


def test_daily_limit_breach():
    guard = OrderGuard()
    result = guard.validate(
        order=make_order(qty=10, price=100.0, order_type="limit"),
        account=make_account(),
        positions=[],
        open_orders=[],
        max_single_position_pct=0.10,
        cash_reserve_pct=0.10,
        max_new_positions_per_day=3,
        today_new_position_count=3,
    )
    assert result.allowed is False
    assert result.reason == "daily_limit"


def test_no_margin_breach():
    guard = OrderGuard()
    result = guard.validate(
        order=make_order(qty=100, price=100.0, order_type="limit"),
        account=make_account(nlv=100_000, cash=5_000),
        positions=[make_position(qty=950, avg_cost=100.0)],
        open_orders=[],
        max_single_position_pct=1.0,
        cash_reserve_pct=0.0,
        max_new_positions_per_day=10,
        today_new_position_count=0,
    )
    assert result.allowed is False
    assert result.reason == "margin_not_allowed"


def test_duplicate_order_rejected():
    guard = OrderGuard()
    result = guard.validate(
        order=make_order(ticker="AAPL", qty=10, side="buy"),
        account=make_account(),
        positions=[],
        open_orders=[make_open_order(ticker="AAPL", side="buy")],
        max_single_position_pct=0.10,
        cash_reserve_pct=0.10,
        max_new_positions_per_day=3,
        today_new_position_count=0,
    )
    assert result.allowed is False
    assert result.reason == "duplicate_order"


def test_sell_order_bypasses_most_guards():
    guard = OrderGuard()
    result = guard.validate(
        order=make_order(ticker="AAPL", qty=10, side="sell"),
        account=make_account(nlv=100_000, cash=0),
        positions=[make_position(ticker="AAPL", qty=10)],
        open_orders=[],
        max_single_position_pct=0.10,
        cash_reserve_pct=0.90,
        max_new_positions_per_day=0,
        today_new_position_count=5,
    )
    assert result.allowed is True
