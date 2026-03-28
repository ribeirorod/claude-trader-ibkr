from __future__ import annotations
import asyncio, json
import click
from trader.adapters.factory import get_adapter
from trader.models import OrderRequest
from trader.cli.__main__ import output_json

@click.group()
def orders():
    """Order management: buy, sell, cancel, modify, stop, trailing-stop, take-profit, bracket."""

def _run_order(ctx, req: OrderRequest):
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    cfg = ctx.obj["config"]

    async def run():
        await adapter.connect()
        try:
            # Guard check when AGENT_MODE=guarded
            if cfg.agent_mode == "guarded" and req.side in ("buy", "short"):
                from trader.guard import OrderGuard
                acct = await adapter.get_account()
                positions = await adapter.list_positions()
                open_ords = await adapter.list_orders("open")
                guard = OrderGuard()
                result = guard.validate(
                    order=req,
                    account=acct,
                    positions=positions,
                    open_orders=open_ords,
                    max_single_position_pct=cfg.max_position_pct,
                    cash_reserve_pct=float(cfg.bear_cash_floor),
                    max_new_positions_per_day=3,
                    today_new_position_count=0,
                )
                if not result.allowed:
                    import sys
                    click.echo(json.dumps({
                        "error": "Order rejected by OrderGuard",
                        "reason": result.reason,
                        "details": result.details,
                    }))
                    sys.exit(1)
            return await adapter.place_order(req)
        finally:
            await adapter.disconnect()
    try:
        output_json(asyncio.run(run()))
    except Exception as e:
        import sys
        click.echo(json.dumps({"error": str(e), "code": type(e).__name__}))
        sys.exit(1)

@orders.command()
@click.argument("ticker")
@click.argument("qty", type=float)
@click.option("--type", "order_type", default="market",
              type=click.Choice(["market", "limit", "stop", "bracket"]),
              help="Order type. bracket requires --take-profit and --stop-loss.")
@click.option("--price", type=float, default=None, help="Limit or stop price.")
@click.option("--take-profit", type=float, default=None, help="Take profit price (bracket orders).")
@click.option("--stop-loss", type=float, default=None, help="Stop loss price (bracket orders).")
@click.option("--contract-type", default="stock",
              type=click.Choice(["stock", "etf", "option"]),
              help="Contract type: stock (default), etf, option.")
@click.option("--expiry", default=None, help="Option expiry YYYY-MM-DD.")
@click.option("--strike", type=float, default=None, help="Option strike price.")
@click.option("--right", type=click.Choice(["call", "put"]), default=None, help="call or put.")
@click.pass_context
def buy(ctx, ticker, qty, order_type, price, take_profit, stop_loss,
        contract_type, expiry, strike, right):
    """
    Buy TICKER QTY shares or contracts.

    Examples:
      trader orders buy AAPL 10
      trader orders buy AAPL 10 --type limit --price 195
      trader orders buy AAPL 10 --type bracket --price 195 --take-profit 210 --stop-loss 185
      trader orders buy AAPL --contract-type option --expiry 2026-04-17 --strike 200 --right call --qty 1
    """
    _run_order(ctx, OrderRequest(
        ticker=ticker, qty=qty, side="buy", order_type=order_type,
        price=price, take_profit=take_profit, stop_loss=stop_loss,
        contract_type=contract_type, expiry=expiry, strike=strike, right=right,
    ))

@orders.command()
@click.argument("ticker")
@click.argument("qty", type=float)
@click.option("--type", "order_type", default="market",
              type=click.Choice(["market", "limit", "bracket"]),
              help="Order type.")
@click.option("--price", type=float, default=None, help="Limit price.")
@click.option("--take-profit", type=float, default=None,
              help="Take profit (cover) price for bracket short.")
@click.option("--stop-loss", type=float, default=None,
              help="Stop loss (cover) price for bracket short.")
@click.pass_context
def short(ctx, ticker, qty, order_type, price, take_profit, stop_loss):
    """
    Short-sell TICKER QTY shares (opens a new short position via IBKR SSHORT).

    \b
    Examples:
      trader orders short PBR 100
      trader orders short PBR 100 --type limit --price 14.50
      trader orders short PBR 100 --type bracket --price 14.50 --take-profit 12.00 --stop-loss 15.50
    """
    _run_order(ctx, OrderRequest(
        ticker=ticker, qty=qty, side="short", order_type=order_type,
        price=price, take_profit=take_profit, stop_loss=stop_loss,
    ))

