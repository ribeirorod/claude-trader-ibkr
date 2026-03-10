from __future__ import annotations
import asyncio
import click
from trader.adapters.factory import get_adapter
from trader.cli.__main__ import output_json

@click.group()
def positions():
    """Position management: list open positions, close, and P&L."""

@positions.command("list")
@click.pass_context
def list_positions(ctx):
    """List all open positions with market value and unrealized P&L."""
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    async def run():
        await adapter.connect()
        try:
            return await adapter.list_positions()
        finally:
            await adapter.disconnect()
    output_json(asyncio.get_event_loop().run_until_complete(run()))

@positions.command()
@click.argument("ticker")
@click.pass_context
def close(ctx, ticker):
    """Close the entire position for TICKER with a market order."""
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    async def run():
        await adapter.connect()
        try:
            return await adapter.close_position(ticker)
        finally:
            await adapter.disconnect()
    output_json(asyncio.get_event_loop().run_until_complete(run()))

@positions.command()
@click.pass_context
def pnl(ctx):
    """Unrealized and realized P&L across all positions."""
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    async def run():
        await adapter.connect()
        try:
            poss = await adapter.list_positions()
        finally:
            await adapter.disconnect()
        return {
            "unrealized": sum(p.unrealized_pnl for p in poss),
            "realized": sum(p.realized_pnl for p in poss),
            "total": sum(p.unrealized_pnl + p.realized_pnl for p in poss),
            "positions": len(poss),
        }
    output_json(asyncio.get_event_loop().run_until_complete(run()))
