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
        providers = await t.news_providers()
        log.info("news_providers", count=len(providers), providers=providers[:5])
        print()

        # Get historical headlines for AAPL in a recent window
        heads = await t.news_history(
            "AAPL",
            start="2025-10-01 00:00:00",
            end="2025-10-30 23:59:59",
            limit=5,
        )
        log.info("news_headlines", count=len(heads), sample=heads[:3])
        print()

        if heads:
            art = await t.news_article(provider_code=heads[0]["provider_code"], article_id=heads[0]["article_id"])
            snippet = (art.get("text") or "")[:300]
            log.info("news_article", provider=heads[0]["provider_code"], article_id=heads[0]["article_id"], snippet=snippet)
            print()

        # Optional: subscribe to bulletins for 10 seconds
        def on_bulletin(b):
            log.info("news_bulletin", **b)
        await t.subscribe_news_bulletins(all_messages=False, on_bulletin=on_bulletin)
        await asyncio.sleep(10)
        await t.unsubscribe_news_bulletins()
        print()
    finally:
        await t.close()

if __name__ == "__main__":
    asyncio.run(main())
