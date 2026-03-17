#!/usr/bin/env python3
"""
Daily Telegram report: beginning-of-day brief and end-of-day summary.

Usage:
  uv run python scripts/daily-report.py --slot open   # BOD 08:00 CET
  uv run python scripts/daily-report.py --slot close  # EOD 22:00 CET
"""
from __future__ import annotations

import asyncio
import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))

sys.path.insert(0, str(ROOT))

from trader.adapters.factory import get_adapter
from trader.config import Config
from trader.notify import send_telegram

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("daily-report")


# ── formatting helpers ────────────────────────────────────────────────────────

def _col(val, width: int, align: str = "<") -> str:
    return format(str(val), f"{align}{width}")


def _fmt_price(v: float | None, currency: str = "") -> str:
    if v is None:
        return "-"
    prefix = f"{currency} " if currency else ""
    return f"{prefix}{v:,.2f}"


def _fmt_pnl(v: float) -> str:
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:,.2f}"


def _parse_time(raw: str | None) -> str:
    """Extract HH:MM from IBKR lastExecutionTime (yyMMddHHmmss or similar)."""
    if not raw:
        return "--:--"
    digits = raw.replace("-", "").replace(":", "").replace("T", "")
    if len(digits) >= 6:
        return f"{digits[-6:-4]}:{digits[-4:-2]}"
    return raw[:5] if len(raw) >= 5 else raw


def _order_type_label(o) -> str:
    t = o.order_type.upper()
    if t == "BRACKET" or (o.take_profit and o.stop_loss):
        return "BRACKET"
    return t


def _table_orders(orders) -> str:
    if not orders:
        return "  (none)"
    header = f"{'Time':<6}  {'Ticker':<7} {'Side':<5} {'Type':<9} {'Qty':>5}  {'Filled':>6}  {'Price':>9}  {'TP':>8}  {'SL':>8}"
    sep    = "-" * len(header)
    rows = [header, sep]
    for o in orders:
        tp = _fmt_price(o.take_profit) if o.take_profit else "-"
        sl = _fmt_price(o.stop_loss) if o.stop_loss else "-"
        rows.append(
            f"{_col(_parse_time(o.created_at), 6)}  "
            f"{_col(o.ticker, 7)}"
            f"{_col(o.side.upper(), 5)}"
            f"{_col(_order_type_label(o), 9)}"
            f"{int(o.qty):>5}  "
            f"{int(o.filled_qty or 0):>6}  "
            f"{_fmt_price(o.filled_price or o.price):>9}  "
            f"{tp:>8}  "
            f"{sl:>8}"
        )
    return "\n".join(rows)


def _table_positions(positions) -> str:
    if not positions:
        return "  (none)"
    header = f"{'Ticker':<7} {'Qty':>6}  {'Avg Cost':>9}  {'Mkt Val':>10}  {'Unreal P&L':>11}"
    sep    = "-" * len(header)
    rows = [header, sep]
    for p in positions:
        rows.append(
            f"{_col(p.ticker, 7)}"
            f"{int(p.qty):>6}  "
            f"{_fmt_price(p.avg_cost):>9}  "
            f"{_fmt_price(p.market_value):>10}  "
            f"{_fmt_pnl(p.unrealized_pnl):>11}"
        )
    return "\n".join(rows)


# ── report builders ───────────────────────────────────────────────────────────

def _bod_report(positions, orders, account, now: datetime) -> str:
    date_str = now.strftime("%a %d %b %Y  %H:%M CET")
    open_orders = [o for o in orders if o.status in ("open", "pending")]
    b = account.balance
    ccy = b.currency

    return "\n".join([
        f"*DAILY BRIEF — {date_str}*",
        "",
        "*ACCOUNT*",
        "```",
        f"{'Cash':<16} {_fmt_price(b.cash, ccy)}",
        f"{'Net Liquidation':<16} {_fmt_price(b.net_liquidation, ccy)}",
        f"{'Buying Power':<16} {_fmt_price(b.buying_power, ccy)}",
        "```",
        "",
        f"*POSITIONS  ({len(positions)} open)*",
        "```",
        _table_positions(positions),
        "```",
        "",
        f"*OPEN ORDERS  ({len(open_orders)})*",
        "```",
        _table_orders(open_orders),
        "```",
    ])


def _eod_report(positions, orders, account, now: datetime) -> str:
    date_str = now.strftime("%a %d %b %Y  %H:%M CET")
    filled = [o for o in orders if o.status == "filled"]
    open_orders = [o for o in orders if o.status in ("open", "pending")]
    b = account.balance
    ccy = b.currency
    unreal = sum(p.unrealized_pnl for p in positions)
    realized = sum(p.realized_pnl for p in positions)

    lines = [
        f"*EOD SUMMARY — {date_str}*",
        "",
        f"*ORDERS FILLED TODAY  ({len(filled)})*",
        "```",
        _table_orders(filled),
        "```",
    ]

    if open_orders:
        lines += [
            "",
            f"*OPEN / GTC  ({len(open_orders)})*",
            "```",
            _table_orders(open_orders),
            "```",
        ]

    lines += [
        "",
        f"*POSITIONS  ({len(positions)} open)*",
        "```",
        _table_positions(positions),
        "```",
        "",
        "*P&L*",
        "```",
        f"{'Unrealized':<14} {_fmt_pnl(unreal)}",
        f"{'Realized':<14} {_fmt_pnl(realized)}",
        f"{'Total':<14} {_fmt_pnl(unreal + realized)}",
        "```",
        "",
        "*ACCOUNT*",
        "```",
        f"{'Net Liquidation':<16} {_fmt_price(b.net_liquidation, ccy)}",
        f"{'Cash':<16} {_fmt_price(b.cash, ccy)}",
        f"{'Buying Power':<16} {_fmt_price(b.buying_power, ccy)}",
        "```",
    ]

    return "\n".join(lines)


# ── main ──────────────────────────────────────────────────────────────────────

async def _fetch(cfg: Config):
    adapter = get_adapter(cfg.default_broker, cfg)
    await adapter.connect()
    try:
        positions = await adapter.list_positions()
        orders = await adapter.list_orders("all")
        account = await adapter.get_account()
    finally:
        await adapter.disconnect()
    return positions, orders, account


def main() -> None:
    parser = argparse.ArgumentParser(description="Send daily BOD/EOD Telegram report.")
    parser.add_argument("--slot", choices=["open", "close"], required=True,
                        help="open = beginning of day, close = end of day")
    args = parser.parse_args()

    cfg = Config()
    now = datetime.now()

    try:
        positions, orders, account = asyncio.run(_fetch(cfg))
    except Exception as exc:
        log.error("Failed to fetch data: %s", exc)
        send_telegram(
            f"<b>Daily report failed ({args.slot})</b>\n<code>{exc}</code>",
            config=cfg,
        )
        sys.exit(1)

    if args.slot == "open":
        msg = _bod_report(positions, orders, account, now)
    else:
        msg = _eod_report(positions, orders, account, now)

    ok = send_telegram(msg, config=cfg, parse_mode="Markdown")
    if ok:
        log.info("Report sent (slot=%s).", args.slot)
    else:
        log.error("Failed to send Telegram report.")
        sys.exit(1)


if __name__ == "__main__":
    main()
