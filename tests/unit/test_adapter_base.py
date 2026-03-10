from trader.adapters.base import Adapter
import inspect

def test_adapter_is_abstract():
    assert inspect.isabstract(Adapter)

def test_adapter_has_required_methods():
    required = [
        "connect", "disconnect", "get_account", "get_quotes",
        "get_option_chain", "place_order", "modify_order",
        "cancel_order", "list_orders", "list_positions",
        "close_position", "get_news",
    ]
    for method in required:
        assert hasattr(Adapter, method), f"Missing: {method}"
