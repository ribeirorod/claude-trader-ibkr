"""
Simple Integration Test - Volatility + VIBE Trader

This script demonstrates the basic integration between Volatility strategies
and VIBE Trader execution using IBKR data.

Usage:
    python examples/simple_integration_test.py
"""

import sys
from pathlib import Path

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from dotenv import load_dotenv
import structlog

# Import from vibe trader
from vibe import Trader

# Import from volatility integration modules - bypass composer __init__ to avoid import errors
volatility_path = Path(__file__).parent.parent / "volatility"
sys.path.insert(0, str(volatility_path))

# Direct imports to avoid composer.__init__ issues
import importlib.util

# Import IBKRDataFetcher
spec = importlib.util.spec_from_file_location(
    "ibkr_data_fetcher",
    volatility_path / "composer" / "core" / "ibkr_data_fetcher.py"
)
ibkr_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ibkr_module)
IBKRDataFetcher = ibkr_module.IBKRDataFetcher

# Import VibeTraderAdapter
spec = importlib.util.spec_from_file_location(
    "vibe_adapter",
    volatility_path / "composer" / "tools" / "vibe_adapter.py"
)
adapter_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter_module)
VibeTraderAdapter = adapter_module.VibeTraderAdapter


log = structlog.get_logger()


def _bold_event(_, __, event_dict):
    """Make event names bold in console output."""
    evt = event_dict.get("event")
    if evt:
        event_dict["event"] = f"\x1b[1m{evt}\x1b[0m"
    return event_dict


async def test_data_fetching():
    """Test 1: Fetch historical data from IBKR."""
    log.info("test_started", test="Data Fetching from IBKR", test_number=1)
    
    fetcher = IBKRDataFetcher()
    log.info("ibkr_connection", client_id=fetcher.client_id, purpose="data_fetching")
    
    try:
        log.info("fetching_data", symbol="AAPL", period="2024-01-01 to now", interval="1d")
        df = await fetcher.fetch_data_async('AAPL', start_date='2024-01-01', interval='1d')
        
        if not df.empty:
            log.info(
                "data_fetched_success",
                rows=len(df),
                columns=list(df.columns),
                date_range=f"{df.index[0]} to {df.index[-1]}"
            )
            print(f"\nData preview:")
            print(df.head())
            print()
            return True
        else:
            log.error("data_fetch_failed", reason="No data returned")
            return False
            
    except Exception as e:
        log.error("data_fetch_error", error=str(e), error_type=type(e).__name__)
        return False
    finally:
        await fetcher.close()


async def test_signal_execution():
    """Test 2: Execute a simple buy signal."""
    log.info("test_started", test="Signal Execution via VIBE Trader", test_number=2)
    
    adapter = VibeTraderAdapter()
    log.info("ibkr_connection", client_id=adapter.client_id, purpose="order_execution")
    
    try:
        log.info("executing_signal", ticker="AAPL", signal="BUY", quantity=1, order_type="market")
        result = await adapter.execute_signal(
            ticker='AAPL',
            signal=1,  # Buy
            quantity=1,
            order_type='market'
        )
        
        if result:
            log.info(
                "order_placed_success",
                order_id=result.order_id,
                status=result.status,
                symbol=result.symbol,
                quantity=result.quantity,
                fill_price=result.avg_fill_price
            )
            return True
        else:
            log.error("order_placement_failed", reason="No result returned")
            return False
            
    except Exception as e:
        log.error("order_execution_error", error=str(e), error_type=type(e).__name__)
        return False
    finally:
        await adapter.close()


async def test_position_tracking():
    """Test 3: Check position tracking."""
    log.info("test_started", test="Position Tracking", test_number=3)
    
    adapter = VibeTraderAdapter()
    log.info("ibkr_connection", client_id=adapter.client_id, purpose="position_tracking")
    
    try:
        log.info("fetching_positions", source="adapter_tracker")
        positions = await adapter.get_positions()
        
        if positions:
            log.info("positions_found", count=len(positions))
            for ticker, pos in positions.items():
                log.info(
                    "position_detail",
                    ticker=ticker,
                    quantity=pos.get('quantity'),
                    entry_price=pos.get('entry_price', 0),
                    entry_time=pos.get('entry_time')
                )
        else:
            log.info("no_positions_tracked")
        
        log.info("fetching_open_orders", source="ibkr")
        orders = await adapter.get_open_orders()
        
        if orders:
            log.info("open_orders_found", count=len(orders))
            for order in orders:
                log.info(
                    "order_detail",
                    symbol=order.symbol,
                    order_id=order.order_id,
                    side=order.side,
                    quantity=order.quantity,
                    status=order.status
                )
        else:
            log.info("no_open_orders")
        
        return True
        
    except Exception as e:
        log.error("position_tracking_error", error=str(e), error_type=type(e).__name__)
        return False
    finally:
        await adapter.close()


