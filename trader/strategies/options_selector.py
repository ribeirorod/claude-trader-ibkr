"""Options selector — translates a directional signal into a concrete option contract.

Pure function: takes signal, current price, ATR, and chain data; returns a
recommendation. No broker calls — the caller is responsible for fetching the
chain via ``adapter.get_option_chain()``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from trader.models.quote import OptionChain, OptionContract


@dataclass
class OptionsRecommendation:
    """Recommended option trade derived from a strategy signal."""

    action: str  # "buy_put", "buy_call", or "no_action"
    contract: OptionContract | None
    suggested_qty: int
    max_risk: float  # premium × 100 × qty
    rationale: str


def select_contract(
    signal: int,
    current_price: float,
    current_atr: float,
    chain: OptionChain,
    account_value: float,
    risk_pct: float = 0.02,
    min_dte: int = 30,
    max_dte: int = 45,
    target_delta_range: tuple[float, float] = (0.30, 0.40),
) -> OptionsRecommendation:
    """Pick the best option contract for a pullback signal.

    Parameters
    ----------
    signal : int
        -1 (bearish → buy put), +1 (bullish → buy call), 0 (no action).
    current_price : float
        Current underlying price.
    current_atr : float
        Current ATR value, used for strike targeting.
    chain : OptionChain
        Full option chain (from ``trader quote chain``).
    account_value : float
        Total account value for position sizing.
    risk_pct : float
        Max fraction of account to risk on the trade (premium = max loss).
    min_dte / max_dte : int
        Acceptable days-to-expiration window.
    target_delta_range : tuple
        Absolute delta range to filter contracts.
    """
    if signal == 0:
        return OptionsRecommendation(
            action="no_action", contract=None,
            suggested_qty=0, max_risk=0.0,
            rationale="Signal is neutral — no trade.",
        )

    right = "put" if signal == -1 else "call"
    action = f"buy_{right}"

    # Target strike: 1 ATR away from current price in the signal direction
    if signal == -1:
        target_strike = current_price - current_atr
    else:
        target_strike = current_price + current_atr

    # Filter chain by right and DTE
    candidates = _filter_candidates(
        chain.contracts, right, chain.expiry, min_dte, max_dte,
    )

    # Score candidates by proximity to target strike and delta preference
    if not candidates:
        return OptionsRecommendation(
            action=action, contract=None,
            suggested_qty=0, max_risk=0.0,
            rationale=f"No {right} contracts found within {min_dte}-{max_dte} DTE.",
        )

    best = _rank_candidates(candidates, target_strike, target_delta_range)

    if best is None:
        # Fallback: pick closest to target strike regardless of delta
        best = min(candidates, key=lambda c: abs(c.strike - target_strike))

    # Position sizing: premium × 100 = cost per contract; max risk = premium paid
    ask = best.ask or best.last or 0.0
    if ask <= 0:
        return OptionsRecommendation(
            action=action, contract=best,
            suggested_qty=0, max_risk=0.0,
            rationale=f"Best {right} at {best.strike} has no valid ask price.",
        )

    max_dollar_risk = account_value * risk_pct
    cost_per_contract = ask * 100  # standard equity option multiplier
    suggested_qty = max(1, int(max_dollar_risk / cost_per_contract))
    max_risk = round(cost_per_contract * suggested_qty, 2)

    delta_str = f"{best.delta:.2f}" if best.delta is not None else "n/a"
    rationale = (
        f"{'Put' if signal == -1 else 'Call'} @ strike {best.strike}, "
        f"delta {delta_str}, expiry {best.expiry}. "
        f"Target strike was {target_strike:.2f} (1 ATR from {current_price:.2f}). "
        f"Max risk ${max_risk:.0f} ({suggested_qty} contract{'s' if suggested_qty > 1 else ''})."
    )

    return OptionsRecommendation(
        action=action,
        contract=best,
        suggested_qty=suggested_qty,
        max_risk=max_risk,
        rationale=rationale,
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


def _filter_candidates(
    contracts: list[OptionContract],
    right: str,
    chain_expiry: str,
    min_dte: int,
    max_dte: int,
) -> list[OptionContract]:
    """Filter contracts by right and DTE window."""
    dte_val = _dte(chain_expiry)
    filtered = []
    for c in contracts:
        if c.right != right:
            continue
        # Use per-contract expiry if available, else chain-level expiry
        contract_dte = _dte(c.expiry) if c.expiry else dte_val
        if min_dte <= contract_dte <= max_dte:
            filtered.append(c)
    return filtered


def _rank_candidates(
    candidates: list[OptionContract],
    target_strike: float,
    delta_range: tuple[float, float],
) -> OptionContract | None:
    """Pick the best candidate: within delta range, closest to target strike."""
    in_delta = []
    for c in candidates:
        if c.delta is not None:
            abs_delta = abs(c.delta)
            if delta_range[0] <= abs_delta <= delta_range[1]:
                in_delta.append(c)

    if not in_delta:
        return None

    return min(in_delta, key=lambda c: abs(c.strike - target_strike))
