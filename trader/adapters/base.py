from __future__ import annotations
from abc import ABC, abstractmethod
from trader.models import (
    Account, Order, OrderRequest, Position,
    Quote, OptionChain, NewsItem, Alert, ScanResult
)

class Adapter(ABC):

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def get_account(self) -> Account: ...

    @abstractmethod
    async def get_quotes(self, tickers: list[str]) -> list[Quote]: ...

    @abstractmethod
    async def get_option_chain(self, ticker: str, expiry: str) -> OptionChain: ...

    @abstractmethod
    async def place_order(self, req: OrderRequest) -> Order: ...

    @abstractmethod
    async def modify_order(self, order_id: str, **kwargs) -> Order: ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool: ...

    @abstractmethod
    async def list_orders(self, status: str = "all") -> list[Order]: ...

    @abstractmethod
    async def list_positions(self) -> list[Position]: ...

    @abstractmethod
    async def close_position(self, ticker: str) -> Order: ...

    @abstractmethod
    async def get_news(self, tickers: list[str], limit: int = 10) -> list[NewsItem]: ...

    @abstractmethod
    async def list_alerts(self) -> list[Alert]: ...

    @abstractmethod
    async def create_alert(
        self, ticker: str, operator: str, price: float, name: str | None = None
    ) -> Alert: ...

    @abstractmethod
    async def delete_alert(self, alert_id: str) -> bool: ...

    async def get_contract_details(self, conid: int) -> dict:
        """Return sector/industry metadata for a contract. Override in subclass."""
        return {}

    async def validate_option_strike(
        self, ticker: str, expiry: str, strike: float, right: str
    ) -> float | None:
        """Check if a strike exists; return nearest valid strike or None."""
        try:
            chain = await self.get_option_chain(ticker, expiry)
        except Exception:
            return None
        available = [
            c.strike for c in chain.contracts
            if c.right == right and c.strike is not None
        ]
        if not available:
            return None
        if strike in available:
            return strike
        return min(available, key=lambda s: abs(s - strike))

    @abstractmethod
    async def scan(
        self,
        scan_type: str,
        location: str = "STK.US.MAJOR",
        filters: list[dict] | None = None,
        limit: int = 20,
    ) -> list[ScanResult]: ...

    @abstractmethod
    async def scan_params(self) -> dict: ...