@orders.command()
@click.argument("ticker")
@click.argument("qty", type=float)
@click.option("--type", "order_type", default="market",
              type=click.Choice(["market", "limit", "stop"]))
@click.option("--price", type=float, default=None)
@click.option("--contract-type", default="stock",
              type=click.Choice(["stock", "etf", "option"]))
@click.option("--expiry", default=None)
@click.option("--strike", type=float, default=None)
@click.option("--right", type=click.Choice(["call", "put"]), default=None)
@click.pass_context
def sell(ctx, ticker, qty, order_type, price, contract_type, expiry, strike, right):
    """Sell TICKER QTY shares or contracts."""
    _run_order(ctx, OrderRequest(
        ticker=ticker, qty=qty, side="sell", order_type=order_type, price=price,
        contract_type=contract_type, expiry=expiry, strike=strike, right=right,
    ))

@orders.command()
@click.argument("ticker")
@click.option("--price", type=float, default=None, help="Limit price (market if omitted).")
@click.option("--qty", type=float, default=None,
              help="Quantity to cover (auto-detected from short position if omitted).")
@click.pass_context
def cover(ctx, ticker, price, qty):
    """
    Buy-to-cover a short position in TICKER.

    \b
    Examples:
      trader orders cover PBR
      trader orders cover PBR --price 12.50
      trader orders cover PBR --qty 50 --price 12.50
    """
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    async def run():
        await adapter.connect()
        try:
            positions = await adapter.list_positions()
            pos = next((p for p in positions if p.ticker == ticker), None)
            if pos is None or pos.qty >= 0:
                raise click.UsageError(
                    f"No short position found for {ticker}. Use --qty to specify size explicitly."
                )
            size = qty or abs(pos.qty)
            order_type = "limit" if price else "market"
            return await adapter.place_order(OrderRequest(
                ticker=ticker, qty=size, side="buy",
                order_type=order_type, price=price,
            ))
        finally:
            await adapter.disconnect()
    try:
        output_json(asyncio.run(run()))
    except Exception as e:
        import sys
        click.echo(json.dumps({"error": str(e), "code": type(e).__name__}))
        sys.exit(1)

@orders.command()
@click.argument("ticker")
@click.argument("qty", type=float)
@click.option("--entry", type=float, required=True, help="Entry limit price.")
@click.option("--take-profit", type=float, required=True, help="Take profit target price.")
@click.option("--stop-loss", type=float, required=True, help="Stop loss trigger price.")
@click.pass_context
def bracket(ctx, ticker, qty, entry, take_profit, stop_loss):
    """
    Place a bracket order: entry limit + automatic take-profit + stop-loss.

    Example: trader orders bracket AAPL 10 --entry 195 --take-profit 210 --stop-loss 185
    """
    _run_order(ctx, OrderRequest(
        ticker=ticker, qty=qty, side="buy", order_type="bracket",
        price=entry, take_profit=take_profit, stop_loss=stop_loss,
    ))

def _resolve_qty(positions, ticker, qty_override):
    """Return qty_override if given, else look up open position size."""
    if qty_override:
        return qty_override
    pos = next((p for p in positions if p.ticker == ticker), None)
    if pos and abs(pos.qty) > 0:
        return abs(pos.qty)
    raise click.UsageError(
        f"No open position found for {ticker}. Use --qty to specify size explicitly."
    )

@orders.command()
@click.argument("ticker")
@click.option("--price", type=float, required=True, help="Stop loss trigger price.")
@click.option("--qty", type=float, default=None, help="Quantity (auto-detected from position if omitted).")
@click.pass_context
def stop(ctx, ticker, price, qty):
    """
    Set a stop-loss order on an existing position.

    Example: trader orders stop AAPL --price 185.00
    """
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    async def run():
        await adapter.connect()
        try:
            positions = await adapter.list_positions()
            size = _resolve_qty(positions, ticker, qty)
            return await adapter.place_order(OrderRequest(
                ticker=ticker, qty=size, side="sell",
                order_type="stop", price=price
            ))
        finally:
            await adapter.disconnect()
    try:
        output_json(asyncio.run(run()))
    except Exception as e:
        import sys
        click.echo(json.dumps({"error": str(e), "code": type(e).__name__}))
        sys.exit(1)

