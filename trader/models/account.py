from pydantic import BaseModel


class Balance(BaseModel):
    cash: float
    net_liquidation: float
    buying_power: float
    currency: str = "USD"


class Margin(BaseModel):
    initial_margin: float
    maintenance_margin: float
    available_margin: float


class Account(BaseModel):
    account_id: str
    balance: Balance
    margin: Margin
