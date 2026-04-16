from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class HistoryRepository:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else Path(__file__).resolve().parents[2] / "history.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS event_history (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    health_score INTEGER NOT NULL,
                    risk_score INTEGER NOT NULL,
                    issue_count INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_event_history_created_at ON event_history(created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_event_history_filters ON event_history(event_type, platform, mode)"
            )

    def record_event(
        self,
        event_type: str,
        platform: str,
        mode: str,
        health_score: int,
        risk_score: int,
        issue_count: int,
        payload: dict,
    ) -> str:
        event_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f") + "-" + event_type
        created_at = datetime.now(timezone.utc).isoformat()
        payload_json = json.dumps(payload, default=str)

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO event_history (event_id, event_type, platform, mode, created_at, health_score, risk_score, issue_count, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (event_id, event_type, platform, mode, created_at, health_score, risk_score, issue_count, payload_json),
            )

        return event_id

    def get_event(self, event_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM event_history WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        if row is None:
            return None

        return {
            "event_id": row["event_id"],
            "event_type": row["event_type"],
            "platform": row["platform"],
            "mode": row["mode"],
            "created_at": row["created_at"],
            "health_score": row["health_score"],
            "risk_score": row["risk_score"],
            "issue_count": row["issue_count"],
            "payload": json.loads(row["payload_json"]),
        }

    def list_events(
        self,
        limit: int = 50,
        offset: int = 0,
        event_type: str | None = None,
        platform: str | None = None,
        mode: str | None = None,
    ) -> list[dict]:
        clauses = ["1=1"]
        values: list[str | int] = []
        if event_type:
            clauses.append("event_type = ?")
            values.append(event_type)
        if platform:
            clauses.append("platform = ?")
            values.append(platform)
        if mode:
            clauses.append("mode = ?")
            values.append(mode)

        query = f"SELECT event_id, event_type, platform, mode, created_at, health_score, risk_score, issue_count FROM event_history WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        values.extend([limit, offset])

        with self._connect() as conn:
            rows = conn.execute(query, tuple(values)).fetchall()

        return [
            {
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "platform": row["platform"],
                "mode": row["mode"],
                "created_at": row["created_at"],
                "health_score": row["health_score"],
                "risk_score": row["risk_score"],
                "issue_count": row["issue_count"],
            }
            for row in rows
        ]

    def recent_events(
        self,
        limit: int = 10,
        platform: str | None = None,
        mode: str | None = None,
        event_type: str | None = None,
    ) -> list[dict]:
        return self.list_events(limit=limit, offset=0, event_type=event_type, platform=platform, mode=mode)
