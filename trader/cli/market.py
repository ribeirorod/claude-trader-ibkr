from __future__ import annotations
import asyncio
import json
from datetime import datetime
from pathlib import Path

import click

from trader.adapters.factory import get_adapter
from trader.market.regime import detect_regime, MarketRegime, _default_fetch, _ma_state
from trader.market.rotation import build_rotation_actions
from trader.risk.time_stop import check_time_stops, log_time_stop_review
from trader.cli.__main__ import output_json


def _get_agent_log_path() -> Path:
    return Path(".trader/logs/agent.jsonl")


def _get_today() -> datetime:
    return datetime.now()


@click.group()
def market():
    """Market regime detection and defensive rotation commands."""


@market.command()
@click.option(
    "--tickers",
    default="SPY,QQQ",
    show_default=True,
    help="Comma-separated regime reference tickers.",
)
def regime(tickers: str):
    """Detect current market regime using 20/50-day MA state on reference tickers.

    \b
    Output:
      regime: bull | caution | bear
      states: per-ticker MA state (+1 bull / -1 bear / 0 neutral)
    """
    ticker_list = [t.strip().upper() for t in tickers.split(",")]

    states: dict[str, int] = {}
    for ticker in ticker_list:
        ohlcv = _default_fetch(ticker, "200d", False)
        states[ticker] = _ma_state(ohlcv)

    if all(s == 1 for s in states.values()):
        reg = MarketRegime.BULL
    elif all(s == -1 for s in states.values()):
        reg = MarketRegime.BEAR
    else:
        reg = MarketRegime.CAUTION

    output_json({"regime": reg.value, "states": states})


@market.command()
@click.option(
    "--tickers",
    default="SPY,QQQ",
    show_default=True,
    help="Comma-separated regime reference tickers.",
)
@click.option(
    "--profile",
    default=".trader/profile.json",
    show_default=True,
    type=click.Path(),
    help="Path to portfolio profile JSON.",
)
def rotate(tickers: str, profile: str):
    """Show defensive rotation actions for the current market regime.

    \b
    In BEAR: suggests inverse ETF buys + defensive sector rotations.
    In CAUTION: suggests partial defensive rotation only.
    In BULL: returns empty list (no action needed).
    """
    ticker_list = [t.strip().upper() for t in tickers.split(",")]
    current_regime = detect_regime(tickers=ticker_list)

    profile_data = json.loads(Path(profile).read_text()) if Path(profile).exists() else {}
    actions = build_rotation_actions(current_regime, profile_data)

    output_json({
        "regime": current_regime.value,
        "actions": actions,
    })


@market.command("time-stops")
@click.option(
    "--regime",
    type=click.Choice(["bull", "caution", "bear"]),
    default=None,
    help="Override detected regime (default: auto-detect via SPY/QQQ).",
)
@click.option("--bull-days", default=20, show_default=True, help="Max trading days in bull regime.")
@click.option("--bear-days", default=10, show_default=True, help="Max trading days in bear regime.")
@click.option("--caution-days", default=15, show_default=True, help="Max trading days in caution regime.")
@click.pass_context
def time_stops(ctx, regime, bull_days, bear_days, caution_days):
    """Check positions against regime-dependent time-stop thresholds."""
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])

    async def run():
        await adapter.connect()
        try:
            return await adapter.list_positions()
        finally:
            await adapter.disconnect()

    try:
        positions = asyncio.run(run())
    except Exception as e:
        import sys
        click.echo(json.dumps({"error": str(e), "code": type(e).__name__}))
        sys.exit(1)

    if regime is None:
        detected = detect_regime()
        regime = detected.value

    agent_log_path = _get_agent_log_path()
    today = _get_today()

    results = check_time_stops(
        positions=positions,
        regime=regime,
        agent_log_path=agent_log_path,
        bull_max_days=bull_days,
        bear_max_days=bear_days,
        caution_max_days=caution_days,
        today=today,
    )

    flagged = [r for r in results if r.action == "review"]
    for r in flagged:
        log_time_stop_review(r, agent_log_path)

    from dataclasses import asdict
    output_json({
        "regime": regime,
        "total_positions": len(positions),
        "checked": len(results),
        "flagged": len(flagged),
        "results": [asdict(r) for r in results],
    })
