from trader.adapters.base import Adapter
from trader.config import Config

def get_adapter(broker: str, config: Config) -> Adapter:
    if broker == "ibkr-rest":
        from trader.adapters.ibkr_rest.adapter import IBKRRestAdapter
        return IBKRRestAdapter(config)
    elif broker == "ibkr-tws":
        from trader.adapters.ibkr_tws.adapter import IBKRTWSAdapter
        return IBKRTWSAdapter(config)
    else:
        raise ValueError(f"Unknown broker '{broker}'. Choose: ibkr-rest, ibkr-tws")
