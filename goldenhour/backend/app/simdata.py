"""Simulated fleet, hospitals and historical accidents for the demo city.

Everything here is SIMULATED. Hospital names are deliberately generic ("Demo ...") and
do not describe real hospitals. In a real deployment these tables come from the 112
control room, ambulance operators and a hospital capability registry.
"""
from __future__ import annotations

import copy
import random

import numpy as np

from .routing import BBOX

CITY_CENTER = {"lat": 22.5726, "lng": 88.3900, "name": "Demo city (central Kolkata)"}

_CAPS = {
    1: ["Trauma team", "CT scan", "Neurosurgery", "Blood bank", "Orthopaedics", "ICU"],
    2: ["Emergency department", "CT scan", "Orthopaedics", "Blood bank"],
    3: ["Emergency department", "X-ray"],
}

_HOSPITALS = [
    ("H1", "Demo Trauma Centre North", 1, 6, 22.600, 88.395),
    ("H2", "Demo Trauma Centre Central", 1, 4, 22.560, 88.365),
    ("H3", "Demo General Hospital East", 2, 5, 22.575, 88.415),
    ("H4", "Demo General Hospital South", 2, 3, 22.515, 88.380),
    ("H5", "Demo Community Hospital West", 3, 3, 22.585, 88.350),
    ("H6", "Demo Community Hospital Southeast", 3, 2, 22.530, 88.420),
    ("H7", "Demo Nursing Home Central", 3, 1, 22.566, 88.381),
    ("H8", "Demo District Hospital North-East", 2, 7, 22.610, 88.425),
]

# (hotspot centre lat, lng, relative weight)
_HOTSPOT_CENTERS = [
    (22.548, 88.352, 1.0),
    (22.575, 88.395, 0.8),
    (22.598, 88.372, 0.9),
    (22.520, 88.405, 0.7),
    (22.610, 88.415, 0.6),
    (22.562, 88.425, 0.8),
]


def _make_hospitals() -> list[dict]:
    return [
        {"id": hid, "name": name, "trauma_level": lvl, "beds_total": beds, "beds_available": beds,
         "capabilities": list(_CAPS[lvl]), "lat": lat, "lng": lng}
        for hid, name, lvl, beds, lat, lng in _HOSPITALS
    ]


def _make_ambulances(seed: int = 21) -> list[dict]:
    rng = random.Random(seed)
    plan = (
        [("GOV", "government", "ALS")] * 3 + [("GOV", "government", "BLS")] * 4
        + [("PVT", "private", "ALS")] * 2 + [("PVT", "private", "BLS")] * 4
        + [("AUTO", "volunteer", "BLS")] * 5
    )
    counters: dict[str, int] = {}
    out = []
    for prefix, provider, kind in plan:
        counters[prefix] = counters.get(prefix, 0) + 1
        lat = rng.uniform(BBOX["lat_min"] + 0.01, BBOX["lat_max"] - 0.01)
        lng = rng.uniform(BBOX["lng_min"] + 0.01, BBOX["lng_max"] - 0.01)
        amb_id = f"{prefix}-{counters[prefix]:02d}"
        out.append({"id": amb_id, "name": amb_id, "type": kind, "provider": provider,
                    "lat": lat, "lng": lng, "home_lat": lat, "home_lng": lng, "status": "available"})
    for a in rng.sample(out, 3):  # a few are already out on other calls
        a["status"] = "busy"
    return out


def make_accidents(seed: int = 5) -> list[dict]:
    """Historical accidents clustered around hotspots, plus scattered background noise."""
    rng = np.random.default_rng(seed)
    pts = []
    for lat, lng, w in _HOTSPOT_CENTERS:
        n = int(130 * w)
        for _ in range(n):
            pts.append({"lat": float(rng.normal(lat, 0.0035)), "lng": float(rng.normal(lng, 0.0042)),
                        "severity": str(rng.choice(["minor", "serious", "critical"], p=[0.5, 0.35, 0.15]))})
    for _ in range(120):
        pts.append({"lat": float(rng.uniform(BBOX["lat_min"], BBOX["lat_max"])),
                    "lng": float(rng.uniform(BBOX["lng_min"], BBOX["lng_max"])),
                    "severity": str(rng.choice(["minor", "serious", "critical"], p=[0.6, 0.3, 0.1]))})
    return pts


class Sim:
    """Mutable simulated world state (ambulance availability, hospital beds)."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.ambulances = _make_ambulances()
        self.hospitals = _make_hospitals()
        self.accidents = make_accidents()
        self.hotspot_cache = None

    def amb(self, amb_id: str) -> dict:
        return next(a for a in self.ambulances if a["id"] == amb_id)

    def hosp(self, hid: str) -> dict:
        return next(h for h in self.hospitals if h["id"] == hid)

    def snapshot(self) -> dict:
        return {"ambulances": copy.deepcopy(self.ambulances), "hospitals": copy.deepcopy(self.hospitals)}
