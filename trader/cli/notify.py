from __future__ import annotations
import click
from trader.notify import send_telegram


@click.command()
@click.argument("message")
@click.option("--parse-mode", default="HTML", type=click.Choice(["HTML", "Markdown"]),
              help="Telegram parse mode.")
def notify(message: str, parse_mode: str) -> None:
    """Send a Telegram notification.

    Used by the agent to send progress updates during multi-step analysis.

    \b
    Examples:
      trader notify "Running regime check..."
      trader notify "<b>Step 1/4:</b> Scanning watchlist signals"
    """
    ok = send_telegram(message, parse_mode=parse_mode)
    if not ok:
        raise click.ClickException("Failed to send Telegram message")
    click.echo("sent")
