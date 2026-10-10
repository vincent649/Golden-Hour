"""Core logic: triage -> ambulance dispatch -> hospital matching -> pre-alert -> registry."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
from sklearn.cluster import DBSCAN

from .geo import haversine_m
from .simdata import Sim

IST = timezone(timedelta(hours=5, minutes=30))
SCENE_TIME_S = 300          # assumed time spent at the scene loading the patient
GOLDEN_HOUR_S = 3600

def unit_penalty_s(severity: str, amb: dict) -> tuple[int, str]:
    """Extra seconds added to a unit's ETA when its capability is a poor fit for the patient.

    Critical patients need advanced life support (ALS); volunteer ambulance autos carry
    no ALS equipment, so they are a last resort for serious and critical cases.
    """
    penalty, why = 0, ""
    if severity == "critical" and amb["type"] != "ALS":
        penalty += 420
        why = "no advanced life support"
    if amb["provider"] == "volunteer" and severity != "minor":
        penalty += 600 if severity == "critical" else 180
        why = (why + "; " if why else "") + "volunteer unit"
    return penalty, why

REQUIRED_CAPS = {
    "critical": ["Trauma team", "CT scan", "Neurosurgery", "Blood bank"],
    "serious": ["CT scan", "Blood bank"],
    "minor": ["Emergency department"],
}

LIKELY_INJURIES = {
    "two_wheeler": ["Head injury", "Limb fractures"],
    "pedestrian": ["Head injury", "Pelvic or limb injuries"],
    "truck_bus": ["Crush injuries", "Multiple trauma"],
    "car": ["Chest or abdominal injury", "Neck injury"],
}

DEFAULT_DETAILS = {"road_type": "urban_arterial", "vehicle": "car", "speed_zone": 50, "people": 1}


def now_iso() -> str:
    return datetime.now(IST).isoformat(timespec="seconds")


def local_hour() -> int:
    return datetime.now(IST).hour


# ---------------------------------------------------------------- dispatch
def rank_ambulances(sim: Sim, router, crash: tuple[float, float], severity: str) -> list[dict]:
    available = [a for a in sim.ambulances if a["status"] == "available"]
    if not available:
        return []
    etas = router.matrix([(a["lat"], a["lng"]) for a in available], [crash])
    ranked = []
    for a, row in zip(available, etas):
        eta = row[0]
        if eta is None:
            continue
        penalty, why = unit_penalty_s(severity, a)
        ranked.append({"id": a["id"], "name": a["name"], "type": a["type"], "provider": a["provider"],
                       "eta_s": round(eta, 1), "score_s": round(eta + penalty, 1), "penalty_note": why,
                       "straight_line_m": round(haversine_m(a["lat"], a["lng"], crash[0], crash[1]))})
    ranked.sort(key=lambda r: r["score_s"])
    return ranked


# ---------------------------------------------------------------- hospitals
def missing_caps(hospital: dict, severity: str) -> list[str]:
    return [c for c in REQUIRED_CAPS[severity] if c not in hospital["capabilities"]]


def match_hospital(sim: Sim, router, crash: tuple[float, float], severity: str) -> dict:
    hospitals = sim.hospitals
    etas = router.matrix([crash], [(h["lat"], h["lng"]) for h in hospitals])[0]
    rows = []
    for h, eta in zip(hospitals, etas):
        if eta is None:
            continue
        miss = missing_caps(h, severity)
        rows.append({"id": h["id"], "name": h["name"], "trauma_level": h["trauma_level"],
                     "eta_s": round(eta, 1), "beds_available": h["beds_available"],
                     "missing": miss, "eligible": not miss and h["beds_available"] > 0})
    if not rows:
        raise RuntimeError("No hospital is reachable from the crash location")
    rows.sort(key=lambda r: r["eta_s"])
    eligible = [r for r in rows if r["eligible"]]
    warning = None
    if eligible:
        chosen = eligible[0]
        reason = (f"Nearest hospital with {', '.join(REQUIRED_CAPS[severity])} and a free bed."
                  if severity != "minor" else "Nearest hospital with an emergency department and a free bed.")
    else:
        with_beds = [r for r in rows if r["beds_available"] > 0] or rows
        chosen = with_beds[0]
        reason = "No hospital meets every requirement; sending the nearest with a free bed."
        warning = "No suitable hospital available. Alert the control room."
    nearest = rows[0]
    nearest_note = None
    if nearest["id"] != chosen["id"]:
        if nearest["missing"]:
            nearest_note = f"Missing: {', '.join(nearest['missing'])}"
        elif nearest["beds_available"] <= 0:
            nearest_note = "No free beds"
    return {"chosen": chosen, "reason": reason, "warning": warning, "candidates": rows[:5],
            "nearest": {**nearest, "rejected": nearest["id"] != chosen["id"], "rejected_reason": nearest_note}}


# ---------------------------------------------------------------- pre-alert
def build_pre_alert(incident_id: str, hospital: dict, severity: str, details: dict,
                    eta_to_hospital_s: float, hospital_caps: list[str], issued_at: str) -> dict:
    prepare = []
    if severity == "critical":
        prepare.append("Activate trauma team")
    else:
        prepare.append("Emergency department team on standby")
    if "Blood bank" in hospital_caps and severity != "minor":
        prepare.append("Blood bank on standby")
    if "CT scan" in hospital_caps and severity != "minor":
        prepare.append("CT scan ready")
    elif "X-ray" in hospital_caps:
        prepare.append("X-ray ready")
    if "Neurosurgery" in hospital_caps and severity == "critical":
        prepare.append("Neurosurgeon on call")
    return {
        "incident_id": incident_id,
        "hospital_id": hospital["id"],
        "hospital_name": hospital["name"],
        "issued_at": issued_at,
        "severity": severity,
        "likely_injuries": LIKELY_INJURIES.get(details["vehicle"], []),
        "likely_injuries_note": "Indicative only, inferred from crash type. Not a clinical assessment.",
        "eta_minutes": round(eta_to_hospital_s / 60, 1),
        "prepare": prepare,
        "crash_summary": f"{details['vehicle'].replace('_', ' ')} on {details['road_type'].replace('_', ' ')}, "
                         f"{details['speed_zone']} km/h zone, {details['people']} involved",
    }


# ---------------------------------------------------------------- incidents
def create_incident(sim: Sim, router, model, store, *, lat: float, lng: float, source: str,
                    details: Optional[dict], severity_override: Optional[str]) -> dict:
    crash = (lat, lng)
    given = dict(details or {})
    used_defaults = not details
    d = {**DEFAULT_DETAILS, **{k: v for k, v in given.items() if v is not None}}
    d["hour"] = d.get("hour") if d.get("hour") is not None else local_hour()

    pred = model.predict(d["road_type"], d["vehicle"], d["speed_zone"], d["hour"], d["people"])
    if severity_override:
        severity = {"value": severity_override, "source": "operator",
                    "probabilities": pred["probabilities"], "confidence": None}
    else:
        severity = {"value": pred["severity"], "source": "assumed details" if used_defaults else "model",
                    "probabilities": pred["probabilities"], "confidence": pred["confidence"]}
    sev = severity["value"]

    incident_id = "INC-" + uuid.uuid4().hex[:6].upper()
    created_at = now_iso()
    incident = {
        "id": incident_id, "created_at": created_at, "status": "dispatched", "source": source,
        "location": {"lat": lat, "lng": lng}, "details": d, "severity": severity,
        "ambulance": None, "hospital": None, "timeline": None, "pre_alert": None,
        "warnings": [], "outcome": None, "resolved_at": None,
    }

    ranked = rank_ambulances(sim, router, crash, sev)
    if not ranked:
        incident["status"] = "unserved"
        incident["warnings"].append("No ambulance is available. Escalate to the control room.")
        incident["routing"] = {"mode": router.mode, "label": router.label}
        store.save(incident)
        return incident

    best = ranked[0]
    amb = sim.amb(best["id"])
    to_scene = router.route((amb["lat"], amb["lng"]), crash)
    straight = min(ranked, key=lambda r: r["straight_line_m"])

    hosp_match = match_hospital(sim, router, crash, sev)
    chosen = hosp_match["chosen"]
    hosp = sim.hosp(chosen["id"])
    to_hospital = router.route(crash, (hosp["lat"], hosp["lng"]))
    if hosp_match["warning"]:
        incident["warnings"].append(hosp_match["warning"])

    # Reserve the resources
    amb["status"] = "busy"
    if hosp["beds_available"] > 0:
        hosp["beds_available"] -= 1

    ambulance_eta = to_scene["duration_s"]
    transport = to_hospital["duration_s"]
    total = ambulance_eta + SCENE_TIME_S + transport
    incident["ambulance"] = {
        "id": amb["id"], "name": amb["name"], "type": amb["type"], "provider": amb["provider"],
        "eta_s": round(ambulance_eta, 1),
        "route": {"coords": to_scene["coords"], "distance_m": round(to_scene["distance_m"]),
                  "duration_s": round(to_scene["duration_s"], 1)},
        "alternatives": [r for r in ranked[1:4]],
        "straight_line_nearest": {"id": straight["id"], "name": straight["name"], "distance_m": straight["straight_line_m"],
                                  "differs_from_choice": straight["id"] != best["id"]},
        "reason": ("Advanced life support unit with the best score for a critical patient"
                   if sev == "critical" and amb["type"] == "ALS" else
                   "Shortest road travel time" if not best["penalty_note"] else
                   f"Best available option ({best['penalty_note']} adds delay in ranking)"),
    }
    incident["hospital"] = {
        "id": hosp["id"], "name": hosp["name"], "trauma_level": hosp["trauma_level"],
        "capabilities": hosp["capabilities"], "beds_available_after": hosp["beds_available"],
        "eta_from_scene_s": round(transport, 1),
        "route": {"coords": to_hospital["coords"], "distance_m": round(to_hospital["distance_m"]),
                  "duration_s": round(to_hospital["duration_s"], 1)},
        "reason": hosp_match["reason"], "candidates": hosp_match["candidates"],
        "nearest": hosp_match["nearest"],
    }
    incident["timeline"] = {
        "ambulance_eta_s": round(ambulance_eta, 1), "scene_time_s": SCENE_TIME_S,
        "transport_s": round(transport, 1), "total_s": round(total, 1),
        "golden_hour_s": GOLDEN_HOUR_S, "remaining_s": round(GOLDEN_HOUR_S - total, 1),
        "golden_hour_ok": total <= GOLDEN_HOUR_S,
        "assumptions": f"{SCENE_TIME_S // 60} min assumed at the scene; ambulance speed factor applied to road times.",
    }
    incident["pre_alert"] = build_pre_alert(incident_id, hosp, sev, d, ambulance_eta + SCENE_TIME_S + transport,
                                            hosp["capabilities"], created_at)
    incident["routing"] = {"mode": router.mode, "label": router.label}
    store.save(incident)
    return incident


def resolve_incident(sim: Sim, store, incident_id: str, outcome: str) -> Optional[dict]:
    inc = store.get(incident_id)
    if inc is None:
        return None
    if inc["status"] in ("resolved", "cancelled"):
        return inc
    amb = inc.get("ambulance")
    hosp = inc.get("hospital")
    if amb:
        a = sim.amb(amb["id"])
        a["status"] = "available"
        if outcome == "delivered_to_hospital" and hosp:
            h = sim.hosp(hosp["id"])
            a["lat"], a["lng"] = h["lat"], h["lng"]
        else:
            a["lat"], a["lng"] = inc["location"]["lat"], inc["location"]["lng"]
    if hosp and outcome == "cancelled_false_alarm":
        h = sim.hosp(hosp["id"])
        h["beds_available"] = min(h["beds_total"], h["beds_available"] + 1)
    inc["status"] = "cancelled" if outcome == "cancelled_false_alarm" else "resolved"
    inc["outcome"] = outcome
    inc["resolved_at"] = now_iso()
    store.save(inc)
    return inc


def registry_row(inc: dict) -> dict:
    """Flat trauma-registry view of an incident."""
    tl = inc.get("timeline") or {}
    return {
        "incident_id": inc["id"], "reported_at": inc["created_at"], "source": inc["source"],
        "lat": inc["location"]["lat"], "lng": inc["location"]["lng"],
        "severity": inc["severity"]["value"], "severity_source": inc["severity"]["source"],
        "ambulance": (inc.get("ambulance") or {}).get("name"),
        "response_time_min": round(tl["ambulance_eta_s"] / 60, 1) if tl else None,
        "hospital": (inc.get("hospital") or {}).get("name"),
        "projected_total_min": round(tl["total_s"] / 60, 1) if tl else None,
        "within_golden_hour": tl.get("golden_hour_ok") if tl else None,
        "status": inc["status"], "outcome": inc.get("outcome"), "resolved_at": inc.get("resolved_at"),
    }


# ---------------------------------------------------------------- hotspots
def compute_hotspots(sim: Sim, router, k_stations: int = 3) -> dict:
    pts = sim.accidents
    coords = np.radians(np.array([[p["lat"], p["lng"]] for p in pts]))
    labels = DBSCAN(eps=650 / 6_371_000, min_samples=15, metric="haversine").fit_predict(coords)

    clusters = []
    for lab in sorted(set(labels) - {-1}):
        members = [p for p, l in zip(pts, labels) if l == lab]
        lat = float(np.mean([m["lat"] for m in members]))
        lng = float(np.mean([m["lng"] for m in members]))
        crit = sum(1 for m in members if m["severity"] == "critical") / len(members)
        clusters.append({"id": f"Z{len(clusters) + 1}", "lat": lat, "lng": lng, "count": len(members),
                         "critical_share": round(crit, 3)})
    if not clusters:
        return {"accidents": [], "hotspots": [], "stations": [], "metrics": None}

    centres = [(c["lat"], c["lng"]) for c in clusters]
    weights = np.array([c["count"] for c in clusters], dtype=float)
    bases = [(a["home_lat"], a["home_lng"]) for a in sim.ambulances]

    to_centres = router.matrix(bases, centres)          # ambulance base -> hotspot
    cand = router.matrix(centres, centres)              # candidate station at hotspot i -> hotspot j
    big = 1e9
    cur = np.array([min((to_centres[i][j] if to_centres[i][j] is not None else big) for i in range(len(bases)))
                    for j in range(len(centres))])
    before = cur.copy()

    def wavg(v):
        return float(np.sum(v * weights) / np.sum(weights))

    stations, chosen = [], set()
    for _ in range(k_stations):
        best_i, best_val = None, wavg(cur)
        for i in range(len(centres)):
            if i in chosen:
                continue
            new = np.minimum(cur, np.array([cand[i][j] if cand[i][j] is not None else big for j in range(len(centres))]))
            val = wavg(new)
            if val < best_val * 0.99:
                best_i, best_val = i, val
        if best_i is None:
            break
        chosen.add(best_i)
        cur = np.minimum(cur, np.array([cand[best_i][j] if cand[best_i][j] is not None else big for j in range(len(centres))]))
        stations.append({"id": f"S{len(stations) + 1}", "lat": centres[best_i][0], "lng": centres[best_i][1],
                         "covers": clusters[best_i]["id"], "avg_eta_after_min": round(wavg(cur) / 60, 2)})

    for c, b, a in zip(clusters, before, cur):
        c["eta_before_min"] = round(float(b) / 60, 2)
        c["eta_after_min"] = round(float(a) / 60, 2)
    b_avg, a_avg = wavg(before) / 60, wavg(cur) / 60
    return {
        "accidents": [{"lat": round(p["lat"], 5), "lng": round(p["lng"], 5), "severity": p["severity"]} for p in pts],
        "hotspots": clusters,
        "stations": stations,
        "metrics": {"avg_eta_before_min": round(b_avg, 2), "avg_eta_after_min": round(a_avg, 2),
                    "improvement_pct": round((1 - a_avg / b_avg) * 100, 1) if b_avg else 0.0,
                    "note": "Accident history is simulated. ETA is the average, weighted by accident count, "
                            "from each hotspot to its nearest ambulance base."},
    }
