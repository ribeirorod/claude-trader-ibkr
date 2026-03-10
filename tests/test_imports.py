"""Quick import validation test - no IBKR connection needed."""
import sys

def test_imports():
    print("Testing imports...")
    
    try:
        from vibe import Trader, Scheduler
        print("✓ vibe.Trader imported")
        print("✓ vibe.Scheduler imported")
    except Exception as e:
        print(f"✗ Failed to import vibe: {e}")
        return False
    
    try:
        from vibe.models import OrderResponse, OrderStatus, Side, OrderType
        print("✓ vibe.models imported")
    except Exception as e:
        print(f"✗ Failed to import models: {e}")
        return False
    
    try:
        from vibe.utils import retry_async, TTLIdempotencyMap, normalize_symbol_ibkr
        print("✓ vibe.utils imported")
    except Exception as e:
        print(f"✗ Failed to import utils: {e}")
        return False
    
    try:
        from vibe.venues.ibkr import IBKRAdapter
        print("✓ vibe.venues.ibkr imported")
    except Exception as e:
        print(f"✗ Failed to import IBKR adapter: {e}")
        return False
    
    print("\nAll imports successful! Ready to test with IBKR credentials.")
    return True

if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)
