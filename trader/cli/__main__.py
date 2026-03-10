from __future__ import annotations
import asyncio, json
import click
from trader.config import Config
from trader.adapters.factory import get_adapter

config = Config()

def output_json(data) -> None:
    """Serialize Pydantic models or dicts/lists to stdout as JSON."""
    if hasattr(data, "model_dump"):
        click.echo(json.dumps(data.model_dump(), indent=2))
    elif isinstance(data, list):
        click.echo(json.dumps(
            [d.model_dump() if hasattr(d, "model_dump") else d for d in data],
            indent=2
        ))
    else:
        click.echo(json.dumps(data, indent=2))

@click.group()
@click.option(
    "--broker",
    default=config.default_broker,
    type=click.Choice(["ibkr-rest", "ibkr-tws"]),
    help="Broker adapter. ibkr-rest (default): IBKR Client Portal Gateway (headless). ibkr-tws: ib_insync + local TWS/Gateway.",
)
@click.option(
    "--output",
    default="json",
    type=click.Choice(["json", "table"]),
    help="Output format. Use json (default) for agent consumption.",
)
@click.pass_context
def cli(ctx, broker, output):
    """
    Trader CLI — agent-first trading tool for stocks, ETFs, and options.

    All commands output JSON by default. Run any subcommand with --help
    to see available options and parameters.

    Broker selection:
      --broker ibkr-rest   IBKR Client Portal Gateway (headless, default)
      --broker ibkr-tws    ib_insync + local TWS/Gateway (optional install)

    Configure via .env file. See .env.example for all variables.
    """
    ctx.ensure_object(dict)
    ctx.obj["broker"] = broker
    ctx.obj["output"] = output
    ctx.obj["config"] = config

from trader.cli import account, quotes, orders, positions, news, strategies

cli.add_command(account.account)
cli.add_command(quotes.quotes)
cli.add_command(orders.orders)
cli.add_command(positions.positions)
cli.add_command(news.news)
cli.add_command(strategies.strategies)

if __name__ == "__main__":
    cli()
