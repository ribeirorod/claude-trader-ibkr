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


async def main():
    load_dotenv()

    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _bold_event,
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    )

    t = Trader()
    try:
        o = await t.sell("AAPL", quantity=1, order_type="limit", limit_price=1000.0, tif="DAY")
        log.info("order_submitted", order_id=o.order_id, status=str(o.status), type=o.order_type, symbol=o.symbol)
        print()

        opens = await t.list_open_orders()
        log.info(
            "open_orders",
            count=len(opens),
            orders=[
                dict(id=oo.order_id, symbol=oo.symbol, type=oo.order_type, status=str(oo.status))
                for oo in opens
            ],
        )
        print()

        m = await t.modify_order(order_id=o.order_id, limit_price=999.0)
        log.info("order_modified", order_id=m.order_id, status=str(m.status), new_limit=999.0)
        print()

        await t.cancel(order_id=o.order_id)
        log.info("order_cancel_requested", order_id=o.order_id)
        print()
    finally:
        await t.close()


if __name__ == "__main__":
    asyncio.run(main())
