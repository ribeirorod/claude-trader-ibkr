from __future__ import annotations
import asyncio
from datetime import datetime
from trader.adapters.base import Adapter
from trader.adapters.ibkr_rest.client import IBKRRestClient
from trader.models import (
    Account, Balance, Margin, Order, OrderRequest,
    Position, Quote, OptionChain, OptionContract, NewsItem,
    Alert, AlertCondition, ScanResult,
)
from trader.config import Config

_F_LAST, _F_BID, _F_ASK = "31", "84", "86"
_QUOTE_FIELDS = f"{_F_LAST},{_F_BID},{_F_ASK}"

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
        self._account_id = config.active_account

    async def connect(self) -> None:
        _RETRIES = 8
        _DELAY = 3.0
        last_exc: Exception | None = None
        for attempt in range(_RETRIES):
            try:
                # Tickle initializes the session after browser login; without it
                # auth/status may keep returning authenticated=false indefinitely.
                await self._client.post("/tickle", json={})
                status = await self._client.get("/iserver/auth/status")
                if status.get("authenticated"):
                    return
            except Exception as exc:
                last_exc = exc
            if attempt < _RETRIES - 1:
                await asyncio.sleep(_DELAY)
        raise RuntimeError(
            "IBKR Client Portal Gateway not authenticated after retries. "
            "Start the gateway and log in via browser at https://localhost:5001"
        ) from last_exc

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
        async def resolve(ticker: str) -> tuple[str, str] | None:
            try:
                conid = await self._resolve_conid(ticker)
                return (str(conid), ticker)
            except Exception:
                return None

        resolved = await asyncio.gather(*[resolve(t) for t in tickers])
        conid_map = {conid: ticker for conid, ticker in resolved if conid is not None}

        if not conid_map:
            return [Quote(ticker=t) for t in tickers]

        # IBKR snapshot: first call subscribes the stream, data may arrive on retry
        snap = await self._client.get(
            f"/iserver/marketdata/snapshot?conids={','.join(conid_map)}&fields={_QUOTE_FIELDS}"
        )
        # Retry conids that came back with no price data at all
        missing = [str(s["conid"]) for s in snap if not (s.get(_F_LAST) or s.get(_F_BID) or s.get(_F_ASK))]
        if missing:
            await asyncio.sleep(1)
            retry = await self._client.get(
                f"/iserver/marketdata/snapshot?conids={','.join(missing)}&fields={_QUOTE_FIELDS}"
            )
            snap = [s for s in snap if str(s.get("conid")) not in missing] + retry

        by_conid = {str(s.get("conid")): s for s in snap}
        return [
            Quote(
                ticker=ticker,
                last=float(d[_F_LAST]) if d.get(_F_LAST) else None,
                bid=float(d[_F_BID]) if d.get(_F_BID) else None,
                ask=float(d[_F_ASK]) if d.get(_F_ASK) else None,
            )
            for conid, ticker in conid_map.items()
            for d in [by_conid.get(conid, {})]
        ]

    async def get_option_chain(self, ticker: str, expiry: str) -> OptionChain:
        search = await self._client.get(f"/iserver/secdef/search?symbol={ticker}")
        conid = search[0]["conid"]
        dt = datetime.strptime(expiry[:7], "%Y-%m")
        month = dt.strftime("%b%y").upper()  # e.g. "MAR26"
        strikes = await self._client.get(
            f"/iserver/secdef/strikes?conid={conid}&sectype=OPT&month={month}"
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
        ibkr_order_type = _ORDER_TYPE_MAP.get(req.order_type)
        if ibkr_order_type is None:
            raise ValueError(f"Unsupported order_type '{req.order_type}'. Supported: {list(_ORDER_TYPE_MAP)}")
        body = {
            "conid": conid,
            "orderType": ibkr_order_type,
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

        # Place parent order first; bracket children are linked via parentId after
        resp = await self._client.post(
            f"/iserver/account/{self._account_id}/orders",
            json={"orders": [body]}
        )
        resp = await self._confirm_replies(resp)
        r = resp[0] if isinstance(resp, list) else resp
        if "error" in r:
            raise ValueError(f"IBKR rejected order: {r['error']}")
        parent_order_id = r.get("order_id", r.get("orderId"))

        # Place bracket child orders linked to parent
        if req.order_type == "bracket" and parent_order_id:
            child_side = "SELL" if req.side == "buy" else "BUY"
            children = []
            if req.take_profit:
                children.append({
                    "conid": conid, "orderType": "LMT", "side": child_side,
                    "quantity": req.qty, "price": req.take_profit,
                    "tif": "GTC", "parentId": parent_order_id,
                })
            if req.stop_loss:
                children.append({
                    "conid": conid, "orderType": "STP", "side": child_side,
                    "quantity": req.qty, "price": req.stop_loss,
                    "tif": "GTC", "parentId": parent_order_id,
                })
            if children:
                child_resp = await self._client.post(
                    f"/iserver/account/{self._account_id}/orders",
                    json={"orders": children}
                )
                await self._confirm_replies(child_resp)

        return Order(
            order_id=str(parent_order_id or ""),
            ticker=req.ticker, qty=req.qty, side=req.side,
            order_type=req.order_type, status="open", price=req.price,
        )

    async def modify_order(self, order_id: str, **kwargs) -> Order:
        # Fetch current order state to build a valid full-body modify request
        orders_data = await self._client.get("/iserver/account/orders")
        existing = next(
            (o for o in orders_data.get("orders", []) if str(o.get("orderId")) == str(order_id)),
            None
        )
        if existing is None:
            raise ValueError(f"Order {order_id} not found")
        conid = int(existing.get("conid", 0))
        # origOrderType uses IBKR canonical names (LMT, STP, MKT); orderType may be display form
        order_type = existing.get("origOrderType") or existing.get("orderType", "LMT")
        # timeInForce "CLOSE" is a display value; map back to valid submit values
        _TIF_MAP = {"CLOSE": "DAY", "DAY": "DAY", "GTC": "GTC", "IOC": "IOC", "GTD": "GTD"}
        tif = _TIF_MAP.get(existing.get("timeInForce", "DAY"), "DAY")
        body = {
            "conid": conid,
            "orderType": order_type,
            "side": existing.get("side", "BUY"),
            "quantity": kwargs.get("quantity", existing.get("totalSize", existing.get("size", 0))),
            "tif": tif,
            "price": kwargs.get("price", existing.get("price")),
        }
        resp = await self._client.post(
            f"/iserver/account/{self._account_id}/order/{order_id}",
            json=body
        )
        resp = await self._confirm_replies(resp)
        r = resp[0] if isinstance(resp, list) else resp
        if "error" in r:
            raise ValueError(f"IBKR rejected modify: {r['error']}")
        return Order(
            order_id=order_id,
            ticker=existing.get("ticker", ""),
            qty=float(body["quantity"]),
            side=body["side"].lower(),
            order_type=body["orderType"].lower(),
            status="open",
            price=body.get("price"),
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
                qty=float(o.get("totalSize", o.get("size", 0))),
                side=o.get("side", "buy").lower(),
                order_type=o.get("orderType", "market").lower(),
                status=order_status,
                price=o.get("price") or None,
                filled_price=o.get("avgPrice") or None,
                filled_qty=o.get("filledQuantity"),
                take_profit=o.get("takeProfitPrice") or None,
                stop_loss=o.get("stopLossPrice") or None,
                created_at=o.get("lastExecutionTime") or o.get("lastExecutionTime_r") or None,
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
        async def fetch(ticker: str) -> list[NewsItem]:
            try:
                conid = await self._resolve_conid(ticker)
                data = await self._client.get(f"/iserver/news/news?conid={conid}&limit={limit}")
                return [
                    NewsItem(
                        id=n.get("id", ""),
                        ticker=ticker,
                        headline=n.get("headline", ""),
                        published_at=n.get("date", ""),
                        source=n.get("provider", ""),
                    )
                    for n in data.get("news", [])
                ]
            except Exception:
                return []

        results = await asyncio.gather(*[fetch(t) for t in tickers])
        return [item for ticker_items in results for item in ticker_items]

    # ------------------------------------------------------------------ alerts

    async def list_alerts(self) -> list[Alert]:
        data = await self._client.get(f"/iserver/account/{self._account_id}/alerts")
        alerts = []
        for a in data if isinstance(data, list) else []:
            cond = None
            conditions = a.get("conditions", [])
            if conditions:
                c = conditions[0]
                op = ">=" if c.get("operator") in (">=", ">") else "<="
                try:
                    val = float(c.get("value", 0))
                except (TypeError, ValueError):
                    val = 0.0
                cond = AlertCondition(operator=op, value=val)
            alerts.append(Alert(
                alert_id=str(a.get("id", "")),
                name=a.get("name", ""),
                ticker=a.get("ticker") or None,
                conid=a.get("conid") or None,
                condition=cond,
                active=bool(a.get("active", 1)),
                triggered=bool(a.get("triggered", 0)),
            ))
        return alerts

    async def create_alert(
        self, ticker: str, operator: str, price: float, name: str | None = None
    ) -> Alert:
        conid = await self._resolve_conid(ticker)
        alert_name = name or f"{ticker} {operator} {price}"
        payload = {
            "alertName": alert_name,
            "alertMessage": alert_name,
            "alertRepeatable": 1,
            "sendMessage": 0,
            "showPopup": 0,
            "iTWSOrdersOnly": 0,
            "tif": "GTC",
            "conditions": [
                {
                    "type": 1,                    # price condition
                    "conidex": f"{conid}@SMART",  # exchange-qualified conid
                    "operator": operator,
                    "value": str(price),
                    "triggerMethod": 0,
                    "logicBind": "n",             # last (and only) condition
                }
            ],
        }
        try:
            resp = await self._client.post(
                f"/iserver/account/{self._account_id}/alert", json=payload
            )
        except Exception as exc:
            if "403" in str(exc):
                raise PermissionError(
                    "IBKR denied alert creation (403). Enable 'Trading Access' for the "
                    "Client Portal API in IBKR Account Management → Settings → API."
                ) from exc
            raise
        alert_id = str(resp.get("id") or resp.get("alert_id") or "")
        return Alert(
            alert_id=alert_id,
            name=alert_name,
            ticker=ticker,
            conid=conid,
            condition=AlertCondition(operator=operator, value=price),
        )

    async def delete_alert(self, alert_id: str) -> bool:
        resp = await self._client.delete(
            f"/iserver/account/{self._account_id}/alert/{alert_id}"
        )
        return bool(resp.get("success") or resp.get("deleted") or True)

    # ------------------------------------------------------------------ scanner

    async def scan(
        self,
        scan_type: str,
        location: str = "STK.US.MAJOR",
        filters: list[dict] | None = None,
        limit: int = 20,
    ) -> list[ScanResult]:
        payload: dict = {
            "instrument": location.split(".")[0],  # e.g. "STK" from "STK.US.MAJOR"
            "location": location,
            "type": scan_type,
            "filter": filters or [],
        }
        data = await self._client.post("/iserver/scanner/run", json=payload)
        contracts = data.get("contracts", []) if isinstance(data, dict) else data
        return [
            ScanResult(
                symbol=c.get("symbol", ""),
                company_name=c.get("company_name", ""),
                conid=c.get("con_id") or None,
                listing_exchange=c.get("listing_exchange", ""),
                sec_type=c.get("sec_type", ""),
                column_value=c.get("column_name", ""),
            )
            for c in contracts[:limit]
        ]

    async def scan_params(self) -> dict:
        return await self._client.get("/iserver/scanner/params")

    async def _confirm_replies(self, resp: dict | list, _max: int = 5) -> dict | list:
        """
        IBKR order submission requires confirming warning messages.
        When the response contains {"id": ..., "message": [...]} entries instead
        of {"order_id": ...}, POST /iserver/reply/{id} with {"confirmed": true}
        until we receive actual order confirmations or exhaust retries.
        """
        for _ in range(_max):
            items = resp if isinstance(resp, list) else [resp]
            pending = [r for r in items if "message" in r and "order_id" not in r and "orderId" not in r]
            if not pending:
                return resp
            # Confirm the first pending reply; IBKR processes one at a time.
            # Log the warning messages so they are visible in agent logs.
            reply_id = pending[0]["id"]
            messages = pending[0].get("message", [])
            import sys
            print(f"[ibkr] confirming order warnings: {messages}", file=sys.stderr)
            resp = await self._client.post(f"/iserver/reply/{reply_id}", json={"confirmed": True})
        return resp

    async def _resolve_conid(
        self, ticker: str, contract_type: str = "stock",
        expiry: str | None = None, strike: float | None = None,
        right: str | None = None
    ) -> int:
        search = await self._client.get(f"/iserver/secdef/search?symbol={ticker}")
        if not search:
            raise ValueError(f"Ticker not found: {ticker}")
        underlying_conid = int(search[0]["conid"])
        if contract_type != "option" or not expiry or not strike or not right:
            return underlying_conid
        # Resolve the specific option contract conid
        dt = datetime.strptime(expiry[:7], "%Y-%m")
        month = dt.strftime("%b%y").upper()
        right_char = right[0].upper()  # "C" or "P"
        info = await self._client.get(
            f"/iserver/secdef/info?conid={underlying_conid}&sectype=OPT"
            f"&month={month}&strike={strike}&right={right_char}"
        )
        if not info:
            raise ValueError(f"No option contract found for {ticker} {month} {right_char} {strike}")
        return int(info[0]["conid"])
