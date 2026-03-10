from __future__ import annotations
import asyncio
import click
from trader.adapters.factory import get_adapter
from trader.cli.__main__ import output_json

@click.group()
def account():
    """Account information. Returns balance, margin, and account summary."""

@account.command()
@click.pass_context
def summary(ctx):
    """Full account summary including balance and margin."""
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    async def run():
        await adapter.connect()
        try:
            return await adapter.get_account()
        finally:
            await adapter.disconnect()
    output_json(asyncio.get_event_loop().run_until_complete(run()))

@account.command()
@click.pass_context
def balance(ctx):
    """Cash balance, net liquidation, and buying power."""
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    async def run():
        await adapter.connect()
        try:
            acct = await adapter.get_account()
            return acct.balance
        finally:
            await adapter.disconnect()
    output_json(asyncio.get_event_loop().run_until_complete(run()))

@account.command()
@click.pass_context
def margin(ctx):
    """Initial margin, maintenance margin, and available margin."""
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    async def run():
        await adapter.connect()
        try:
            acct = await adapter.get_account()
            return acct.margin
        finally:
            await adapter.disconnect()
    output_json(asyncio.get_event_loop().run_until_complete(run()))
