from __future__ import annotations
from pydantic import BaseModel


class Quote(BaseModel):
    ticker: str
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    volume: int | None = None
    contract_type: str = "stock"


class OptionContract(BaseModel):
    strike: float
    right: str
    expiry: str
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    implied_vol: float | None = None
    open_interest: int | None = None


class OptionChain(BaseModel):
    ticker: str
    expiry: str
    contracts: list[OptionContract]
