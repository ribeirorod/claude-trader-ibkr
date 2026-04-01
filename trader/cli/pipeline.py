from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import click

from trader.adapters.factory import get_adapter
from trader.cli.__main__ import output_json
from trader.guard import OrderGuard
from trader.market.regime import detect_regime
from trader.models import OrderRequest
from trader.news.factory import get_news_provider
from trader.pipeline.analyze import run_analyze
from trader.pipeline.discover import run_discover
from trader.pipeline.models import ProposalSet

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent.parent


def _get_watchlist_path() -> Path:
    return _ROOT / ".trader" / "watchlists.json"


def _get_pipeline_dir() -> Path:
    return _ROOT / ".trader" / "pipeline"


@click.group()
def pipeline():
    """Pipeline commands: discover candidates and analyze trade proposals."""


@pipeline.command()
@click.option(
    "--regime",
    type=click.Choice(["bull", "caution", "bear"]),
    default=None,
    help="Market regime override. Auto-detected if omitted.",
)
@click.pass_context
def discover(ctx, regime: str | None):
    """Discover trade candidates via watchlists and market scans.

    \b
    Connects to the broker adapter for scanning, fetches news for
    enrichment, and writes candidates.json to the pipeline directory.
    """
    obj = ctx.find_root().obj or {}
    broker = obj.get("broker", "ibkr-rest")
    config = obj.get("config")

    if config is None:
        from trader.config import Config
        config = Config()

    pipeline_dir = _get_pipeline_dir()

    # Auto-detect regime if not provided
    if regime is None:
        regime = detect_regime(cache_dir=pipeline_dir).value

    adapter = get_adapter(broker, config)
    news_provider = get_news_provider(config)

    watchlist_path = _get_watchlist_path()

    async def _run():
        await adapter.connect()
        try:
            result = await run_discover(
                regime=regime,
                watchlist_path=watchlist_path,
                pipeline_dir=pipeline_dir,
                scan_fn=adapter.scan,
                news_fn=news_provider.get_news,
            )
            return result
        finally:
            await adapter.disconnect()
            await news_provider.aclose()

    result = asyncio.run(_run())
    output_json(result)


@pipeline.command()
@click.option(
    "--regime",
    type=click.Choice(["bull", "caution", "bear"]),
    default=None,
    help="Market regime override. Auto-detected if omitted.",
)
@click.option(
    "--consensus",
    type=int,
    default=3,
    show_default=True,
    help="Minimum strategy consensus for discovery candidates.",
)
@click.option(
    "--watchlist-consensus",
    type=int,
    default=2,
    show_default=True,
    help="Minimum strategy consensus for watchlist candidates.",
)
@click.pass_context
def analyze(ctx, regime: str | None, consensus: int, watchlist_consensus: int):
    """Analyze discovered candidates and produce ranked trade proposals.

    \b
    Reads candidates.json from the pipeline directory, fetches account
    state from the broker, runs multi-strategy analysis, and writes
    proposals.json.
    """
    obj = ctx.find_root().obj or {}
    broker = obj.get("broker", "ibkr-rest")
    config = obj.get("config")

    if config is None:
        from trader.config import Config
        config = Config()

    pipeline_dir = _get_pipeline_dir()
    candidates_path = pipeline_dir / "candidates.json"

    if not candidates_path.exists():
        raise click.ClickException(
            f"candidates.json not found in {pipeline_dir}. Run 'trader pipeline discover' first."
        )

    # Auto-detect regime if not provided
    if regime is None:
        regime = detect_regime(cache_dir=pipeline_dir).value

    adapter = get_adapter(broker, config)

    async def _run():
        await adapter.connect()
        try:
            account = await adapter.get_account()
            positions = await adapter.list_positions()
            orders = await adapter.list_orders()

            account_value = account.balance.net_liquidation

            result = run_analyze(
                pipeline_dir=pipeline_dir,
                regime=regime,
                account_value=account_value,
                existing_positions=positions,
                open_orders=orders,
                consensus_threshold=consensus,
                watchlist_consensus_threshold=watchlist_consensus,
            )

            return result
        finally:
            await adapter.disconnect()

    result = asyncio.run(_run())
    output_json(result)


