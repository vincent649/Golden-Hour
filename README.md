# GoldenHour

A post-crash response platform that covers the three stages most systems treat separately:

1. **Bystander Copilot** – voice-guided first aid in English, Hindi and Bengali, a Good Samaritan note, and a one-tap SOS.
2. **Smart Dispatch** – pools government, private and volunteer ambulances, ranks them by real road travel time, and prefers advanced life support for critical patients.
3. **Hospital Pre-Alert** – picks a hospital that can actually treat the injury (not just the nearest), reserves a bed and sends a brief before the patient arrives.

Plus severity triage (scikit-learn), ambulance pre-positioning from accident hotspots (DBSCAN), and an automatic trauma registry with CSV export.

**Stack:** FastAPI + SQLite + scikit-learn + networkx (backend), React + Vite + Leaflet (frontend).

> **Prototype only.** Fleet, hospitals, beds and accident history are simulated. Not for real emergencies. In an emergency call 112.

## Run it

You need Python 3.10+ and Node 18+.

**1. Backend** (terminal 1)

```bash
cd backend
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
# macOS / Linux:       source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

API docs open at http://localhost:8000/docs.

**2. Frontend** (terminal 2)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The dev server proxies `/api` to the backend.

## Try this flow (about 3 minutes)

1. **Dispatch console:** click the map to place a crash, choose a vehicle, set severity to *critical* and press **Dispatch**. Watch the unit drive to the scene and on to the hospital against the golden-hour clock.
2. Note the yellow notice: the *nearest* hospital was skipped because it lacks a trauma team, CT and neurosurgery.
3. **Bystander Copilot:** tap a location, press **Send SOS**, switch language, use **Read aloud**. The SOS appears in the console's incident list within 5 seconds.
4. **Hotspots:** the recommended ambulance stations and the average response-time improvement.
5. **Trauma registry:** every incident as a structured record. Export CSV.

*Reset demo* (top right) restores the fleet, beds and registry.

## Routing: real roads or offline

| Mode | When | Notes |
|---|---|---|
| **OSRM (OpenStreetMap roads)** | default when internet is available | Uses the public demo server `router.project-osrm.org`. Fine for a demo; for anything heavier run your own OSRM and set `OSRM_URL`. |
| **Synthetic grid** | automatic fallback, or `ROUTING=synthetic` | A seeded offline grid city. Routes will not follow the real streets drawn on the map. The badge in the header shows which mode is active. |

If OSRM fails while running, the backend switches to the synthetic grid and stays there until restarted.

Environment variables: `ROUTING` (`auto`/`osrm`/`synthetic`), `OSRM_URL`, `AMBULANCE_SPEED_FACTOR` (default 0.85, ambulances are faster than normal traffic), `GOLDENHOUR_DB` (SQLite path, default `goldenhour.db`).

## Tests

```bash
cd backend
pytest -q
```

22 tests cover dispatch, hospital matching, bed reservation, severity model sanity, registry, hotspots, first-aid content, and both routers (OSRM is tested against mocked responses).

## API summary

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/state` | Fleet, hospitals, dropdown options, routing mode |
| POST | `/api/incidents` | Report a crash; returns the full plan (severity, ambulance, hospital, timeline, pre-alert) |
| GET | `/api/incidents`, `/api/incidents/{id}` | List or fetch incidents |
| POST | `/api/incidents/{id}/resolve` | Close with `delivered_to_hospital`, `treated_at_scene` or `cancelled_false_alarm` |
| POST | `/api/severity` | Triage estimate for crash details |
| GET | `/api/hotspots` | Hotspots, recommended stations, response-time improvement |
| GET | `/api/registry`, `/api/registry.csv` | Trauma registry and export |
| GET | `/api/first-aid?lang=en\|hi\|bn` | Bystander guidance |
| POST | `/api/reset` | Reset the simulation and registry |

## How the decisions are made

- **Ambulance ranking:** road travel time to the scene, plus a penalty for a poor fit: +7 min for a non-ALS unit on a critical patient, and extra for volunteer units on serious or critical cases (`engine.unit_penalty_s`). This is a policy choice, so tune it with clinicians.
- **Hospital matching:** a hospital is *eligible* only if it has the capabilities the severity needs (critical: trauma team, CT, neurosurgery, blood bank; serious: CT, blood bank; minor: emergency department) and a free bed. The nearest eligible one by road wins.
- **Golden-hour check:** ambulance ETA + 5 min assumed at the scene + transport time, against 60 minutes.
- **Pre-positioning:** DBSCAN clusters accident locations; stations are added greedily where they cut the accident-weighted travel time most.

## What is simulated, and how to make it real

| Simulated here | Real source |
|---|---|
| Ambulance positions and availability | 112 control room / operator GPS feeds (`simdata.py`) |
| Hospital capabilities and beds | A hospital capability registry (`simdata.py`) |
| Accident history | State police / MoRTH (iRAD) open data (`simdata.make_accidents`) |
| Severity model training data | Real labelled crash records (`severity.make_training_data`) |

## Known limits

- The live OSRM path could not be run against the real server where this was built (no internet), so it is verified only against mocked responses. Test it once on your machine.
- First-aid text is conservative general guidance and has **not been clinically reviewed**. Have a doctor or trainer review it before any real use.
- The severity model is trained on synthetic data and demonstrates the pipeline only.
- "Likely injuries" in the pre-alert are inferred from crash type alone and labelled as indicative.
- State (fleet, beds) is in memory in a single process and resets on restart. Incidents persist in SQLite.
- Map tiles need internet access.
