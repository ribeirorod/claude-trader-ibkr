import asyncio
from dotenv import load_dotenv

from vibe import Trader, Scheduler


trader = Trader()
scheduler = Scheduler()


@scheduler.every(seconds=10)
async def breakout_strategy() -> None:
    history = await trader.history("AAPL", start="today", interval="1m")
    if history.empty:
        return
    current = float(history.iloc[-1]["close"])
    high_20 = float(history.tail(20)["high"].max())
    if current > high_20:
        await trader.buy("AAPL", quantity=1, order_type="market")


async def main() -> None:
    load_dotenv()
    await scheduler.run()


if __name__ == "__main__":
    asyncio.run(main())




