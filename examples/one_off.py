import asyncio
import os

from dotenv import load_dotenv
import structlog

from vibe import Trader


log = structlog.get_logger()


def _bold_event(_, __, event_dict):
    evt = event_dict.get("event")
    if evt:
        event_dict["event"] = f"\x1b[1m{evt}\x1b[0m"
    return event_dict


async def main() -> None:
    load_dotenv()

    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _bold_event,
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    )

    trader = Trader()
    try:
        order = await trader.buy("AAPL", quantity=1, order_type="market")
        log.info("market_buy", order_id=order.order_id, status=str(order.status), symbol=order.symbol)
        print()

        history = await trader.history("AAPL", start="2024-01-01", interval="1d")
        tail = history.tail(3).to_dict(orient="records")
        log.info("history_tail", rows=len(tail), data=tail)
        print()
    finally:
        await trader.close()


if __name__ == "__main__":
    asyncio.run(main())


