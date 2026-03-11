from __future__ import annotations
from pydantic import BaseModel

class AlertCondition(BaseModel):
    operator: str          # ">=" | "<="
    value: float

class Alert(BaseModel):
    alert_id: str
    name: str
    ticker: str | None = None
    conid: int | None = None
    condition: AlertCondition | None = None
    active: bool = True
    triggered: bool = False
