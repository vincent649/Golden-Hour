"""Road routing.

Two interchangeable routers:

* OsrmRouter      - real road network through an OSRM server (default: the public
                    demo server, override with OSRM_URL). Needs internet access.
* SyntheticRouter - an offline, seeded grid "city" so the whole system also runs
                    with no internet (tests, flights, locked-down networks).

get_router() picks one. ROUTING=osrm|synthetic|auto (default auto: try OSRM, fall
back to synthetic). If OSRM fails while running, the wrapper falls back to the
synthetic router and stays there, so one response never mixes both worlds.
"""
from __future__ import annotations

import os
import random
from typing import Optional, Sequence

import httpx
import networkx as nx
import numpy as np

from .geo import haversine_m

LatLng = tuple[float, float]

# Ambulances use sirens and clear lanes, so they beat ordinary traffic times.
# This is an assumption, kept in one place so it is easy to change.
AMBULANCE_SPEED_FACTOR = float(os.getenv("AMBULANCE_SPEED_FACTOR", "0.85"))

# Bounding box of the demo city (central Kolkata, east of the river).
BBOX = {"lat_min": 22.50, "lat_max": 22.62, "lng_min": 88.34, "lng_max": 88.43}


class SyntheticRouter:
    """Seeded grid city with fast arterial roads and slower local streets."""

    mode = "synthetic"
    label = "Synthetic grid (offline)"

    def __init__(self, n: int = 24, seed: int = 7):
        rng = random.Random(seed)
        self.G = nx.Graph()
        lat_step = (BBOX["lat_max"] - BBOX["lat_min"]) / (n - 1)
        lng_step = (BBOX["lng_max"] - BBOX["lng_min"]) / (n - 1)
        pos: dict[tuple[int, int], LatLng] = {}
        for i in range(n):
            for j in range(n):
                jitter_lat = rng.uniform(-0.18, 0.18) * lat_step
                jitter_lng = rng.uniform(-0.18, 0.18) * lng_step
                pos[(i, j)] = (
                    BBOX["lat_min"] + i * lat_step + jitter_lat,
                    BBOX["lng_min"] + j * lng_step + jitter_lng,
                )
        for (i, j), p in pos.items():
            self.G.add_node((i, j), lat=p[0], lng=p[1])
        for i in range(n):
            for j in range(n):
                for di, dj in ((1, 0), (0, 1)):
                    ni, nj = i + di, j + dj
                    if ni >= n or nj >= n:
                        continue
                    arterial = (di == 1 and j % 6 == 0) or (dj == 1 and i % 6 == 0)
                    if not arterial and rng.random() < 0.10:
                        continue  # a missing local street
                    speed_ms = (45 if arterial else 24) / 3.6
                    length = haversine_m(*pos[(i, j)], *pos[(ni, nj)])
                    self.G.add_edge((i, j), (ni, nj), length=length, t=length / speed_ms)
        biggest = max(nx.connected_components(self.G), key=len)
        self.G = self.G.subgraph(biggest).copy()
        self.nodes = list(self.G.nodes)
        self.coords = np.array([[self.G.nodes[k]["lat"], self.G.nodes[k]["lng"]] for k in self.nodes])

    # ----- helpers -----
    def _snap(self, p: LatLng) -> tuple[tuple[int, int], float]:
        """Nearest graph node and the off-network distance in metres."""
        mid_lat = np.radians(p[0])
        dy = (self.coords[:, 0] - p[0]) * 111_320.0
        dx = (self.coords[:, 1] - p[1]) * 111_320.0 * np.cos(mid_lat)
        idx = int(np.argmin(dx * dx + dy * dy))
        node = self.nodes[idx]
        d = haversine_m(p[0], p[1], self.G.nodes[node]["lat"], self.G.nodes[node]["lng"])
        return node, d

    @staticmethod
    def _snap_time(d_m: float) -> float:
        return d_m / (15 / 3.6)  # crawling speed on the last stretch to/from the road

    # ----- public API -----
    def matrix(self, sources: Sequence[LatLng], dests: Sequence[LatLng]) -> list[list[Optional[float]]]:
        snapped_dest = [self._snap(d) for d in dests]
        out: list[list[Optional[float]]] = []
        for s in sources:
            s_node, s_d = self._snap(s)
            dist = nx.single_source_dijkstra_path_length(self.G, s_node, weight="t")
            row = []
            for d_node, d_d in snapped_dest:
                t = dist.get(d_node)
                row.append(None if t is None else (t + self._snap_time(s_d) + self._snap_time(d_d)) * AMBULANCE_SPEED_FACTOR)
            out.append(row)
        return out

    def route(self, a: LatLng, b: LatLng) -> dict:
        a_node, a_d = self._snap(a)
        b_node, b_d = self._snap(b)
        path = nx.shortest_path(self.G, a_node, b_node, weight="t")
        coords = [[a[0], a[1]]] + [[self.G.nodes[n]["lat"], self.G.nodes[n]["lng"]] for n in path] + [[b[0], b[1]]]
        length = sum(self.G[u][v]["length"] for u, v in zip(path, path[1:])) + a_d + b_d
        t = sum(self.G[u][v]["t"] for u, v in zip(path, path[1:])) + self._snap_time(a_d) + self._snap_time(b_d)
        return {"duration_s": t * AMBULANCE_SPEED_FACTOR, "distance_m": length, "coords": coords}


