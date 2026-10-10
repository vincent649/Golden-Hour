"""Crash severity triage.

IMPORTANT: there is no public, labelled crash-severity dataset bundled here, so the
model is trained at startup on SYNTHETIC records whose risk pattern follows widely
reported factors (speed, road type, vulnerable road users, heavy vehicles, night).
It demonstrates the pipeline. For real use, retrain on real records (for example
MoRTH / iRAD data) by replacing `make_training_data`.
"""
from __future__ import annotations

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

CLASSES = ["minor", "serious", "critical"]
ROAD_TYPES = ["local_street", "urban_arterial", "state_highway", "national_highway"]
VEHICLES = ["car", "two_wheeler", "truck_bus", "pedestrian"]
SPEED_ZONES = [30, 50, 80, 100]

_ROAD_RISK = dict(zip(ROAD_TYPES, [0.0, 0.6, 1.4, 2.0]))
_VEH_RISK = dict(zip(VEHICLES, [0.5, 1.3, 1.8, 1.6]))

FEATURES = ROAD_TYPES + VEHICLES + ["speed_zone", "night", "people"]


def _is_night(hour: int) -> int:
    return 1 if (hour >= 22 or hour <= 5) else 0


def encode(road_type: str, vehicle: str, speed_zone: int, hour: int, people: int) -> list[float]:
    row = [1.0 if road_type == r else 0.0 for r in ROAD_TYPES]
    row += [1.0 if vehicle == v else 0.0 for v in VEHICLES]
    row += [float(speed_zone), float(_is_night(hour)), float(people)]
    return row


def make_training_data(n: int = 4000, seed: int = 11):
    rng = np.random.default_rng(seed)
    X, scores = [], []
    for _ in range(n):
        road = ROAD_TYPES[rng.integers(len(ROAD_TYPES))]
        veh = VEHICLES[rng.choice(len(VEHICLES), p=[0.35, 0.35, 0.15, 0.15])]
        speed = SPEED_ZONES[rng.integers(len(SPEED_ZONES))]
        hour = int(rng.integers(0, 24))
        people = int(rng.integers(1, 7))
        score = (
            _ROAD_RISK[road]
            + _VEH_RISK[veh]
            + (speed - 30) / 35.0
            + 1.0 * _is_night(hour)
            + 0.25 * (people - 1)
            + rng.normal(0, 0.45)
        )
        X.append(encode(road, veh, speed, hour, people))
        scores.append(score)
    # Most crashes are minor and few are critical, so cut the score at the 55th and 85th percentile.
    lo, hi = np.quantile(scores, [0.55, 0.85])
    y = [0 if s < lo else (1 if s < hi else 2) for s in scores]
    return np.array(X), np.array(y)


class SeverityModel:
    def __init__(self):
        X, y = make_training_data()
        X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=3, stratify=y)
        self.clf = RandomForestClassifier(n_estimators=80, max_depth=9, random_state=5, n_jobs=1)
        self.clf.fit(X_tr, y_tr)
        self.holdout_accuracy = float(self.clf.score(X_te, y_te))
        self.trained_on = "synthetic records (demo)"

    def predict(self, road_type: str, vehicle: str, speed_zone: int, hour: int, people: int) -> dict:
        x = np.array([encode(road_type, vehicle, speed_zone, hour, people)])
        proba = self.clf.predict_proba(x)[0]
        classes = [CLASSES[int(c)] for c in self.clf.classes_]
        probs = {c: round(float(p), 3) for c, p in zip(classes, proba)}
        label = max(probs, key=probs.get)
        return {"severity": label, "probabilities": probs, "confidence": probs[label]}

    def info(self) -> dict:
        return {"model": "RandomForest (scikit-learn)", "trained_on": self.trained_on,
                "holdout_accuracy": round(self.holdout_accuracy, 3), "features": FEATURES}
