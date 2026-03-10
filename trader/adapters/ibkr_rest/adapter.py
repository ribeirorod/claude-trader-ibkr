from __future__ import annotations
from trader.adapters.base import Adapter
from trader.adapters.ibkr_rest.client import IBKRRestClient
from trader.models import (
    Account, Balance, Margin, Order, OrderRequest,
    Position, Quote, OptionChain, OptionContract, NewsItem
)
from trader.config import Config

_ORDER_TYPE_MAP = {
    "market": "MKT", "limit": "LMT", "stop": "STP",
    "trailing_stop": "TRAIL", "bracket": "LMT",
}

_STATUS_MAP = {
    "PreSubmitted": "open", "Submitted": "open", "Filled": "filled",
    "Cancelled": "cancelled", "Inactive": "cancelled",
}

class IBKRRestAdapter(Adapter):
    def __init__(self, config: Config):
        self._config = config
        self._client = IBKRRestClient(config)
        self._account_id = config.ib_account

    async def connect(self) -> None:
        status = await self._client.get("/iserver/auth/status")
        if not status.get("authenticated"):
            raise RuntimeError("IBKR Client Portal Gateway not authenticated. Log in via browser first.")

    async def disconnect(self) -> None:
        await self._client.aclose()

    async def get_account(self) -> Account:
        data = await self._client.get(f"/portfolio/{self._account_id}/summary")
        return Account(
            account_id=self._account_id,
            balance=Balance(
                cash=float(data.get("totalcashvalue", {}).get("amount", 0)),
                net_liquidation=float(data.get("netliquidation", {}).get("amount", 0)),
                buying_power=float(data.get("buyingpower", {}).get("amount", 0)),
            ),
            margin=Margin(
                initial_margin=float(data.get("initmarginreq", {}).get("amount", 0)),
                maintenance_margin=float(data.get("maintmarginreq", {}).get("amount", 0)),
                available_margin=float(data.get("excessliquidity", {}).get("amount", 0)),
            ),
        )

    async def get_quotes(self, tickers: list[str]) -> list[Quote]:
        quotes = []
        for ticker in tickers:
            try:
                search = await self._client.get(f"/iserver/secdef/search?symbol={ticker}")
                conid = search[0]["conid"] if search else None
                if not conid:
                    continue
                snap = await self._client.get(f"/iserver/marketdata/snapshot?conids={conid}&fields=31,84,86")
                d = snap[0] if snap else {}
                quotes.append(Quote(
                    ticker=ticker,
                    last=float(d.get("31", 0)) or None,
                    bid=float(d.get("84", 0)) or None,
                    ask=float(d.get("86", 0)) or None,
                ))
            except Exception:
                quotes.append(Quote(ticker=ticker))
        return quotes

    async def get_option_chain(self, ticker: str, expiry: str) -> OptionChain:
        search = await self._client.get(f"/iserver/secdef/search?symbol={ticker}")
        conid = search[0]["conid"]
        month = expiry[:7].replace("-", "")
        strikes = await self._client.get(
            f"/iserver/secdef/strike?conid={conid}&sectype=OPT&month={month}"
        )
        contracts = []
        for strike in strikes.get("call", []):
            contracts.append(OptionContract(strike=strike, right="call", expiry=expiry))
        for strike in strikes.get("put", []):
            contracts.append(OptionContract(strike=strike, right="put", expiry=expiry))
        return OptionChain(ticker=ticker, expiry=expiry, contracts=contracts)

    async def place_order(self, req: OrderRequest) -> Order:
        conid = await self._resolve_conid(req.ticker, req.contract_type,
                                          req.expiry, req.strike, req.right)
        body = {
            "conid": conid,
            "orderType": _ORDER_TYPE_MAP[req.order_type],
            "side": req.side.upper(),
            "quantity": req.qty,
            "tif": "DAY",
        }
        if req.price:
            body["price"] = req.price
        if req.trail_percent:
            body["trailingAmt"] = req.trail_percent
            body["trailingType"] = "%"
        if req.trail_amount:
            body["trailingAmt"] = req.trail_amount
            body["trailingType"] = "amt"

        resp = await self._client.post(
            f"/iserver/account/{self._account_id}/orders",
            json={"orders": [body]}
        )
        r = resp[0] if isinstance(resp, list) else resp
        return Order(
            order_id=str(r.get("order_id", r.get("orderId", ""))),
            ticker=req.ticker, qty=req.qty, side=req.side,
            order_type=req.order_type, status="open", price=req.price,
        )

    async def modify_order(self, order_id: str, **kwargs) -> Order:
        await self._client.post(
            f"/iserver/account/{self._account_id}/order/{order_id}",
            json=kwargs
        )
        return Order(
            order_id=order_id,
            ticker=kwargs.get("ticker", ""),
            qty=float(kwargs.get("quantity", 0)),
            side=kwargs.get("side", "buy"),
            order_type=kwargs.get("orderType", "limit"),
            status="open",
            price=kwargs.get("price"),
        )

    async def cancel_order(self, order_id: str) -> bool:
        await self._client.delete(
            f"/iserver/account/{self._account_id}/order/{order_id}"
        )
        return True

    async def list_orders(self, status: str = "all") -> list[Order]:
        data = await self._client.get("/iserver/account/orders")
        result = []
        for o in data.get("orders", []):
            order_status = _STATUS_MAP.get(o.get("status", ""), "open")
            if status != "all" and order_status != status:
                continue
            result.append(Order(
                order_id=str(o.get("orderId", "")),
                ticker=o.get("ticker", ""),
                qty=float(o.get("remainingQuantity", 0)),
                side=o.get("side", "buy").lower(),
                order_type=o.get("orderType", "market").lower(),
                status=order_status,
                price=o.get("price"),
                filled_price=o.get("avgPrice"),
                filled_qty=o.get("filledQuantity"),
            ))
        return result

    async def list_positions(self) -> list[Position]:
        data = await self._client.get(f"/portfolio/{self._account_id}/positions/0")
        return [
            Position(
                ticker=p.get("ticker", p.get("contractDesc", "")),
                qty=float(p.get("position", 0)),
                avg_cost=float(p.get("avgCost", 0)),
                market_value=float(p.get("mktValue", 0)),
                unrealized_pnl=float(p.get("unrealizedPnl", 0)),
                realized_pnl=float(p.get("realizedPnl", 0)),
            )
            for p in data
        ]

    async def close_position(self, ticker: str) -> Order:
        positions = await self.list_positions()
        pos = next((p for p in positions if p.ticker == ticker), None)
        if not pos:
            raise ValueError(f"No open position for {ticker}")
        side = "sell" if pos.qty > 0 else "buy"
        req = OrderRequest(ticker=ticker, qty=abs(pos.qty), side=side, order_type="market")
        return await self.place_order(req)

    async def get_news(self, tickers: list[str], limit: int = 10) -> list[NewsItem]:
        items = []
        for ticker in tickers:
            try:
                search = await self._client.get(f"/iserver/secdef/search?symbol={ticker}")
                conid = search[0]["conid"] if search else None
                if not conid:
                    continue
                data = await self._client.get(f"/iserver/news/news?conid={conid}&limit={limit}")
                for n in data.get("news", []):
                    items.append(NewsItem(
                        id=n.get("id", ""),
                        ticker=ticker,
                        headline=n.get("headline", ""),
                        published_at=n.get("date", ""),
                        source=n.get("provider", ""),
                    ))
            except Exception:
                pass
        return items

    async def _resolve_conid(
        self, ticker: str, contract_type: str = "stock",
        expiry: str | None = None, strike: float | None = None,
        right: str | None = None
    ) -> int:
        search = await self._client.get(f"/iserver/secdef/search?symbol={ticker}")
        return search[0]["conid"]
