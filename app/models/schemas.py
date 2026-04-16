from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field


class SystemInfo(BaseModel):
    hostname: str
    os_name: str
    os_version: str
    uptime_seconds: int


class ResourceUsage(BaseModel):
    cpu_percent: float
    memory_total_mb: int
    memory_used_mb: int
    disk_total_gb: float
    disk_used_gb: float
    disk_usage_percent: float


class ProcessInfo(BaseModel):
    pid: int
    name: str
    cpu_percent: float
    memory_mb: float
    status: str


class ServiceInfo(BaseModel):
    name: str
    status: str
    description: str
    restart_count: int = 0


class Issue(BaseModel):
    id: str
    type: str
    category: str
    description: str
    target: Optional[str] = None
    severity: str = "low"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    priority_score: int = Field(default=10, ge=0, le=100)
    evidence: List[str] = Field(default_factory=list)
    detection_reason: Optional[str] = None
    severity_reason: Optional[str] = None
    confidence_reason: Optional[str] = None


class IssueSummary(BaseModel):
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    total_count: int = 0


class Action(BaseModel):
    id: str
    action_type: str
    issue_id: Optional[str] = None
    target: Optional[str] = None
    description: str
    planning_reason: Optional[str] = None
    allowed: Optional[bool] = None
    risk_tier: Optional[str] = None
    action_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    approval_required: Optional[bool] = None
    execution_mode: Optional[str] = None
    policy_reason: Optional[str] = None
    dispatch_reason: Optional[str] = None
    reason: Optional[str] = None


class VerificationResult(BaseModel):
    action_id: str
    issue_id: Optional[str] = None
    action_type: str
    verified: bool
    reason: str
    verified_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExecutionResult(BaseModel):
    action_id: str
    issue_id: Optional[str] = None
    action_type: str
    target: Optional[str] = None
    allowed: bool
    executed: bool
    success: bool
    message: str
    dispatch_reason: Optional[str] = None
    dispatch_reason: Optional[str] = None


class DecisionTraceEntry(BaseModel):
    stage: str
    subject_type: str
    subject_id: Optional[str] = None
    reason: str
    detail: Optional[str] = None


class TraceBundle(BaseModel):
    entries: List[DecisionTraceEntry] = Field(default_factory=list)


class StateSnapshot(BaseModel):
    system_info: SystemInfo
    resources: ResourceUsage
    processes: List[ProcessInfo] = Field(default_factory=list)
    services: List[ServiceInfo] = Field(default_factory=list)
    open_ports: List[int] = Field(default_factory=list)
    recent_logs: List[str] = Field(default_factory=list)
    issues: List[Issue] = Field(default_factory=list)
    health_score: int = Field(default=100, ge=0, le=100)
    risk_score: int = Field(default=0, ge=0, le=100)
    issue_summary: IssueSummary = Field(default_factory=IssueSummary)
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PlanResponse(BaseModel):
    snapshot: StateSnapshot
    candidate_actions: List[Action] = Field(default_factory=list)
    allowed_actions: List[Action] = Field(default_factory=list)
    approval_required_actions: List[Action] = Field(default_factory=list)
    blocked_actions: List[Action] = Field(default_factory=list)
    decision_trace: List[DecisionTraceEntry] = Field(default_factory=list)


class DispatchResult(BaseModel):
    executed_actions: List[ExecutionResult] = Field(default_factory=list)
    actions: List[Action] = Field(default_factory=list)


class ExecuteResponse(BaseModel):
    snapshot: StateSnapshot
    candidate_actions: List[Action] = Field(default_factory=list)
    allowed_actions: List[Action] = Field(default_factory=list)
    approval_required_actions: List[Action] = Field(default_factory=list)
    blocked_actions: List[Action] = Field(default_factory=list)
    dispatch: DispatchResult
    verification_results: List[VerificationResult] = Field(default_factory=list)
    decision_trace: List[DecisionTraceEntry] = Field(default_factory=list)
