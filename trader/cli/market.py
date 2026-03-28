from __future__ import annotations
import json
from pathlib import Path

import click

from trader.market.regime import detect_regime, MarketRegime, _default_fetch, _ma_state
from trader.market.rotation import build_rotation_actions
from trader.cli.__main__ import output_json


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
