from __future__ import annotations
import asyncio, json, sys
import click
from trader.adapters.factory import get_adapter
from trader.cli.__main__ import output_json


@click.group()
def alerts():
    """Price alerts: set, list, and delete IBKR price alerts."""


def _run(ctx, coro):
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    async def run():
        await adapter.connect()
        try:
            return await coro(adapter)
        finally:
            await adapter.disconnect()
    try:
        output_json(asyncio.run(run()))
    except Exception as e:
        click.echo(json.dumps({"error": str(e), "code": type(e).__name__}))
        sys.exit(1)


@alerts.command("list")
@click.pass_context
def list_alerts(ctx):
    """
    List all active price alerts.

    Example: trader alerts list
    """
    _run(ctx, lambda a: a.list_alerts())


@alerts.command("create")
@click.argument("ticker")
@click.option("--above", "price_above", type=float, default=None,
              help="Trigger when price rises at or above this value.")
@click.option("--below", "price_below", type=float, default=None,
              help="Trigger when price falls at or below this value.")
@click.option("--name", default=None, help="Custom alert name.")
@click.pass_context
def create_alert(ctx, ticker, price_above, price_below, name):
    """
    Create a price alert for TICKER.

    Exactly one of --above or --below is required.

    Examples:
      trader alerts create AAPL --above 200
      trader alerts create AAPL --below 150 --name "AAPL support break"
    """
    if price_above is None and price_below is None:
        raise click.UsageError("Provide --above or --below")
    if price_above is not None and price_below is not None:
        raise click.UsageError("Provide only one of --above or --below")

    operator = ">=" if price_above is not None else "<="
    price = price_above if price_above is not None else price_below

    async def coro(a):
        return await a.create_alert(ticker, operator, price, name)

    _run(ctx, coro)


@alerts.command("delete")
@click.argument("alert_id")
@click.pass_context
def delete_alert(ctx, alert_id):
    """
    Delete an alert by ALERT_ID.

    Example: trader alerts delete 12345
    """
    async def coro(a):
        ok = await a.delete_alert(alert_id)
        return {"deleted": ok, "alert_id": alert_id}

    _run(ctx, coro)
