from __future__ import annotations
import asyncio, json
import click
from trader.adapters.factory import get_adapter
from trader.cli.__main__ import output_json

@click.group()
def quotes():
    """Market data commands for stocks, ETFs, and options."""

@quotes.command("get")
@click.argument("tickers", nargs=-1, required=True)
@click.pass_context
def get_quotes(ctx, tickers):
    """
    Get live quotes for one or more tickers.

    TICKERS: Space-separated list e.g. AAPL MSFT TSLA
    """
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    async def run():
        await adapter.connect()
        try:
            return await adapter.get_quotes(list(tickers))
        finally:
            await adapter.disconnect()
    try:
        output_json(asyncio.run(run()))
    except Exception as e:
        import sys
        click.echo(json.dumps({"error": str(e), "code": type(e).__name__}))
        sys.exit(1)

@quotes.command("chain")
@click.argument("ticker")
@click.option("--expiry", required=True, help="Expiry date YYYY-MM-DD e.g. 2026-04-17")
@click.option("--strike", type=float, default=None, help="Filter by strike price.")
@click.option("--right", type=click.Choice(["call", "put"]), default=None, help="Filter calls or puts.")
@click.pass_context
def option_chain(ctx, ticker, expiry, strike, right):
    """
    Get options chain for TICKER at EXPIRY.

    Use --strike and --right to filter. Returns all contracts if unfiltered.
    """
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    async def run():
        await adapter.connect()
        try:
            chain = await adapter.get_option_chain(ticker, expiry)
        finally:
            await adapter.disconnect()
        if strike:
            chain.contracts = [c for c in chain.contracts if c.strike == strike]
        if right:
            chain.contracts = [c for c in chain.contracts if c.right == right]
        return chain
    try:
        output_json(asyncio.run(run()))
    except Exception as e:
        import sys
        click.echo(json.dumps({"error": str(e), "code": type(e).__name__}))
        sys.exit(1)
