from __future__ import annotations
from typing import Literal
from pydantic import BaseModel


class OrderRequest(BaseModel):
    ticker: str
    qty: float
    side: Literal["buy", "sell", "short"]
    order_type: Literal["market", "limit", "stop", "trailing_stop", "bracket"]
    price: float | None = None
    trail_percent: float | None = None
    trail_amount: float | None = None
    take_profit: float | None = None
    stop_loss: float | None = None
    contract_type: Literal["stock", "etf", "option"] = "stock"
    expiry: str | None = None
    strike: float | None = None
    right: Literal["call", "put"] | None = None


class Order(BaseModel):
    order_id: str
    ticker: str
    qty: float
    side: Literal["buy", "sell", "short"]
    order_type: str
    status: Literal["open", "filled", "cancelled", "pending"]
    price: float | None = None
    filled_price: float | None = None
    filled_qty: float | None = None
    take_profit: float | None = None
    stop_loss: float | None = None
    created_at: str | None = None  # raw IBKR lastExecutionTime
