from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.models.schemas import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
    OperatorAction,
)


class InvalidApprovalTransitionError(ValueError):
    pass


class ApprovalRepository:
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
                CREATE TABLE IF NOT EXISTS approval_requests (
                    request_id TEXT PRIMARY KEY,
                    incident_key TEXT NOT NULL,
                    playbook_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    action_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    target TEXT,
                    platform TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    risk_tier TEXT,
                    action_confidence REAL,
                    policy_reason TEXT,
                    justification_summary TEXT NOT NULL,
                    current_incident_state TEXT NOT NULL,
                    current_step_state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS approval_decisions (
                    decision_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    operator_action TEXT NOT NULL,
                    decision_reason TEXT NOT NULL,
                    decided_at TEXT NOT NULL,
                    prior_status TEXT NOT NULL,
                    resulting_status TEXT NOT NULL,
                    FOREIGN KEY(request_id) REFERENCES approval_requests(request_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_approval_requests_status_created ON approval_requests(status, created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_approval_requests_incident ON approval_requests(incident_key, created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_approval_decisions_request ON approval_decisions(request_id, decided_at DESC)"
            )

    def _serialize_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.isoformat()

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if value is None:
            return None
        return datetime.fromisoformat(value)

    def _row_to_request(self, row: sqlite3.Row) -> ApprovalRequest:
        return ApprovalRequest(
            request_id=row["request_id"],
            incident_key=row["incident_key"],
            playbook_id=row["playbook_id"],
            step_id=row["step_id"],
            action_id=row["action_id"],
            action_type=row["action_type"],
            target=row["target"],
            platform=row["platform"],
            mode=row["mode"],
            risk_tier=row["risk_tier"],
            action_confidence=row["action_confidence"],
            policy_reason=row["policy_reason"],
            justification_summary=row["justification_summary"],
            current_incident_state=row["current_incident_state"],
            current_step_state=row["current_step_state"],
            created_at=self._parse_datetime(row["created_at"]) or datetime.now(timezone.utc),
            expires_at=self._parse_datetime(row["expires_at"]),
            status=ApprovalStatus(row["status"]),
        )

    def _row_to_decision(self, row: sqlite3.Row) -> ApprovalDecision:
        return ApprovalDecision(
            decision_id=row["decision_id"],
            request_id=row["request_id"],
            operator_action=OperatorAction(row["operator_action"]),
            decision_reason=row["decision_reason"],
            decided_at=self._parse_datetime(row["decided_at"]) or datetime.now(timezone.utc),
            prior_status=ApprovalStatus(row["prior_status"]),
            resulting_status=ApprovalStatus(row["resulting_status"]),
        )

    def _request_id(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f") + "-approval-request"

    def _decision_id(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f") + "-approval-decision"

    def _validate_transition(self, prior_status: ApprovalStatus, resulting_status: ApprovalStatus) -> None:
        allowed: dict[ApprovalStatus, set[ApprovalStatus]] = {
            ApprovalStatus.pending: {
                ApprovalStatus.approved,
                ApprovalStatus.denied,
                ApprovalStatus.expired,
                ApprovalStatus.cancelled,
            },
            ApprovalStatus.approved: set(),
            ApprovalStatus.denied: set(),
            ApprovalStatus.expired: set(),
            ApprovalStatus.cancelled: set(),
        }
        if resulting_status not in allowed.get(prior_status, set()):
            raise InvalidApprovalTransitionError(
                f"Invalid approval transition from {prior_status.value} to {resulting_status.value}."
            )

    def get_pending_for_action(
        self,
        *,
        incident_key: str,
        playbook_id: str,
        step_id: str,
        action_id: str,
    ) -> ApprovalRequest | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM approval_requests
                WHERE incident_key = ?
                  AND playbook_id = ?
                  AND step_id = ?
                  AND action_id = ?
                  AND status = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (
                    incident_key,
                    playbook_id,
                    step_id,
                    action_id,
                    ApprovalStatus.pending.value,
                ),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_request(row)

    def get_latest_for_action(
        self,
        *,
        incident_key: str,
        playbook_id: str,
        step_id: str,
        action_id: str,
    ) -> ApprovalRequest | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM approval_requests
                WHERE incident_key = ?
                  AND playbook_id = ?
                  AND step_id = ?
                  AND action_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (
                    incident_key,
                    playbook_id,
                    step_id,
                    action_id,
                ),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_request(row)

    def create_request(self, request: ApprovalRequest) -> ApprovalRequest:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO approval_requests (
                    request_id, incident_key, playbook_id, step_id, action_id, action_type, target,
                    platform, mode, risk_tier, action_confidence, policy_reason, justification_summary,
                    current_incident_state, current_step_state, created_at, expires_at, status, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.request_id,
                    request.incident_key,
                    request.playbook_id,
                    request.step_id,
                    request.action_id,
                    request.action_type,
                    request.target,
                    request.platform,
                    request.mode,
                    request.risk_tier,
                    request.action_confidence,
                    request.policy_reason,
                    request.justification_summary,
                    request.current_incident_state,
                    request.current_step_state,
                    self._serialize_datetime(request.created_at),
                    self._serialize_datetime(request.expires_at),
                    request.status.value,
                    now,
                ),
            )
        return request

    def create_or_get_pending_request(self, request: ApprovalRequest) -> ApprovalRequest:
        existing = self.get_pending_for_action(
            incident_key=request.incident_key,
            playbook_id=request.playbook_id,
            step_id=request.step_id,
            action_id=request.action_id,
        )
        if existing is not None:
            return existing
        return self.create_request(request)

    def build_request(
        self,
        *,
        incident_key: str,
        playbook_id: str,
        step_id: str,
        action_id: str,
        action_type: str,
        target: str | None,
        platform: str,
        mode: str,
        risk_tier: str | None,
        action_confidence: float | None,
        policy_reason: str | None,
        justification_summary: str,
        current_incident_state: str,
        current_step_state: str,
        expires_at: datetime | None = None,
    ) -> ApprovalRequest:
        return ApprovalRequest(
            request_id=self._request_id(),
            incident_key=incident_key,
            playbook_id=playbook_id,
            step_id=step_id,
            action_id=action_id,
            action_type=action_type,
            target=target,
            platform=platform,
            mode=mode,
            risk_tier=risk_tier,
            action_confidence=action_confidence,
            policy_reason=policy_reason,
            justification_summary=justification_summary,
            current_incident_state=current_incident_state,
            current_step_state=current_step_state,
            created_at=datetime.now(timezone.utc),
            expires_at=expires_at,
            status=ApprovalStatus.pending,
        )

    def get_request(self, request_id: str) -> ApprovalRequest | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM approval_requests WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_request(row)

    def list_requests(
        self,
        *,
        status: ApprovalStatus | None = None,
        platform: str | None = None,
        mode: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ApprovalRequest]:
        clauses = ["1=1"]
        values: list[str | int] = []
        if status is not None:
            clauses.append("status = ?")
            values.append(status.value)
        if platform:
            clauses.append("platform = ?")
            values.append(platform)
        if mode:
            clauses.append("mode = ?")
            values.append(mode)
        values.extend([limit, offset])
        query = (
            f"SELECT * FROM approval_requests WHERE {' AND '.join(clauses)} "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?"
        )
        with self._connect() as conn:
            rows = conn.execute(query, tuple(values)).fetchall()
        return [self._row_to_request(row) for row in rows]

    def list_requests_for_incident(self, incident_key: str, limit: int = 50) -> list[ApprovalRequest]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM approval_requests
                WHERE incident_key = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (incident_key, limit),
            ).fetchall()
        return [self._row_to_request(row) for row in rows]

    def expire_outdated_pending(self, now: datetime | None = None) -> int:
        now = now or datetime.now(timezone.utc)
        now_iso = now.isoformat()
        with self._connect() as conn:
            result = conn.execute(
                """
                UPDATE approval_requests
                SET status = ?, updated_at = ?
                WHERE status = ?
                  AND expires_at IS NOT NULL
                  AND expires_at <= ?
                """,
                (
                    ApprovalStatus.expired.value,
                    now_iso,
                    ApprovalStatus.pending.value,
                    now_iso,
                ),
            )
        return result.rowcount

    def decide(
        self,
        *,
        request_id: str,
        operator_action: OperatorAction,
        decision_reason: str,
    ) -> ApprovalDecision:
        request = self.get_request(request_id)
        if request is None:
            raise KeyError(f"Approval request {request_id} not found.")

        prior_status = request.status
        resulting_status = (
            ApprovalStatus.approved if operator_action == OperatorAction.approve else ApprovalStatus.denied
        )
        self._validate_transition(prior_status, resulting_status)

        decided_at = datetime.now(timezone.utc)
        decision = ApprovalDecision(
            decision_id=self._decision_id(),
            request_id=request_id,
            operator_action=operator_action,
            decision_reason=decision_reason,
            decided_at=decided_at,
            prior_status=prior_status,
            resulting_status=resulting_status,
        )
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE approval_requests
                SET status = ?, updated_at = ?, current_step_state = ?
                WHERE request_id = ?
                """,
                (
                    resulting_status.value,
                    decided_at.isoformat(),
                    resulting_status.value,
                    request_id,
                ),
            )
            conn.execute(
                """
                INSERT INTO approval_decisions (
                    decision_id, request_id, operator_action, decision_reason, decided_at, prior_status, resulting_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.decision_id,
                    decision.request_id,
                    decision.operator_action.value,
                    decision.decision_reason,
                    decision.decided_at.isoformat(),
                    decision.prior_status.value,
                    decision.resulting_status.value,
                ),
            )
        return decision

    def list_decisions(
        self,
        *,
        request_id: str | None = None,
        limit: int = 50,
    ) -> list[ApprovalDecision]:
        values: list[str | int] = []
        clauses = ["1=1"]
        if request_id:
            clauses.append("request_id = ?")
            values.append(request_id)
        values.append(limit)
        query = (
            f"SELECT * FROM approval_decisions WHERE {' AND '.join(clauses)} "
            "ORDER BY decided_at DESC LIMIT ?"
        )
        with self._connect() as conn:
            rows = conn.execute(query, tuple(values)).fetchall()
        return [self._row_to_decision(row) for row in rows]

    def approval_summary(
        self,
        *,
        platform: str | None = None,
        mode: str | None = None,
    ) -> dict[str, int]:
        clauses = ["1=1"]
        values: list[str] = []
        if platform:
            clauses.append("platform = ?")
            values.append(platform)
        if mode:
            clauses.append("mode = ?")
            values.append(mode)
        query = (
            f"SELECT status, COUNT(*) AS count FROM approval_requests "
            f"WHERE {' AND '.join(clauses)} GROUP BY status"
        )
        with self._connect() as conn:
            rows = conn.execute(query, tuple(values)).fetchall()
        counts = {row["status"]: int(row["count"]) for row in rows}
        return counts
