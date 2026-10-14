import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from aquasentinel import config
from aquasentinel.main import app


@pytest.fixture
def gated(monkeypatch):
    monkeypatch.setattr(config, "APP_PASSWORD", "secret")
    monkeypatch.setattr(config, "APP_USERNAME", "aquasentinel")
    with TestClient(app) as c:
        yield c


def test_gate_asks_for_login(gated):
    r = gated.get("/api/state")
    assert r.status_code == 401 and "Basic" in r.headers["www-authenticate"]
    assert gated.get("/api/state", auth=("aquasentinel", "wrong")).status_code == 401


def test_login_sets_cookie_that_also_opens_the_websocket(gated):
    r = gated.get("/api/state", auth=("aquasentinel", "secret"))
    assert r.status_code == 200 and "aquasentinel_auth" in r.headers["set-cookie"]
    assert gated.get("/api/state").status_code == 200          # cookie alone
    with gated.websocket_connect("/ws/live"):
        pass


def test_websocket_without_login_is_refused(gated):
    gated.cookies.clear()
    with pytest.raises(WebSocketDisconnect):
        with gated.websocket_connect("/ws/live") as ws:
            ws.receive_text()


def test_boat_endpoints_use_their_own_key(gated, monkeypatch):
    monkeypatch.setattr(config, "INGEST_API_KEY", "boatkey")
    assert gated.get("/api/boat/waypoints", headers={"X-API-Key": "boatkey"}).status_code == 200
    assert gated.get("/api/boat/waypoints").status_code == 401
