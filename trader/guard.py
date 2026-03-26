from __future__ import annotations
from dataclasses import dataclass
from trader.models import OrderRequest, Account, Position, Order


@dataclass
class GuardResult:
    allowed: bool
    reason: str | None = None
    details: dict | None = None


class OrderGuard:
    def validate(
        self,
        order: OrderRequest,
        account: Account,
        positions: list[Position],
        open_orders: list[Order],
        max_single_position_pct: float = 0.10,
        cash_reserve_pct: float = 0.10,
        max_new_positions_per_day: int = 3,
        today_new_position_count: int = 0,
    ) -> GuardResult:
        # Sell/cover orders bypass capital guards — you're reducing exposure
        is_entry = order.side in ("buy", "short")

        # Duplicate detection (applies to all order types)
        for o in open_orders:
            if o.ticker == order.ticker and o.side == order.side and o.status == "open":
                return GuardResult(
                    allowed=False, reason="duplicate_order",
                    details={"existing_order_id": o.order_id},
                )

        if not is_entry:
            return GuardResult(allowed=True)

        nlv = account.balance.net_liquidation
        order_cost = self._estimate_cost(order)
        existing_exposure = sum(abs(p.market_value) for p in positions)
        pending_exposure = sum(
            (o.price or 0) * o.qty for o in open_orders if o.status == "open" and o.side in ("buy", "short")
        )
        total_exposure = existing_exposure + pending_exposure

        # Daily new position limit
        if today_new_position_count >= max_new_positions_per_day:
            return GuardResult(
                allowed=False, reason="daily_limit",
                details={"today": today_new_position_count, "max": max_new_positions_per_day},
            )

        # No margin: total exposure must not exceed NLV
        if total_exposure + order_cost > nlv:
            return GuardResult(
                allowed=False, reason="margin_not_allowed",
                details={"total_exposure": total_exposure + order_cost, "nlv": nlv},
            )

        # Cash floor: exposure must not exceed (1 - reserve) * NLV
        max_exposure = (1 - cash_reserve_pct) * nlv
        if total_exposure + order_cost > max_exposure:
            return GuardResult(
                allowed=False, reason="cash_floor_breach",
                details={"total_exposure": total_exposure + order_cost, "max_exposure": max_exposure},
            )

        # Max single position
        ticker_exposure = sum(abs(p.market_value) for p in positions if p.ticker == order.ticker)
        if (ticker_exposure + order_cost) / nlv > max_single_position_pct:
            return GuardResult(
                allowed=False, reason="position_limit",
                details={
                    "ticker": order.ticker,
                    "new_exposure": ticker_exposure + order_cost,
                    "max_pct": max_single_position_pct,
                },
            )

        return GuardResult(allowed=True)

    def _estimate_cost(self, order: OrderRequest) -> float:
        if order.price:
            return order.price * order.qty
        return 0.0
