import json
import sqlite3
import time
import uuid

from .config import RUNTIME


class Store:
    def __init__(self, path=None):
        self.db = sqlite3.connect(path or RUNTIME / "workspace.sqlite3")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS objects (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, ts REAL, vehicle TEXT, kind TEXT, payload TEXT)"
        )
        self.db.commit()

    def get(self, key, default=None):
        row = self.db.execute("SELECT value FROM objects WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, key, value):
        self.db.execute(
            "INSERT INTO objects VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value, allow_nan=False)),
        )
        self.db.commit()

    def event(self, vehicle, kind, payload):
        e = {
            "id": uuid.uuid4().hex,
            "ts": time.time(),
            "vehicle": vehicle,
            "kind": kind,
            "payload": payload,
        }
        self.db.execute(
            "INSERT INTO events VALUES (?,?,?,?,?)",
            (e["id"], e["ts"], vehicle, kind, json.dumps(payload, allow_nan=False)),
        )
        self.db.commit()
        return e

    def events(self, vehicle=None, limit=200):
        rows = self.db.execute(
            "SELECT id,ts,vehicle,kind,payload FROM events WHERE (? IS NULL OR vehicle=?) ORDER BY ts DESC LIMIT ?",
            (vehicle, vehicle, min(limit, 2000)),
        ).fetchall()
        return [
            dict(zip(["id", "ts", "vehicle", "kind", "payload"], [*r[:4], json.loads(r[4])]))
            for r in rows
        ]
