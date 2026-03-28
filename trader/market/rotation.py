from __future__ import annotations
from trader.market.regime import MarketRegime


def build_rotation_actions(regime: MarketRegime, profile: dict) -> list[dict]:
    """Return ordered rotation action suggestions based on market regime.

    Returns an empty list for BULL — no defensive action needed.
    Returns inverse ETF + defensive sectors for BEAR.
    Returns defensive sectors only for CAUTION.
    """
    bear_cfg = profile.get("bear_market", {})
    if not bear_cfg:
        return []

    inverse_basket = bear_cfg.get("inverse_etf_basket", [])
    defensive_sectors = bear_cfg.get("defensive_sectors", [])
    actions: list[dict] = []

    if regime == MarketRegime.BEAR:
        for etf in inverse_basket:
            actions.append({
                "action": "BUY",
                "ticker": etf["ticker"],
                "reason": f"Bear regime hedge: {etf['description']}",
            })
        for sector in defensive_sectors:
            actions.append({
                "action": "ROTATE",
                "ticker": sector,
                "reason": "Defensive sector rotation — bear regime",
            })

    elif regime == MarketRegime.CAUTION:
        for sector in defensive_sectors[:2]:
            actions.append({
                "action": "CONSIDER",
                "ticker": sector,
                "reason": "Partial defensive rotation — caution regime",
            })

    return actions
