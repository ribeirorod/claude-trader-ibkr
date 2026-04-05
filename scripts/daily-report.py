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


def _fmt_orders(orders) -> str:
    if not orders:
        return "  (none)"
    rows = []
    for o in orders:
        side = o.side.upper()
        otype = _order_type_label(o)
        qty = int(o.qty)
        price = _fmt_price(o.filled_price or o.price)
        line = f"  {o.ticker:<7} {side} {qty}x @ {price}"
        if otype == "BRACKET":
            tp = _fmt_price(o.take_profit) if o.take_profit else "-"
            sl = _fmt_price(o.stop_loss) if o.stop_loss else "-"
            line += f"  TP:{tp} SL:{sl}"
        rows.append(line)
    return "\n".join(rows)


def _fmt_positions(positions) -> str:
    if not positions:
        return "  (none)"
    rows = []
    for p in positions:
        pnl = _fmt_pnl(p.unrealized_pnl)
        rows.append(f"  {p.ticker:<7} {int(p.qty):>4}x  avg {_fmt_price(p.avg_cost):>8}  P&L {pnl}")
    return "\n".join(rows)


# ── report builders ───────────────────────────────────────────────────────────

def _bod_report(positions, orders, account, now: datetime) -> str:
    date_str = now.strftime("%a %d %b %Y  %H:%M CET")
    open_orders = [o for o in orders if o.status in ("open", "pending")]
    b = account.balance
    ccy = b.currency

    return "\n".join([
        f"<b>DAILY BRIEF — {date_str}</b>",
        "",
        f"<b>Account</b>",
        f"<pre>  Net Liq   {_fmt_price(b.net_liquidation, ccy)}",
        f"  Cash      {_fmt_price(b.cash, ccy)}",
        f"  Buying Pw {_fmt_price(b.buying_power, ccy)}</pre>",
        "",
        f"<b>Positions ({len(positions)})</b>",
        f"<pre>{_fmt_positions(positions)}</pre>",
        "",
        f"<b>Open Orders ({len(open_orders)})</b>",
        f"<pre>{_fmt_orders(open_orders)}</pre>",
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
        f"<b>EOD SUMMARY — {date_str}</b>",
        "",
        f"<b>Filled Today ({len(filled)})</b>",
        f"<pre>{_fmt_orders(filled)}</pre>",
    ]

    if open_orders:
        lines += [
            "",
            f"<b>Open / GTC ({len(open_orders)})</b>",
            f"<pre>{_fmt_orders(open_orders)}</pre>",
        ]

    lines += [
        "",
        f"<b>Positions ({len(positions)})</b>",
        f"<pre>{_fmt_positions(positions)}</pre>",
        "",
        f"<b>P&L</b>",
        f"<pre>  Unrealized  {_fmt_pnl(unreal)}",
        f"  Realized    {_fmt_pnl(realized)}",
        f"  Total       {_fmt_pnl(unreal + realized)}</pre>",
        "",
        f"<pre>  Net Liq     {_fmt_price(b.net_liquidation, ccy)}</pre>",
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

    ok = send_telegram(msg, config=cfg, parse_mode="HTML")
    if ok:
        log.info("Report sent (slot=%s).", args.slot)
    else:
        log.error("Failed to send Telegram report.")
        sys.exit(1)


if __name__ == "__main__":
    main()