@orders.command("trailing-stop")
@click.argument("ticker")
@click.option("--trail-percent", type=float, default=None,
              help="Trailing amount as percentage e.g. 2.5 for 2.5%%.")
@click.option("--trail-amount", type=float, default=None,
              help="Trailing amount in dollars e.g. 5.00.")
@click.option("--qty", type=float, default=None, help="Quantity (auto-detected from position if omitted).")
@click.pass_context
def trailing_stop(ctx, ticker, trail_percent, trail_amount, qty):
    """
    Set a trailing stop on an existing position.

    Use either --trail-percent or --trail-amount (not both).
    Example: trader orders trailing-stop AAPL --trail-percent 2.5
    """
    if trail_percent is None and trail_amount is None:
        raise click.UsageError("Provide --trail-percent or --trail-amount")
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    async def run():
        await adapter.connect()
        try:
            positions = await adapter.list_positions()
            size = _resolve_qty(positions, ticker, qty)
            return await adapter.place_order(OrderRequest(
                ticker=ticker, qty=size, side="sell", order_type="trailing_stop",
                trail_percent=trail_percent, trail_amount=trail_amount,
            ))
        finally:
            await adapter.disconnect()
    try:
        output_json(asyncio.run(run()))
    except Exception as e:
        import sys
        click.echo(json.dumps({"error": str(e), "code": type(e).__name__}))
        sys.exit(1)

@orders.command("take-profit")
@click.argument("ticker")
@click.option("--price", type=float, required=True, help="Take profit target price.")
@click.option("--qty", type=float, default=None, help="Quantity (auto-detected from position if omitted).")
@click.pass_context
def take_profit(ctx, ticker, price, qty):
    """
    Set a take-profit limit order on an existing position.

    Example: trader orders take-profit AAPL --price 210.00
    """
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    async def run():
        await adapter.connect()
        try:
            positions = await adapter.list_positions()
            size = _resolve_qty(positions, ticker, qty)
            return await adapter.place_order(OrderRequest(
                ticker=ticker, qty=size, side="sell",
                order_type="limit", price=price
            ))
        finally:
            await adapter.disconnect()
    try:
        output_json(asyncio.run(run()))
    except Exception as e:
        import sys
        click.echo(json.dumps({"error": str(e), "code": type(e).__name__}))
        sys.exit(1)

@orders.command()
@click.argument("order_id")
@click.option("--price", type=float, default=None, help="New limit price.")
@click.option("--qty", type=float, default=None, help="New quantity.")
@click.pass_context
def modify(ctx, order_id, price, qty):
    """
    Modify a pending order's price or quantity.

    Example: trader orders modify ord_001 --price 198.00
    """
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    kwargs = {}
    if price is not None:
        kwargs["price"] = price
    if qty is not None:
        kwargs["quantity"] = qty
    async def run():
        await adapter.connect()
        try:
            return await adapter.modify_order(order_id, **kwargs)
        finally:
            await adapter.disconnect()
    try:
        output_json(asyncio.run(run()))
    except Exception as e:
        import sys
        click.echo(json.dumps({"error": str(e), "code": type(e).__name__}))
        sys.exit(1)

@orders.command()
@click.argument("order_id")
@click.pass_context
def cancel(ctx, order_id):
    """
    Cancel a pending order by ORDER_ID.

    Example: trader orders cancel ord_001
    """
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    async def run():
        await adapter.connect()
        try:
            ok = await adapter.cancel_order(order_id)
        finally:
            await adapter.disconnect()
        return {"cancelled": ok, "order_id": order_id}
    try:
        output_json(asyncio.run(run()))
    except Exception as e:
        import sys
        click.echo(json.dumps({"error": str(e), "code": type(e).__name__}))
        sys.exit(1)

@orders.command("list")
@click.option("--status", default="all",
              type=click.Choice(["open", "filled", "cancelled", "all"]),
              help="Filter by status: open, filled, cancelled, all (default).")
@click.pass_context
def list_orders(ctx, status):
    """
    List orders filtered by status.

    Example: trader orders list --status open
    """
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    async def run():
        await adapter.connect()
        try:
            return await adapter.list_orders(status)
        finally:
            await adapter.disconnect()
    try:
        output_json(asyncio.run(run()))
    except Exception as e:
        import sys
        click.echo(json.dumps({"error": str(e), "code": type(e).__name__}))
        sys.exit(1)
