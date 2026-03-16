import pytest
from fastapi.testclient import TestClient


def test_health_returns_ok():
    from trader.server.app import create_app
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_status_returns_scheduler_info(monkeypatch):
    import trader.server.app as app_module
    monkeypatch.setenv("IBKR_MODE", "paper")
    # Inject a fake scheduler state
    fake_scheduler = type("S", (), {"running": True, "get_jobs": lambda self: []})()
    from trader.server.app import create_app
    app = create_app(scheduler=fake_scheduler)
    client = TestClient(app)
    response = client.get("/status")
    assert response.status_code == 200
    data = response.json()
    assert data["scheduler"] == "running"
    assert data["ibkr_mode"] == "paper"
    assert "jobs" in data
