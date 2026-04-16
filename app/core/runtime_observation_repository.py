from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.models.schemas import (
    CommandResult,
    RuntimeObservationTrace,
)


class RuntimeObservationRepository:
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
                CREATE TABLE IF NOT EXISTS runtime_observation_batches (
                    batch_id TEXT PRIMARY KEY,
                    platform TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    requested_at TEXT NOT NULL,
                    finished_at TEXT,
                    partial_failure INTEGER NOT NULL,
                    task_count INTEGER NOT NULL,
                    trace_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_command_results (
                    invocation_id TEXT PRIMARY KEY,
                    batch_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    command_name TEXT NOT NULL,
                    args_json TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    exit_code INTEGER NOT NULL,
                    stdout_summary TEXT NOT NULL,
                    stderr_summary TEXT NOT NULL,
                    parsed_artifact_type TEXT,
                    parsed_artifact_summary TEXT,
                    result_json TEXT NOT NULL,
                    FOREIGN KEY(batch_id) REFERENCES runtime_observation_batches(batch_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_runtime_batches_requested_at ON runtime_observation_batches(requested_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_runtime_results_batch ON runtime_command_results(batch_id, started_at DESC)"
            )

    def record_trace(self, trace: RuntimeObservationTrace) -> None:
        batch = trace.batch
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runtime_observation_batches (
                    batch_id, platform, mode, requested_at, finished_at,
                    partial_failure, task_count, trace_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch.batch_id,
                    batch.platform,
                    batch.mode,
                    batch.requested_at.isoformat(),
                    batch.finished_at.isoformat() if batch.finished_at else None,
                    1 if batch.partial_failure else 0,
                    batch.task_count,
                    json.dumps(trace.model_dump(mode="json"), default=str),
                ),
            )
            for result in trace.results:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO runtime_command_results (
                        invocation_id, batch_id, task_id, command_name, args_json,
                        started_at, finished_at, success, exit_code, stdout_summary,
                        stderr_summary, parsed_artifact_type, parsed_artifact_summary, result_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        result.invocation_id,
                        batch.batch_id,
                        result.task_id,
                        result.command_name,
                        json.dumps(result.args),
                        result.started_at.isoformat(),
                        result.finished_at.isoformat(),
                        1 if result.success else 0,
                        result.exit_code,
                        result.stdout_summary,
                        result.stderr_summary,
                        result.parsed_artifact_type,
                        result.parsed_artifact_summary,
                        json.dumps(result.model_dump(mode="json"), default=str),
                    ),
                )

    def list_recent_traces(
        self,
        *,
        limit: int = 20,
        platform: str | None = None,
        mode: str | None = None,
    ) -> list[RuntimeObservationTrace]:
        clauses = ["1=1"]
        values: list[str | int] = []
        if platform:
            clauses.append("platform = ?")
            values.append(platform)
        if mode:
            clauses.append("mode = ?")
            values.append(mode)
        values.append(limit)
        query = (
            f"SELECT trace_json FROM runtime_observation_batches "
            f"WHERE {' AND '.join(clauses)} ORDER BY requested_at DESC LIMIT ?"
        )
        with self._connect() as conn:
            rows = conn.execute(query, tuple(values)).fetchall()
        traces: list[RuntimeObservationTrace] = []
        for row in rows:
            traces.append(RuntimeObservationTrace.model_validate(json.loads(row["trace_json"])))
        return traces

    def get_result(self, invocation_id: str) -> CommandResult | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT result_json FROM runtime_command_results WHERE invocation_id = ?",
                (invocation_id,),
            ).fetchone()
        if row is None:
            return None
        return CommandResult.model_validate(json.loads(row["result_json"]))
