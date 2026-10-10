"""Trauma registry storage (SQLite). One JSON document per incident."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from typing import Optional


class IncidentStore:
    def __init__(self, path: Optional[str] = None):
        self.path = path or os.getenv("GOLDENHOUR_DB", "goldenhour.db")
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.lock = threading.Lock()
        with self.lock:
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS incidents ("
                "id TEXT PRIMARY KEY, created_at TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL)"
            )
            self.conn.commit()

    def save(self, incident: dict) -> None:
        with self.lock:
            self.conn.execute(
                "INSERT INTO incidents (id, created_at, status, payload) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET status=excluded.status, payload=excluded.payload",
                (incident["id"], incident["created_at"], incident["status"], json.dumps(incident)),
            )
            self.conn.commit()

    def get(self, incident_id: str) -> Optional[dict]:
        with self.lock:
            row = self.conn.execute("SELECT payload FROM incidents WHERE id = ?", (incident_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, limit: int = 200) -> list[dict]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT payload FROM incidents ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def count(self) -> int:
        with self.lock:
            return self.conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]

    def clear(self) -> None:
        with self.lock:
            self.conn.execute("DELETE FROM incidents")
            self.conn.commit()
