from __future__ import annotations
from trader.adapters.base import Adapter
from trader.models import (
    Account, Balance, Margin, Order, OrderRequest,
    Position, Quote, OptionChain, OptionContract, NewsItem,
    Alert, ScanResult,
)
from trader.config import Config

class IBKRTWSAdapter(Adapter):
    """ib_insync adapter — requires pip install 'trader[tws]' and TWS/Gateway running."""

    def __init__(self, config: Config):
        self._config = config
        self._ib = None  # lazy init

    def _get_ib(self):
        if self._ib is None:
            try:
                from ib_insync import IB
            except ImportError:
                raise ImportError(
                    "ib_insync not installed. Run: pip install 'trader[tws]'"
                )
            self._ib = IB()
        return self._ib

    async def connect(self) -> None:
        ib = self._get_ib()
        await ib.connectAsync(
            self._config.ib_host,
            self._config.ib_port,
            clientId=101,
        )

    async def disconnect(self) -> None:
        if self._ib:
            self._ib.disconnect()

    async def get_account(self) -> Account:
        ib = self._get_ib()
        vals = {v.tag: v.value for v in ib.accountValues()}
        return Account(
            account_id=self._config.ib_account,
            balance=Balance(
                cash=float(vals.get("TotalCashValue", 0)),
                net_liquidation=float(vals.get("NetLiquidation", 0)),
                buying_power=float(vals.get("BuyingPower", 0)),
            ),
            margin=Margin(
                initial_margin=float(vals.get("InitMarginReq", 0)),
                maintenance_margin=float(vals.get("MaintMarginReq", 0)),
                available_margin=float(vals.get("ExcessLiquidity", 0)),
            ),
        )

    async def get_quotes(self, tickers: list[str]) -> list[Quote]:
        from ib_insync import Stock
        ib = self._get_ib()
        contracts = [Stock(t, "SMART", "USD") for t in tickers]
        await ib.qualifyContractsAsync(*contracts)
        tickers_data = [ib.reqMktData(c, "", False, False) for c in contracts]
        try:
            await ib.sleep(1)
            return [
                Quote(ticker=t, bid=td.bid, ask=td.ask, last=td.last)
                for t, td in zip(tickers, tickers_data)
            ]
        finally:
            for c in contracts:
                ib.cancelMktData(c)

    async def get_option_chain(self, ticker: str, expiry: str) -> OptionChain:
        from ib_insync import Stock
        ib = self._get_ib()
        stock = Stock(ticker, "SMART", "USD")
        await ib.qualifyContractsAsync(stock)
        chains = await ib.reqSecDefOptParamsAsync(ticker, "", "STK", stock.conId)
        chain = next((c for c in chains if c.exchange == "SMART"), chains[0])
        contracts = []
        for strike in chain.strikes:
            for right in ["C", "P"]:
                contracts.append(OptionContract(
                    strike=strike,
                    right="call" if right == "C" else "put",
                    expiry=expiry,
                ))
        return OptionChain(ticker=ticker, expiry=expiry, contracts=contracts)

    async def place_order(self, req: OrderRequest) -> Order:
        from ib_insync import Stock, Option, LimitOrder, MarketOrder, StopOrder, Order as IBOrder
        ib = self._get_ib()
        if req.contract_type == "option":
            contract = Option(req.ticker, req.expiry.replace("-", ""),
                              req.strike, req.right[0].upper(), "SMART")
        else:
            contract = Stock(req.ticker, "SMART", "USD")
        await ib.qualifyContractsAsync(contract)
        if req.order_type == "market":
            ibkr_order = MarketOrder(req.side.upper(), req.qty)
        elif req.order_type == "limit":
            ibkr_order = LimitOrder(req.side.upper(), req.qty, req.price)
        elif req.order_type == "stop":
            ibkr_order = StopOrder(req.side.upper(), req.qty, req.price)
        else:
            ibkr_order = MarketOrder(req.side.upper(), req.qty)
        trade = ib.placeOrder(contract, ibkr_order)
        return Order(
            order_id=str(trade.order.orderId),
            ticker=req.ticker, qty=req.qty, side=req.side,
            order_type=req.order_type, status="open", price=req.price,
        )

    async def modify_order(self, order_id: str, **kwargs) -> Order:
        raise NotImplementedError("Use cancel + replace for TWS order modification")

    async def cancel_order(self, order_id: str) -> bool:
        ib = self._get_ib()
        trades = ib.openTrades()
        trade = next((t for t in trades if str(t.order.orderId) == order_id), None)
        if trade:
            ib.cancelOrder(trade.order)
            return True
        return False

    async def list_orders(self, status: str = "all") -> list[Order]:
        ib = self._get_ib()
        trades = ib.trades()
        result = []
        for t in trades:
            s = t.orderStatus.status
            mapped = "filled" if s == "Filled" else "cancelled" if s in ("Cancelled", "Inactive") else "open"
            if status != "all" and mapped != status:
                continue
            result.append(Order(
                order_id=str(t.order.orderId),
                ticker=t.contract.symbol,
                qty=t.order.totalQuantity,
                side=t.order.action.lower(),
                order_type=t.order.orderType.lower(),
                status=mapped,
                price=t.order.lmtPrice or None,
                filled_price=t.orderStatus.avgFillPrice or None,
                filled_qty=t.orderStatus.filled or None,
            ))
        return result

    async def list_positions(self) -> list[Position]:
        ib = self._get_ib()
        return [
            Position(
                ticker=p.contract.symbol,
                qty=p.position,
                avg_cost=p.avgCost,
                market_value=p.position * p.avgCost,
                unrealized_pnl=p.unrealizedPNL or 0,
                realized_pnl=p.realizedPNL or 0,
            )
            for p in ib.portfolio()
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
        from ib_insync import Stock
        ib = self._get_ib()
        items = []
        for ticker in tickers:
            contract = Stock(ticker, "SMART", "USD")
            await ib.qualifyContractsAsync(contract)
            news = await ib.reqHistoricalNewsAsync(
                contract.conId, providers="BRFG+DJNL",
                startDateTime="", endDateTime="", totalResults=limit
            )
            for n in news:
                items.append(NewsItem(
                    id=n.articleId,
                    ticker=ticker,
                    headline=n.headline,
                    published_at=str(n.time),
                    source=n.providerCode,
                ))
        return items

    async def scan(self, scan_type: str, location: str = "STK.US.MAJOR", filters: list[dict] | None = None, limit: int = 20) -> list[ScanResult]:
        raise NotImplementedError("Scanner not supported on ibkr-tws; use ibkr-rest")

    async def scan_params(self) -> dict:
        raise NotImplementedError("Scanner not supported on ibkr-tws; use ibkr-rest")

    async def list_alerts(self) -> list[Alert]:
        raise NotImplementedError("Alerts not supported on ibkr-tws; use ibkr-rest")

    async def create_alert(self, ticker: str, operator: str, price: float, name: str | None = None) -> Alert:
        raise NotImplementedError("Alerts not supported on ibkr-tws; use ibkr-rest")

    async def delete_alert(self, alert_id: str) -> bool:
        raise NotImplementedError("Alerts not supported on ibkr-tws; use ibkr-rest")