class OsrmRouter:
    mode = "osrm"
    label = "OpenStreetMap roads (OSRM)"

    def __init__(self, base_url: str, timeout: float = 8.0):
        self.base = base_url.rstrip("/")
        self.client = httpx.Client(timeout=timeout, headers={"User-Agent": "GoldenHour-hackathon-prototype"})

    @staticmethod
    def _fmt(points: Sequence[LatLng]) -> str:
        return ";".join(f"{lng:.6f},{lat:.6f}" for lat, lng in points)

    def matrix(self, sources: Sequence[LatLng], dests: Sequence[LatLng]) -> list[list[Optional[float]]]:
        pts = list(sources) + list(dests)
        src_idx = ";".join(str(i) for i in range(len(sources)))
        dst_idx = ";".join(str(len(sources) + i) for i in range(len(dests)))
        url = f"{self.base}/table/v1/driving/{self._fmt(pts)}"
        r = self.client.get(url, params={"sources": src_idx, "destinations": dst_idx, "annotations": "duration"})
        r.raise_for_status()
        data = r.json()
        if data.get("code") != "Ok":
            raise RuntimeError(f"OSRM table error: {data.get('code')}")
        return [[None if v is None else v * AMBULANCE_SPEED_FACTOR for v in row] for row in data["durations"]]

    def route(self, a: LatLng, b: LatLng) -> dict:
        url = f"{self.base}/route/v1/driving/{self._fmt([a, b])}"
        r = self.client.get(url, params={"overview": "full", "geometries": "geojson"})
        r.raise_for_status()
        data = r.json()
        if data.get("code") != "Ok" or not data.get("routes"):
            raise RuntimeError(f"OSRM route error: {data.get('code')}")
        rt = data["routes"][0]
        coords = [[lat, lng] for lng, lat in rt["geometry"]["coordinates"]]
        return {"duration_s": rt["duration"] * AMBULANCE_SPEED_FACTOR, "distance_m": rt["distance"], "coords": coords}


class ResilientRouter:
    """Uses the primary router; on any failure switches (stickily) to the synthetic one."""

    def __init__(self, primary, fallback: SyntheticRouter):
        self.primary = primary
        self.fallback = fallback
        self.degraded = False
        self.last_error: Optional[str] = None

    @property
    def active(self):
        return self.fallback if self.degraded else self.primary

    @property
    def mode(self) -> str:
        return self.active.mode

    @property
    def label(self) -> str:
        return self.active.label

    def _call(self, name: str, *args):
        if not self.degraded:
            try:
                return getattr(self.primary, name)(*args)
            except Exception as exc:  # network, rate limit, bad response
                self.degraded = True
                self.last_error = f"{type(exc).__name__}: {exc}"
        return getattr(self.fallback, name)(*args)

    def matrix(self, sources, dests):
        return self._call("matrix", sources, dests)

    def route(self, a, b):
        return self._call("route", a, b)


def _probe_osrm(base_url: str) -> bool:
    try:
        r = httpx.get(
            f"{base_url.rstrip('/')}/route/v1/driving/88.3639,22.5726;88.4000,22.5800",
            params={"overview": "false"},
            timeout=3.0,
        )
        return r.status_code == 200 and r.json().get("code") == "Ok"
    except Exception:
        return False


def get_router():
    mode = os.getenv("ROUTING", "auto").lower()
    synthetic = SyntheticRouter()
    if mode == "synthetic":
        return synthetic
    base = os.getenv("OSRM_URL", "https://router.project-osrm.org")
    if mode == "osrm" or _probe_osrm(base):
        return ResilientRouter(OsrmRouter(base), synthetic)
    return synthetic