@pipeline.command()
@click.option(
    "--max-orders",
    type=int,
    default=5,
    show_default=True,
    help="Maximum number of proposals to execute in one run.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what would be placed without sending orders.",
)
@click.pass_context
def execute(ctx, max_orders: int, dry_run: bool):
    """Execute trade proposals from proposals.json.

    \b
    Reads proposals.json, converts each proposal into an order request,
    and places orders via the broker adapter. Supports bracket orders
    (with stop-loss + take-profit), limit orders, and options.

    Every order is validated by OrderGuard before placement. Orders that
    fail guard checks are skipped with status="guarded".

    Examples:
      trader pipeline execute
      trader pipeline execute --max-orders 3
      trader pipeline execute --dry-run
    """
    obj = ctx.find_root().obj or {}
    broker = obj.get("broker", "ibkr-rest")
    config = obj.get("config")

    if config is None:
        from trader.config import Config
        config = Config()

    pipeline_dir = _get_pipeline_dir()
    proposals_path = pipeline_dir / "proposals.json"

    if not proposals_path.exists():
        raise click.ClickException(
            f"proposals.json not found in {pipeline_dir}. Run 'trader pipeline analyze' first."
        )

    proposal_set = ProposalSet.model_validate_json(proposals_path.read_text())
    all_proposals = [
        p for sp in proposal_set.sectors.values() for p in sp.proposals
    ]
    all_proposals.sort(key=lambda p: p.rank)

    to_execute = all_proposals[:max_orders]

    if not to_execute:
        output_json({"status": "no_proposals", "message": "No proposals to execute"})
        return

    adapter = get_adapter(broker, config)
    guard = OrderGuard()

    async def _run():
        await adapter.connect()
        try:
            # Fetch account state for guard validation
            account = await adapter.get_account()
            positions = await adapter.list_positions()
            open_orders = await adapter.list_orders()

            results = []
            for p in to_execute:
                strike = p.order.strike
                expiry = p.order.expiry
                right = p.order.right

                # Validate option strikes against the real chain
                if p.order.contract_type == "option" and strike and expiry and right:
                    valid_strike = await adapter.validate_option_strike(
                        p.ticker, expiry, strike, right
                    )
                    if valid_strike is None:
                        results.append({
                            "ticker": p.ticker,
                            "direction": p.direction,
                            "status": "skipped",
                            "reason": f"no options chain for {p.ticker} {expiry}",
                        })
                        continue
                    if valid_strike != strike:
                        logger.info(
                            "%s: snapped strike %.2f → %.2f",
                            p.ticker, strike, valid_strike,
                        )
                    strike = valid_strike

                order_req = OrderRequest(
                    ticker=p.ticker,
                    qty=p.order.qty,
                    side=p.order.side,
                    order_type=p.order.order_type,
                    price=p.order.price,
                    stop_loss=p.order.stop_loss,
                    take_profit=p.order.take_profit,
                    contract_type=p.order.contract_type,
                    expiry=expiry,
                    strike=strike,
                    right=right,
                )

                # OrderGuard validation before placement
                guard_result = guard.validate(
                    order=order_req,
                    account=account,
                    positions=positions,
                    open_orders=open_orders,
                )
                if not guard_result.allowed:
                    logger.warning(
                        "%s: order blocked by guard — %s",
                        p.ticker, guard_result.reason,
                    )
                    results.append({
                        "ticker": p.ticker,
                        "direction": p.direction,
                        "status": "guarded",
                        "reason": guard_result.reason,
                        "details": guard_result.details,
                    })
                    continue

                if dry_run:
                    results.append({
                        "ticker": p.ticker,
                        "direction": p.direction,
                        "order": order_req.model_dump(exclude_none=True),
                        "sizing": p.sizing.model_dump() if p.sizing else {},
                        "status": "dry_run",
                    })
                else:
                    try:
                        resp = await adapter.place_order(order_req)
                        results.append({
                            "ticker": p.ticker,
                            "direction": p.direction,
                            "status": "placed",
                            "order_response": resp if isinstance(resp, dict) else resp.model_dump() if hasattr(resp, "model_dump") else str(resp),
                        })
                    except Exception as exc:
                        results.append({
                            "ticker": p.ticker,
                            "direction": p.direction,
                            "status": "error",
                            "error": str(exc),
                        })

            return {
                "executed": len([r for r in results if r["status"] == "placed"]),
                "guarded": len([r for r in results if r["status"] == "guarded"]),
                "errors": len([r for r in results if r["status"] == "error"]),
                "dry_run": dry_run,
                "results": results,
            }
        finally:
            await adapter.disconnect()

    result = asyncio.run(_run())
    output_json(result)


@pipeline.command()
@click.option("--regime", type=click.Choice(["bull", "caution", "bear"]), default=None,
              help="Market regime override. Auto-detected if omitted.")
@click.option("--consensus", type=int, default=3, show_default=True,
              help="Minimum strategy consensus for discovery candidates.")
@click.option("--watchlist-consensus", type=int, default=2, show_default=True,
              help="Minimum strategy consensus for watchlist candidates.")
@click.option("--max-orders", type=int, default=5, show_default=True,
              help="Maximum number of proposals to execute.")
@click.option("--dry", "dry_run", is_flag=True, default=False,
              help="Run discover + analyze only, skip execution.")
@click.pass_context
def run(ctx, regime, consensus, watchlist_consensus, max_orders, dry_run):
    """Run the full pipeline: discover -> analyze -> execute.

    \b
    With --dry, stops after analyze (review proposals before acting).

    Examples:
      trader pipeline run                    # full auto
      trader pipeline run --dry              # discover + analyze only
      trader pipeline run --regime bear      # force bear regime
    """
    # Step 1: Invoke discover
    ctx.invoke(discover, regime=regime)

    # Read the regime that discover resolved (from candidates.json)
    pipeline_dir = _get_pipeline_dir()
    candidates_path = pipeline_dir / "candidates.json"
    if candidates_path.exists():
        cs_data = json.loads(candidates_path.read_text())
        resolved_regime = cs_data.get("regime", regime)
    else:
        resolved_regime = regime

    # Step 2: Invoke analyze with resolved regime
    ctx.invoke(analyze, regime=resolved_regime, consensus=consensus,
               watchlist_consensus=watchlist_consensus)

    if dry_run:
        return

    # Step 3: Invoke execute
    ctx.invoke(execute, max_orders=max_orders, dry_run=False)
