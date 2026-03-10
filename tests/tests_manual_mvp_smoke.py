import asyncio
import os
from dotenv import load_dotenv

from vibe import Trader


async def main():
    load_dotenv()
    trader = Trader()
    results = {}
    try:
        # 1) Market buy small qty
        r1 = await trader.buy("AAPL", quantity=1, order_type="market")
        results["market_buy"] = r1.status

        # 2) Limit sell far from market to stay pending, then cancel
        r2 = await trader.sell("AAPL", quantity=1, order_type="limit", limit_price=1000.0)
        results["limit_sell_submit"] = r2.status
        await trader.cancel(order_id=r2.order_id)
        # Allow IBKR to process cancel briefly
        await asyncio.sleep(1)
        r2s = await trader.get_order(order_id=r2.order_id)
        results["limit_sell_after_cancel"] = r2s.status

        # 3) Stop sell (should accept, may remain pending)
        r3 = await trader.sell("AAPL", quantity=1, order_type="stop", stop_price=1.0)
        results["stop_sell_submit"] = r3.status
        await trader.cancel(order_id=r3.order_id)

        # 4) History checks
        h1 = await trader.history("AAPL", start="today", interval="1m")
        h5 = await trader.history("AAPL", start="today", interval="5m")
        hH = await trader.history("AAPL", start="2024-01-01", interval="1h")
        hD = await trader.history("AAPL", start="2024-01-01", interval="1d")
        results["history_shapes"] = {
            "1m": (len(h1.index), list(h1.columns)),
            "5m": (len(h5.index), list(h5.columns)),
            "1h": (len(hH.index), list(hH.columns)),
            "1d": (len(hD.index), list(hD.columns)),
        }

        print("SMOKE_RESULTS:", results)
    finally:
        await trader.close()

if __name__ == "__main__":
    asyncio.run(main())
