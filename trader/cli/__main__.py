from __future__ import annotations
import asyncio, json, sys
from datetime import datetime
from pathlib import Path
import click
from trader.config import Config
from trader.adapters.factory import get_adapter

config = Config()

def _serialize(data) -> str:
    if hasattr(data, "model_dump"):
        return json.dumps(data.model_dump(), indent=2)
    elif isinstance(data, list):
        return json.dumps(
            [d.model_dump() if hasattr(d, "model_dump") else d for d in data],
            indent=2
        )
    return json.dumps(data, indent=2)

def output_json(data) -> None:
    """Serialize to stdout and, if --save was passed, write to outputs/."""
    text = _serialize(data)
    click.echo(text)

    # Check if --save was requested via root context
    ctx = click.get_current_context(silent=True)
    if ctx is None:
        return
    root = ctx.find_root()
    obj = root.obj or {}
    if not obj.get("save"):
        return

    output_dir = Path(obj.get("output_dir", "outputs"))

    # Build path: outputs/{command_group}/{YYYY-MM-DD}/{HH-MM-SS}_{leaf_cmd}{args}.json
    # Walk context chain to get e.g. ["scan", "run"]
    parts = []
    c = ctx
    while c.parent is not None:
        if c.info_name:
            parts.append(c.info_name)
        c = c.parent
    parts.reverse()

    group = parts[0] if parts else "misc"
    leaf = "_".join(parts[1:]) if len(parts) > 1 else "run"

    now = datetime.now()
    date_dir = output_dir / group / now.strftime("%Y-%m-%d")
    date_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{now.strftime('%H-%M-%S')}_{leaf}.json"
    out_path = date_dir / filename
    out_path.write_text(text)

    # Print save notice to stderr so stdout stays clean for piping
    click.echo(f"  → saved: {out_path}", err=True)


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
@click.option(
    "--save", is_flag=True, default=False,
    help="Save output to outputs/{command}/{date}/{time}_{subcommand}.json",
)
@click.option(
    "--output-dir",
    default="outputs",
    show_default=True,
    type=click.Path(),
    help="Root directory for saved outputs (used with --save).",
)
@click.pass_context
def cli(ctx, broker, output, save, output_dir):
    """
    Trader CLI — agent-first trading tool for stocks, ETFs, and options.

    All commands output JSON by default. Run any subcommand with --help
    to see available options and parameters.

    \b
    Broker selection:
      --broker ibkr-rest   IBKR Client Portal Gateway (headless, default)
      --broker ibkr-tws    ib_insync + local TWS/Gateway (optional install)

    \b
    Saving output for later review:
      trader --save scan run TOP_PERC_GAIN
      trader --save strategies signals --tickers NVDA,MSFT --strategy rsi
      trader --save --output-dir /tmp/runs quotes get AAPL MSFT

    Saved files land in: outputs/{command}/{YYYY-MM-DD}/{HH-MM-SS}_{subcommand}.json

    Configure via .env file. See .env.example for all variables.
    """
    ctx.ensure_object(dict)
    ctx.obj["broker"] = broker
    ctx.obj["output"] = output
    ctx.obj["config"] = config
    ctx.obj["save"] = save
    ctx.obj["output_dir"] = output_dir


from trader.cli import account, quotes, orders, positions, news, strategies, alerts, scan, watchlist, report

cli.add_command(account.account)
cli.add_command(quotes.quotes)
cli.add_command(orders.orders)
cli.add_command(positions.positions)
cli.add_command(news.news)
cli.add_command(strategies.strategies)
cli.add_command(alerts.alerts)
cli.add_command(scan.scan)
cli.add_command(watchlist.watchlist)
cli.add_command(report.report)

from trader.cli.market import market
cli.add_command(market)

from trader.cli.pipeline import pipeline
cli.add_command(pipeline)

from trader.cli.notify import notify
cli.add_command(notify)

if __name__ == "__main__":
    cli()
