"""First alert, impact figures, farmer brief and the voice socket, all without a model: no key is set in tests."""
import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from aquasentinel import main
from aquasentinel.agents import edge


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


def _anomaly(hub, zone="SW"):
    return hub.store.insert("anomalies", started=time.time(), zone=zone, lat=11.0, lon=77.0, params=["ph", "ec"],
                            peak={"ph": 9.4, "ec": 1900}, baseline={"ph": 7.6, "ec": 420}, status="open")


def test_first_alert_falls_back_to_the_rule(client):
    hub = main.hub
    aid = _anomaly(hub)
    asyncio.run(hub._first_alert(aid))
    alert = hub.store.get("anomalies", aid)["edge_alert"]
    assert alert["by"] == "rule" and alert["model"] is None and alert["seconds"] >= 0
    assert "SW" in alert["title"] and "pH" in alert["body"]
    assert [c["direction"] for c in alert["facts"]["changes"]] == ["up", "up"]


def test_gemma_reply_parsing():
    assert edge._parse("**TITLE:** Water change\nBODY: One. Two.") == ("Water change", "One. Two.")
    assert edge._parse("Water change\nOne.\nTwo.") == ("Water change", "One. Two.")
    with pytest.raises(ValueError):
        edge._parse("only one line")


def test_impact_reports_measured_times_only(client):
    hub = main.hub
    aid = _anomaly(hub)
    asyncio.run(hub._first_alert(aid))
    d = client.get("/api/impact").json()
    assert {"readings", "readings_per_hour", "speed_scale", "events", "median"} <= d.keys()
    ev = next(e for e in d["events"] if e["anomaly_id"] == aid)
    assert ev["first_alert_by"] == "rule" and ev["first_alert_s"] is not None
    assert ev["source_s"] is None and ev["diagnosis_s"] is None          # not traced, not diagnosed: nothing is made up


def test_farmer_brief_without_gemini(client):
    r = client.get("/api/farmer", params={"zone": "SW", "lang": "ta"})
    assert r.status_code == 200 and r.json()["brief"] is None and r.json()["language"] == "ta"
    assert client.get("/api/farmer", params={"zone": "Atlantis"}).status_code == 404
    facts = main.hub.farmer_facts("SW")
    assert facts["zone"] == "SW" and facts["data_is_simulated"] is True


def test_voice_socket_says_when_not_configured(client):
    with client.websocket_connect("/ws/voice") as ws:
        msg = ws.receive_json()
    assert msg["type"] == "error" and "GEMINI_LIVE_MODEL" in msg["message"]


def test_edge_alert_column_survives_reset(client):
    hub = main.hub
    asyncio.run(hub.reset())
    aid = _anomaly(hub)
    hub.store.update("anomalies", aid, edge_alert={"by": "rule", "title": "t"})
    assert hub.store.get("anomalies", aid)["edge_alert"]["by"] == "rule"
