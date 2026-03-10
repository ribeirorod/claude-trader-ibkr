from pydantic import BaseModel


class Position(BaseModel):
    ticker: str
    qty: float
    avg_cost: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float = 0.0
    contract_type: str = "stock"


class PnL(BaseModel):
    ticker: str | None = None
    unrealized: float
    realized: float
    total: float
