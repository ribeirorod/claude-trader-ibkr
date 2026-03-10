import os, pytest
from trader.config import Config

def test_config_defaults(monkeypatch):
    monkeypatch.delenv("IB_PORT", raising=False)
    monkeypatch.delenv("DEFAULT_BROKER", raising=False)
    monkeypatch.delenv("MAX_POSITION_PCT", raising=False)
    c = Config()
    assert c.ib_port == 5000
    assert c.default_broker == "ibkr-rest"
    assert c.max_position_pct == 0.05

def test_config_from_env(monkeypatch):
    monkeypatch.setenv("IB_PORT", "7497")
    monkeypatch.setenv("BENZINGA_API_KEY", "testkey")
    c = Config()
    assert c.ib_port == 7497
    assert c.benzinga_api_key == "testkey"
