import pytest

def test_tws_adapter_importable_without_ib_insync():
    """The tws adapter must not crash on import even if ib_insync is not installed."""
    try:
        from trader.adapters.ibkr_tws.adapter import IBKRTWSAdapter
        assert IBKRTWSAdapter is not None
    except ImportError as e:
        if "ib_insync" in str(e):
            pytest.skip("ib_insync not installed — expected in CI")
        raise

def test_tws_adapter_is_adapter_subclass():
    from trader.adapters.ibkr_tws.adapter import IBKRTWSAdapter
    from trader.adapters.base import Adapter
    assert issubclass(IBKRTWSAdapter, Adapter)
