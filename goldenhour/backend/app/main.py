"""GoldenHour API."""
from __future__ import annotations

import csv
import io
import threading
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import engine
from .firstaid import get_guidance
from .routing import BBOX, get_router
from .severity import ROAD_TYPES, SPEED_ZONES, VEHICLES, SeverityModel
from .simdata import CITY_CENTER, Sim
from .store import IncidentStore

app = FastAPI(title="GoldenHour API", version="1.0.0",
              description="Post-crash response: bystander guidance, ambulance dispatch, hospital pre-alert.")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])

# ---- application state (single process, prototype) ----
LOCK = threading.RLock()
sim = Sim()
router = get_router()
model = SeverityModel()
store = IncidentStore()

MARGIN = 0.03  # allow a little outside the demo bounding box


class Details(BaseModel):
    road_type: Literal[tuple(ROAD_TYPES)] = "urban_arterial"  # type: ignore[valid-type]
    vehicle: Literal[tuple(VEHICLES)] = "car"  # type: ignore[valid-type]
    speed_zone: Literal[tuple(SPEED_ZONES)] = 50  # type: ignore[valid-type]
    people: int = Field(1, ge=1, le=10)
    hour: Optional[int] = Field(None, ge=0, le=23)


class IncidentIn(BaseModel):
    lat: float
    lng: float
    source: Literal["operator", "bystander", "auto_detect"] = "operator"
    details: Optional[Details] = None
    severity_override: Optional[Literal["minor", "serious", "critical"]] = None


class ResolveIn(BaseModel):
    outcome: Literal["delivered_to_hospital", "treated_at_scene", "cancelled_false_alarm"]


def _routing_info() -> dict:
    return {"mode": router.mode, "label": router.label,
            "degraded": bool(getattr(router, "degraded", False)),
            "last_error": getattr(router, "last_error", None)}


@app.get("/api/health")
def health():
    return {"status": "ok", "routing": _routing_info(), "model": model.info(), "incidents": store.count()}


@app.get("/api/state")
def state():
    with LOCK:
        snap = sim.snapshot()
    return {"city": CITY_CENTER, "bbox": BBOX, "routing": _routing_info(), **snap,
            "options": {"road_types": ROAD_TYPES, "vehicles": VEHICLES, "speed_zones": SPEED_ZONES}}


@app.post("/api/severity")
def severity(details: Details):
    hour = details.hour if details.hour is not None else engine.local_hour()
    return model.predict(details.road_type, details.vehicle, details.speed_zone, hour, details.people)


@app.post("/api/incidents")
def create_incident(body: IncidentIn):
    if not (BBOX["lat_min"] - MARGIN <= body.lat <= BBOX["lat_max"] + MARGIN
            and BBOX["lng_min"] - MARGIN <= body.lng <= BBOX["lng_max"] + MARGIN):
        raise HTTPException(422, "Location is outside the demo coverage area")
    with LOCK:
        try:
            return engine.create_incident(
                sim, router, model, store, lat=body.lat, lng=body.lng, source=body.source,
                details=body.details.model_dump() if body.details else None,
                severity_override=body.severity_override)
        except RuntimeError as exc:
            raise HTTPException(503, str(exc))


@app.get("/api/incidents")
def list_incidents(limit: int = Query(100, ge=1, le=500)):
    return store.list(limit)


@app.get("/api/incidents/{incident_id}")
def get_incident(incident_id: str):
    inc = store.get(incident_id)
    if inc is None:
        raise HTTPException(404, "Incident not found")
    return inc


@app.post("/api/incidents/{incident_id}/resolve")
def resolve(incident_id: str, body: ResolveIn):
    with LOCK:
        inc = engine.resolve_incident(sim, store, incident_id, body.outcome)
    if inc is None:
        raise HTTPException(404, "Incident not found")
    return inc


@app.get("/api/registry")
def registry():
    rows = [engine.registry_row(i) for i in store.list(500)]
    total = len(rows)
    with_tl = [r for r in rows if r["response_time_min"] is not None]
    summary = {
        "total": total,
        "avg_response_min": round(sum(r["response_time_min"] for r in with_tl) / len(with_tl), 1) if with_tl else None,
        "within_golden_hour": sum(1 for r in with_tl if r["within_golden_hour"]),
        "critical": sum(1 for r in rows if r["severity"] == "critical"),
    }
    return {"summary": summary, "rows": rows}


@app.get("/api/registry.csv")
def registry_csv():
    rows = [engine.registry_row(i) for i in store.list(500)]
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=goldenhour_trauma_registry.csv"})


@app.get("/api/hotspots")
def hotspots():
    with LOCK:
        if sim.hotspot_cache is None:
            sim.hotspot_cache = engine.compute_hotspots(sim, router)
        return {**sim.hotspot_cache, "routing": _routing_info()}


@app.get("/api/first-aid")
def first_aid(lang: str = "en"):
    return get_guidance(lang)


@app.post("/api/reset")
def reset():
    """Restore the simulated fleet, beds and registry (handy between demo runs)."""
    with LOCK:
        sim.reset()
        store.clear()
    return {"status": "reset"}
