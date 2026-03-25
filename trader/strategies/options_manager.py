"""Options position manager — decides whether to hold, close, roll, or defend option positions.

Pure function: takes current position data and market context; returns an action
recommendation. No broker calls — the caller executes via the CLI.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class OptionPosition:
    """Snapshot of an open option position."""

    ticker: str
    right: str  # "put" or "call"
    strike: float
    expiry: str  # YYYY-MM-DD
    qty: int
    avg_cost: float  # premium paid per contract
    current_price: float  # current option mid-price
    underlying_price: float


@dataclass
class OptionsAction:
    """Recommended action for an option position."""

    action: str  # "hold", "close", "roll", "defend"
    urgency: str  # "immediate", "soon", "monitor"
    reason: str
    # Roll details (populated when action == "roll")
    new_expiry: str | None = None
    new_strike: float | None = None
    # P&L context
    unrealized_pnl_pct: float = 0.0
    dte: int = 0


def evaluate_position(
    pos: OptionPosition,
    available_expiries: list[str] | None = None,
    profit_target_pct: float = 0.50,
    close_dte: int = 5,
    roll_dte: int = 14,
    monitor_dte: int = 21,
) -> OptionsAction:
    """Evaluate an option position and recommend an action.

    Parameters
    ----------
    pos : OptionPosition
        Current position snapshot.
    available_expiries : list[str] | None
        Future expiry dates available for rolling (YYYY-MM-DD).
    profit_target_pct : float
        Close when unrealized gain reaches this fraction of cost basis (default 50%).
    close_dte / roll_dte / monitor_dte : int
        DTE thresholds for close, roll consideration, and monitoring.
    """
    dte = _dte(pos.expiry)
    cost_basis = pos.avg_cost * 100 * abs(pos.qty)
    current_value = pos.current_price * 100 * abs(pos.qty)

    if cost_basis > 0:
        pnl_pct = (current_value - cost_basis) / cost_basis
    else:
        pnl_pct = 0.0

    # Check if ITM
    if pos.right == "put":
        itm = pos.underlying_price < pos.strike
    else:
        itm = pos.underlying_price > pos.strike

    # Priority 1: Expiry approaching — close immediately
    if dte <= close_dte:
        if itm and dte > 0:
            return OptionsAction(
                action="hold", urgency="monitor", dte=dte,
                unrealized_pnl_pct=pnl_pct,
                reason=f"ITM with {dte} DTE — hold for expiry value, but monitor closely.",
            )
        return OptionsAction(
            action="close", urgency="immediate", dte=dte,
            unrealized_pnl_pct=pnl_pct,
            reason=f"Only {dte} DTE remaining. Close to avoid expiry risk.",
        )

    # Priority 2: Profit target hit — take profits
    if pnl_pct >= profit_target_pct:
        return OptionsAction(
            action="close", urgency="soon", dte=dte,
            unrealized_pnl_pct=pnl_pct,
            reason=(
                f"Profit target reached ({pnl_pct:.0%} gain vs {profit_target_pct:.0%} target). "
                f"Close to lock in gains — theta decay accelerates from here."
            ),
        )

    # Priority 3: Roll window — losing position with time to act
    if dte <= roll_dte and pnl_pct < 0:
        new_expiry = _next_monthly_expiry(pos.expiry, available_expiries)
        return OptionsAction(
            action="roll", urgency="soon", dte=dte,
            unrealized_pnl_pct=pnl_pct,
            new_expiry=new_expiry,
            new_strike=pos.strike,  # same strike by default
            reason=(
                f"Losing position ({pnl_pct:.0%}) with only {dte} DTE. "
                f"Roll to {new_expiry or 'next monthly'} to buy time."
            ),
        )

    # Priority 4: Monitor zone — watch theta decay
    if dte <= monitor_dte:
        return OptionsAction(
            action="hold", urgency="monitor", dte=dte,
            unrealized_pnl_pct=pnl_pct,
            reason=(
                f"{dte} DTE, P&L {pnl_pct:.0%}. Theta accelerating — "
                f"close if no catalyst expected before {pos.expiry}."
            ),
        )

    # Default: hold
    return OptionsAction(
        action="hold", urgency="monitor", dte=dte,
        unrealized_pnl_pct=pnl_pct,
        reason=f"{dte} DTE, P&L {pnl_pct:.0%}. No action needed yet.",
    )


def evaluate_spread(
    long_pos: OptionPosition,
    short_pos: OptionPosition,
    available_expiries: list[str] | None = None,
    profit_target_pct: float = 0.50,
    close_dte: int = 5,
) -> OptionsAction:
    """Evaluate a vertical spread and recommend an action.

    For spreads, max loss is capped at the net debit. Defense is simpler.
    """
    dte = _dte(long_pos.expiry)
    net_debit = (long_pos.avg_cost - short_pos.avg_cost) * 100 * abs(long_pos.qty)
    current_value = (long_pos.current_price - short_pos.current_price) * 100 * abs(long_pos.qty)

    if abs(net_debit) > 0:
        pnl_pct = (current_value - net_debit) / abs(net_debit)
    else:
        pnl_pct = 0.0

    # Expiry imminent — close
    if dte <= close_dte:
        return OptionsAction(
            action="close", urgency="immediate", dte=dte,
            unrealized_pnl_pct=pnl_pct,
            reason=f"Spread at {dte} DTE — close to avoid pin risk and assignment.",
        )

    # Profit target
    if pnl_pct >= profit_target_pct:
        return OptionsAction(
            action="close", urgency="soon", dte=dte,
            unrealized_pnl_pct=pnl_pct,
            reason=(
                f"Spread profit target reached ({pnl_pct:.0%}). "
                f"Close — remaining upside not worth the risk."
            ),
        )

    # Max loss is capped for spreads — less urgency to defend
    return OptionsAction(
        action="hold", urgency="monitor", dte=dte,
        unrealized_pnl_pct=pnl_pct,
        reason=(
            f"Spread at {dte} DTE, P&L {pnl_pct:.0%}. "
            f"Max loss capped at net debit — hold unless thesis broken."
        ),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _dte(expiry_str: str) -> int:
    """Days to expiration from an expiry date string."""
    try:
        expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
    except ValueError:
        return -1
    return (expiry_date - date.today()).days


def _next_monthly_expiry(
    current_expiry: str, available: list[str] | None
) -> str | None:
    """Find the next monthly expiry after the current one."""
    if not available:
        return None
    try:
        current = datetime.strptime(current_expiry, "%Y-%m-%d").date()
    except ValueError:
        return available[0] if available else None

    future = []
    for exp_str in available:
        try:
            exp = datetime.strptime(exp_str, "%Y-%m-%d").date()
            if exp > current:
                future.append(exp_str)
        except ValueError:
            continue

    return min(future) if future else None
