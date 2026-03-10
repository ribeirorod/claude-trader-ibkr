import asyncio
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
        orders = await trader.bracket(
            symbol="AAPL",
            side="buy",
            quantity=1,
            entry_price=170.00,     # use None for market entry
            stop_loss=165.00,
            take_profit=175.00,
            tif="GTC",
            outside_rth=False,
        )
        log.info(
            "bracket_submitted",
            parent_id=orders["parent"].order_id,
            tp_id=orders["take_profit"].order_id,
            sl_id=orders["stop_loss"].order_id,
            parent_status=orders["parent"].status,
            tp_status=orders["take_profit"].status,
            sl_status=orders["stop_loss"].status,
            symbol=orders["parent"].symbol,
            tif="GTC",
        )
        print()
    finally:
        await trader.close()


if __name__ == "__main__":
    asyncio.run(main())