async def test_full_workflow():
    """Test 4: Full workflow - Fetch data, generate signal, execute."""
    log.info("test_started", test="Full Workflow (Data → Signal → Execution)", test_number=4)
    
    fetcher = IBKRDataFetcher()
    adapter = VibeTraderAdapter()
    log.info("ibkr_connections", fetcher_client_id=fetcher.client_id, adapter_client_id=adapter.client_id)
    
    try:
        # Step 1: Fetch data
        log.info("workflow_step", step=1, action="Fetching AAPL data")
        df = await fetcher.fetch_data_async('AAPL', start_date='2024-01-01', interval='1d')
        
        if df.empty:
            log.error("workflow_failed", step=1, reason="No data fetched")
            return False
        
        log.info("data_fetched", rows=len(df))
        
        # Step 2: Simple signal logic (for demonstration)
        log.info("workflow_step", step=2, action="Generating signal")
        
        if len(df) >= 20:
            last_close = df['Close'].iloc[-1]
            avg_20 = df['Close'].tail(20).mean()
            
            log.info(
                "signal_calculation",
                last_close=f"${last_close:.2f}",
                avg_20=f"${avg_20:.2f}",
                strategy="20-day moving average"
            )
            
            if last_close > avg_20:
                signal = 1  # Buy
                log.info("signal_generated", signal="BUY", reason="price above 20-day average")
            else:
                signal = 0  # Hold
                log.info("signal_generated", signal="HOLD", reason="price below 20-day average")
        else:
            signal = 0
            log.info("signal_generated", signal="HOLD", reason="insufficient data")
        
        # Step 3: Execute signal
        log.info("workflow_step", step=3, action="Executing signal")
        
        if signal == 1:
            result = await adapter.execute_signal(
                ticker='AAPL',
                signal=signal,
                quantity=1,
                order_type='market'
            )
            
            if result:
                log.info("workflow_complete", order_id=result.order_id, status=result.status)
                return True
            else:
                log.error("workflow_failed", step=3, reason="Order execution failed")
                return False
        else:
            log.info("workflow_complete", action="No execution needed", signal="HOLD")
            return True
            
    except Exception as e:
        log.error("workflow_error", error=str(e), error_type=type(e).__name__)
        return False
    finally:
        await fetcher.close()
        await adapter.close()


async def main():
    """Run all integration tests."""
    load_dotenv()
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _bold_event,
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    )
    
    print("\n" + "=" * 60)
    print("VOLATILITY + VIBE TRADER INTEGRATION TESTS")
    print("=" * 60)
    print("\nThese tests verify the integration between:")
    print("  - Volatility (Strategy Engine)")
    print("  - VIBE Trader (Execution Engine)")
    print("  - IBKR (Data & Broker)")
    print("\n⚠️  WARNING: These tests will place REAL orders on your IBKR account!")
    print("   Make sure you're connected to PAPER TRADING account.")
    
    input("\nPress ENTER to continue or Ctrl+C to cancel...")
    print()
    
    log.info("test_suite_started", total_tests=4)
    
    results = []
    
    # Run tests
    results.append(("Data Fetching", await test_data_fetching()))
    results.append(("Signal Execution", await test_signal_execution()))
    results.append(("Position Tracking", await test_position_tracking()))
    results.append(("Full Workflow", await test_full_workflow()))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name:.<40} {status}")
    
    total = len(results)
    passed_count = sum(1 for _, p in results if p)
    
    print(f"\nTotal: {passed_count}/{total} tests passed")
    
    if passed_count == total:
        print("\n🎉 All tests passed! Integration is working correctly.")
        log.info("test_suite_complete", status="success", passed=passed_count, total=total)
    else:
        print("\n⚠️  Some tests failed. Check the output above for details.")
        log.warning("test_suite_complete", status="partial_failure", passed=passed_count, total=total, failed=total-passed_count)


if __name__ == '__main__':
    asyncio.run(main())
