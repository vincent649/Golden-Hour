import httpx
import pytest

from app import engine
from app.main import model, sim
from app.routing import AMBULANCE_SPEED_FACTOR, OsrmRouter, ResilientRouter, SyntheticRouter

CENTRAL = {"lat": 22.566, "lng": 88.381}  # right next to the small "Nursing Home Central"


def post_incident(client, **kw):
    body = {**CENTRAL, "source": "operator", **kw}
    r = client.post("/api/incidents", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_health_and_state(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["routing"]["mode"] == "synthetic"
    s = client.get("/api/state").json()
    assert len(s["ambulances"]) == 18 and len(s["hospitals"]) == 8
    assert sum(a["status"] == "busy" for a in s["ambulances"]) == 3


def test_severity_model_quality_and_direction():
    assert model.holdout_accuracy > 0.7
    risky = model.predict("national_highway", "truck_bus", 100, 2, 4)
    safe = model.predict("local_street", "car", 30, 14, 1)
    assert risky["probabilities"]["critical"] > safe["probabilities"]["critical"]
    assert safe["severity"] == "minor"
    assert abs(sum(risky["probabilities"].values()) - 1) < 0.01


def test_full_incident_flow(client):
    inc = post_incident(client, severity_override="critical")
    assert inc["status"] == "dispatched"
    assert inc["ambulance"]["route"]["coords"] and inc["hospital"]["route"]["coords"]
    tl = inc["timeline"]
    assert tl["total_s"] == pytest.approx(tl["ambulance_eta_s"] + tl["scene_time_s"] + tl["transport_s"], abs=0.5)
    assert tl["golden_hour_ok"] == (tl["total_s"] <= 3600)
    assert inc["pre_alert"]["hospital_id"] == inc["hospital"]["id"]
    assert "Activate trauma team" in inc["pre_alert"]["prepare"]
    # resources reserved
    assert sim.amb(inc["ambulance"]["id"])["status"] == "busy"
    h = sim.hosp(inc["hospital"]["id"])
    assert h["beds_available"] == h["beds_total"] - 1


def test_chosen_ambulance_is_best_ranked_and_available(client):
    busy_before = {a["id"] for a in sim.ambulances if a["status"] == "busy"}
    inc = post_incident(client, severity_override="serious")
    assert inc["ambulance"]["id"] not in busy_before
    alts = inc["ambulance"]["alternatives"]
    # chosen unit scores no worse than any alternative
    assert all(a["score_s"] >= inc["ambulance"]["eta_s"] - 1 for a in alts)


def test_critical_patient_prefers_als_over_volunteer_auto(client):
    for _ in range(4):
        inc = post_incident(client, severity_override="critical")
        assert inc["ambulance"]["provider"] != "volunteer"
        assert inc["ambulance"]["type"] == "ALS" or inc["ambulance"]["provider"] != "volunteer"
    assert engine.unit_penalty_s("critical", {"type": "BLS", "provider": "volunteer"})[0] > \
        engine.unit_penalty_s("critical", {"type": "BLS", "provider": "private"})[0] > \
        engine.unit_penalty_s("critical", {"type": "ALS", "provider": "private"})[0] == 0
    assert engine.unit_penalty_s("minor", {"type": "BLS", "provider": "volunteer"})[0] == 0


def test_critical_patient_gets_capable_hospital_not_nearest_clinic(client):
    inc = post_incident(client, severity_override="critical")
    hosp = inc["hospital"]
    assert {"Trauma team", "CT scan", "Neurosurgery", "Blood bank"} <= set(hosp["capabilities"])
    nearest = hosp["nearest"]
    assert nearest["rejected"] is True and nearest["rejected_reason"]
    assert nearest["trauma_level"] == 3


def test_minor_patient_can_use_nearest(client):
    inc = post_incident(client, severity_override="minor")
    assert inc["hospital"]["nearest"]["rejected"] is False


def test_no_beds_forces_next_hospital(client):
    first = post_incident(client, severity_override="critical")["hospital"]["id"]
    sim.hosp(first)["beds_available"] = 0
    second = post_incident(client, severity_override="critical")["hospital"]["id"]
    assert second != first


def test_unserved_when_no_ambulance(client):
    for a in sim.ambulances:
        a["status"] = "busy"
    inc = post_incident(client)
    assert inc["status"] == "unserved" and inc["ambulance"] is None
    assert any("ambulance" in w.lower() for w in inc["warnings"])


def test_outside_area_rejected(client):
    r = client.post("/api/incidents", json={"lat": 28.6, "lng": 77.2})
    assert r.status_code == 422


def test_bad_inputs_rejected(client):
    r = client.post("/api/incidents", json={**CENTRAL, "details": {"vehicle": "spaceship"}})
    assert r.status_code == 422
    r = client.post("/api/incidents", json={**CENTRAL, "severity_override": "doomed"})
    assert r.status_code == 422


def test_defaults_are_labelled_as_assumed(client):
    inc = post_incident(client, source="bystander")
    assert inc["severity"]["source"] == "assumed details"
    inc2 = post_incident(client, details={"vehicle": "two_wheeler", "road_type": "state_highway", "speed_zone": 80, "people": 2})
    assert inc2["severity"]["source"] == "model"


def test_resolve_frees_ambulance_and_updates_registry(client):
    inc = post_incident(client)
    amb_id = inc["ambulance"]["id"]
    r = client.post(f"/api/incidents/{inc['id']}/resolve", json={"outcome": "delivered_to_hospital"})
    assert r.status_code == 200 and r.json()["status"] == "resolved"
    amb = sim.amb(amb_id)
    hosp = sim.hosp(inc["hospital"]["id"])
    assert amb["status"] == "available" and (amb["lat"], amb["lng"]) == (hosp["lat"], hosp["lng"])
    reg = client.get("/api/registry").json()
    assert reg["summary"]["total"] == 1 and reg["rows"][0]["outcome"] == "delivered_to_hospital"
    assert client.post("/api/incidents/NOPE/resolve", json={"outcome": "treated_at_scene"}).status_code == 404


def test_cancel_releases_bed(client):
    inc = post_incident(client)
    h = sim.hosp(inc["hospital"]["id"])
    assert h["beds_available"] == h["beds_total"] - 1
    client.post(f"/api/incidents/{inc['id']}/resolve", json={"outcome": "cancelled_false_alarm"})
    assert h["beds_available"] == h["beds_total"]


def test_registry_csv(client):
    post_incident(client)
    r = client.get("/api/registry.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    assert lines[0].startswith("incident_id") and len(lines) == 2


def test_hotspots(client):
    d = client.get("/api/hotspots").json()
    assert len(d["hotspots"]) >= 4 and 1 <= len(d["stations"]) <= 3
    m = d["metrics"]
    assert m["avg_eta_after_min"] <= m["avg_eta_before_min"] and m["improvement_pct"] >= 0


def test_first_aid_languages(client):
    for lang in ("en", "hi", "bn"):
        g = client.get(f"/api/first-aid?lang={lang}").json()
        assert g["lang"] == lang and len(g["steps"]) == 7 and g["legal"] and g["clinically_reviewed"] is False
    assert client.get("/api/first-aid?lang=xx").json()["lang"] == "en"


def test_reset(client):
    post_incident(client)
    client.post("/api/reset")
    assert client.get("/api/incidents").json() == []
    assert all(h["beds_available"] == h["beds_total"] for h in sim.hospitals)


# ---------- routers ----------
def test_synthetic_router_is_symmetric_and_positive():
    r = SyntheticRouter()
    a, b = (22.51, 88.35), (22.60, 88.42)
    ab = r.matrix([a], [b])[0][0]
    ba = r.matrix([b], [a])[0][0]
    assert ab > 0 and ab == pytest.approx(ba, rel=0.01)
    route = r.route(a, b)
    assert route["duration_s"] == pytest.approx(ab, rel=0.01)
    assert route["coords"][0] == [a[0], a[1]] and route["coords"][-1] == [b[0], b[1]]


def _osrm_with(handler):
    r = OsrmRouter("http://osrm.test")
    r.client = httpx.Client(transport=httpx.MockTransport(handler))
    return r


def test_osrm_router_parses_responses():
    def handler(req: httpx.Request):
        if "/table/" in req.url.path:
            return httpx.Response(200, json={"code": "Ok", "durations": [[100.0, None], [200.0, 300.0]]})
        return httpx.Response(200, json={"code": "Ok", "routes": [{
            "duration": 120.0, "distance": 1500.0,
            "geometry": {"coordinates": [[88.36, 22.57], [88.37, 22.58]]}}]})

    r = _osrm_with(handler)
    m = r.matrix([(22.5, 88.3), (22.6, 88.4)], [(22.55, 88.35), (22.56, 88.36)])
    assert m[0][0] == pytest.approx(100 * AMBULANCE_SPEED_FACTOR) and m[0][1] is None
    rt = r.route((22.57, 88.36), (22.58, 88.37))
    assert rt["coords"] == [[22.57, 88.36], [22.58, 88.37]]  # flipped to lat,lng
    assert rt["duration_s"] == pytest.approx(120 * AMBULANCE_SPEED_FACTOR)


def test_resilient_router_falls_back_and_stays():
    def boom(req):
        raise httpx.ConnectError("no network")

    rr = ResilientRouter(_osrm_with(boom), SyntheticRouter())
    assert rr.mode == "osrm"
    out = rr.matrix([(22.51, 88.35)], [(22.60, 88.42)])
    assert out[0][0] > 0 and rr.degraded and rr.mode == "synthetic" and "ConnectError" in rr.last_error


def test_engine_constants_consistent():
    assert set(engine.REQUIRED_CAPS) == {"minor", "serious", "critical"}
