from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Optional

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


class TraceStage(str, Enum):
    runtime_observation_collected = "runtime_observation_collected"
    snapshot_collected = "snapshot_collected"
    issues_detected = "issues_detected"
    issues_scored = "issues_scored"
    actions_planned = "actions_planned"
    actions_policy_classified = "actions_policy_classified"
    actions_dispatched = "actions_dispatched"
    actions_executed = "actions_executed"
    actions_verified = "actions_verified"
    approval_requested = "approval_requested"
    approval_decided = "approval_decided"
    execution_blocked_waiting_for_approval = "execution_blocked_waiting_for_approval"


class AuditStage(BaseModel):
    stage: TraceStage
    summary: str
    platform: str
    mode: str
    issue_count: int = 0
    action_count: int = 0
    important_issue_types: List[str] = Field(default_factory=list)
    important_action_types: List[str] = Field(default_factory=list)


class AuditTrail(BaseModel):
    stages: List[AuditStage] = Field(default_factory=list)


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
    recurrence_status: Optional[str] = None
    recurrence_count: int = 0
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    related_event_ids: List[str] = Field(default_factory=list)
    incident_key: Optional[str] = None
    trend_direction: Optional[str] = None
    anomaly_reason: Optional[str] = None
    baseline_summary: Optional[str] = None
    deviation_score: float = 0.0
    anomaly_context: Optional["AnomalyContext"] = None


class HostBaseline(BaseModel):
    platform: str
    mode: str
    hostname: Optional[str] = None
    event_count: int = 0
    avg_cpu_percent: float = 0.0
    avg_memory_used_mb: float = 0.0
    avg_memory_percent: float = 0.0
    avg_disk_usage_percent: float = 0.0
    avg_risk_score: float = 0.0
    avg_health_score: float = 0.0
    healthy_service_names: List[str] = Field(default_factory=list)
    common_process_names: List[str] = Field(default_factory=list)


class BaselineComparison(BaseModel):
    metric: str
    current_value: float | str
    baseline_value: float | str
    delta: float | None = None
    trend: str


class DeviationSignal(BaseModel):
    signal_type: str
    description: str
    severity: str
    current_value: float | str
    baseline_value: float | str
    delta: float | None = None


class AnomalyContext(BaseModel):
    anomaly_reasons: List[str] = Field(default_factory=list)
    deviation_score: float = 0.0
    baseline_comparisons: List[BaselineComparison] = Field(default_factory=list)
    deviation_signals: List[DeviationSignal] = Field(default_factory=list)


class BaselineSummary(BaseModel):
    host_baseline: HostBaseline
    baseline_comparisons: List[BaselineComparison] = Field(default_factory=list)
    deviation_signals: List[DeviationSignal] = Field(default_factory=list)
    anomaly_score: float = 0.0


class IssueSummary(BaseModel):
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    total_count: int = 0


class AllowedCommand(BaseModel):
    command_name: str
    args: List[str] = Field(default_factory=list)
    safety_class: str
    platform: str
    mode: str
    description: Optional[str] = None


class CommandPolicyDecision(BaseModel):
    command_name: str
    args: List[str] = Field(default_factory=list)
    allowed: bool
    reason: str
    safety_class: str
    platform: str
    mode: str


class CommandInvocation(BaseModel):
    invocation_id: str
    task_id: str
    command_name: str
    args: List[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    success: bool = False
    exit_code: Optional[int] = None
    stdout_summary: str = ""
    stderr_summary: str = ""
    parsed_artifact_type: Optional[str] = None
    parsed_artifact_summary: Optional[str] = None


class CommandResult(BaseModel):
    invocation_id: str
    task_id: str
    command_name: str
    args: List[str] = Field(default_factory=list)
    started_at: datetime
    finished_at: datetime
    success: bool
    exit_code: int
    stdout_summary: str
    stderr_summary: str
    parsed_artifact_type: Optional[str] = None
    parsed_artifact_summary: Optional[str] = None


class ObservationTask(BaseModel):
    task_id: str
    task_name: str
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    status: str = "pending"
    status_reason: Optional[str] = None
    command_invocation_ids: List[str] = Field(default_factory=list)
    parsed_artifact_type: Optional[str] = None
    parsed_artifact_summary: Optional[str] = None


class ObservationBatch(BaseModel):
    batch_id: str
    platform: str
    mode: str
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    partial_failure: bool = False
    task_count: int = 0


class RuntimeObservationTrace(BaseModel):
    batch: ObservationBatch
    tasks: List[ObservationTask] = Field(default_factory=list)
    allowed_commands: List[AllowedCommand] = Field(default_factory=list)
    policy_decisions: List[CommandPolicyDecision] = Field(default_factory=list)
    invocations: List[CommandInvocation] = Field(default_factory=list)
    results: List[CommandResult] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


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


class ApprovalStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    denied = "denied"
    expired = "expired"
    cancelled = "cancelled"


class OperatorAction(str, Enum):
    approve = "approve"
    deny = "deny"


class EscalationClass(str, Enum):
    none = "none"
    human_required = "human_required"
    blocked_non_escalatable = "blocked_non_escalatable"


class ApprovalPolicy(BaseModel):
    approval_required: bool
    approval_reason: str
    escalation_class: EscalationClass = EscalationClass.none


class ApprovalRequest(BaseModel):
    request_id: str
    incident_key: str
    playbook_id: str
    step_id: str
    action_id: str
    action_type: str
    target: Optional[str] = None
    platform: str
    mode: str
    risk_tier: Optional[str] = None
    action_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    policy_reason: Optional[str] = None
    justification_summary: str
    current_incident_state: str
    current_step_state: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    status: ApprovalStatus = ApprovalStatus.pending


class ApprovalDecision(BaseModel):
    decision_id: str
    request_id: str
    operator_action: OperatorAction
    decision_reason: str
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    prior_status: ApprovalStatus
    resulting_status: ApprovalStatus


class ApprovalDecisionInput(BaseModel):
    decision_reason: str = Field(min_length=1, max_length=500)


class OperatorDecisionTrace(BaseModel):
    trace_id: str
    event_type: str
    request_id: str
    incident_key: str
    action_id: str
    detail: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ApprovalQueueItem(BaseModel):
    request: ApprovalRequest
    incident_title: Optional[str] = None
    playbook_name: Optional[str] = None
    step_name: Optional[str] = None


class ApprovalRequestDetail(BaseModel):
    request: ApprovalRequest
    decisions: List[ApprovalDecision] = Field(default_factory=list)


class ApprovalSummary(BaseModel):
    pending_count: int = 0
    approved_count: int = 0
    denied_count: int = 0
    expired_count: int = 0
    cancelled_count: int = 0
    total_count: int = 0


class IncidentLifecycleState(str, Enum):
    detected = "detected"
    analyzed = "analyzed"
    planned = "planned"
    approval_pending = "approval_pending"
    approved = "approved"
    denied = "denied"
    expired = "expired"
    blocked = "blocked"
    dispatched = "dispatched"
    executed = "executed"
    verified = "verified"
    failed = "failed"
    closed = "closed"


class NodeType(str, Enum):
    host = "host"
    service = "service"
    process = "process"
    port = "port"
    issue = "issue"
    incident = "incident"
    action = "action"
    strategy = "strategy"


class EdgeType(str, Enum):
    depends_on = "depends_on"
    listens_on = "listens_on"
    targets = "targets"
    contains = "contains"
    executes = "executes"
    related_to = "related_to"


class GraphNode(BaseModel):
    id: str
    type: NodeType
    label: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    severity: Optional[str] = None


class GraphEdge(BaseModel):
    source_id: str
    target_id: str
    type: EdgeType
    description: str


class HostGraph(BaseModel):
    nodes: List[GraphNode] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StepTransition(BaseModel):
    step_id: str
    from_state: IncidentLifecycleState
    to_state: IncidentLifecycleState
    reason: str
    transitioned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class VerificationCheckpoint(BaseModel):
    checkpoint_id: str
    step_id: str
    success_condition: str
    failure_condition: str
    verified: Optional[bool] = None
    reason: Optional[str] = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PlaybookStep(BaseModel):
    step_id: str
    name: str
    description: str
    action_type: Optional[str] = None
    action_id: Optional[str] = None
    target: Optional[str] = None
    success_condition: str
    failure_condition: str
    retryable: bool = False
    next_step_on_success: Optional[str] = None
    next_step_on_failure: Optional[str] = None
    status: str = "pending"
    status_reason: Optional[str] = None
    execution_mode: Optional[str] = None
    approval_required: Optional[bool] = None
    risk_tier: Optional[str] = None
    policy_reason: Optional[str] = None
    checkpoint: Optional[VerificationCheckpoint] = None


class Playbook(BaseModel):
    playbook_id: str
    issue_type: str
    name: str
    description: str
    steps: List[PlaybookStep] = Field(default_factory=list)


class RemediationStrategy(BaseModel):
    incident_key: str
    issue_id: str
    issue_type: str
    severity: str
    priority_score: int
    recurrence_status: Optional[str] = None
    baseline_context: Optional[str] = None
    selection_reason: str
    playbook: Playbook
    candidate_action_ids: List[str] = Field(default_factory=list)


class StrategyCandidate(BaseModel):
    strategy_id: str
    name: str
    description: str
    issue_type: str
    target: str
    ordered_step_ids: List[str] = Field(default_factory=list)
    action_types: List[str] = Field(default_factory=list)
    estimated_risk: float = Field(default=0.0, ge=0.0, le=1.0)
    estimated_approval_burden: float = Field(default=0.0, ge=0.0, le=1.0)
    estimated_execution_feasibility: float = Field(default=0.0, ge=0.0, le=1.0)
    estimated_observability: float = Field(default=0.0, ge=0.0, le=1.0)
    estimated_disruption: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale_summary: str


class StrategyScore(BaseModel):
    severity_alignment: float = 0.0
    confidence_support: float = 0.0
    recurrence_pressure: float = 0.0
    chronicity_pressure: float = 0.0
    baseline_deviation_support: float = 0.0
    approval_cost: float = 0.0
    disruption_cost: float = 0.0
    execution_feasibility: float = 0.0
    observability_gain: float = 0.0
    risk_fit: float = 0.0
    total_score: float = 0.0
    dimension_reasons: dict[str, str] = Field(default_factory=dict)


class StrategyTradeoff(BaseModel):
    dimension: str
    impact: str
    value: float
    reason: str


class StrategyEvaluationContext(BaseModel):
    issue_id: str
    incident_key: Optional[str] = None
    issue_type: str
    severity: str
    confidence: float
    recurrence_status: Optional[str] = None
    recurrence_count: int = 0
    deviation_score: float = 0.0
    priority_score: int = 0
    platform: str
    mode: str
    current_incident_state: Optional[str] = None


class StrategyDecisionTrace(BaseModel):
    rank: int
    strategy: StrategyCandidate
    score: StrategyScore
    decision_reason: str
    tradeoffs: List[StrategyTradeoff] = Field(default_factory=list)


class StrategySelection(BaseModel):
    issue_id: str
    incident_key: Optional[str] = None
    selected_strategy_id: str
    selected_strategy: StrategyCandidate
    ranked_candidates: List[StrategyDecisionTrace] = Field(default_factory=list)
    winning_reason: str
    rejected_reasons: dict[str, str] = Field(default_factory=dict)
    evaluation_context: StrategyEvaluationContext


class IncidentState(BaseModel):
    incident_key: str
    issue_id: Optional[str] = None
    issue_type: str
    current_state: IncidentLifecycleState
    previous_state: Optional[IncidentLifecycleState] = None
    allowed_transitions: List[IncidentLifecycleState] = Field(default_factory=list)
    transition_reason: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    transitions: List[StepTransition] = Field(default_factory=list)


class PlaybookExecution(BaseModel):
    incident_key: str
    issue_id: Optional[str] = None
    playbook_id: str
    current_step_id: Optional[str] = None
    completed_step_ids: List[str] = Field(default_factory=list)
    failed_step_ids: List[str] = Field(default_factory=list)
    blocked_step_ids: List[str] = Field(default_factory=list)
    verification_checkpoints: List[VerificationCheckpoint] = Field(default_factory=list)
    current_state: IncidentLifecycleState
    previous_state: Optional[IncidentLifecycleState] = None
    allowed_transitions: List[IncidentLifecycleState] = Field(default_factory=list)
    transition_reason: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    transitions: List[StepTransition] = Field(default_factory=list)


class VerificationResult(BaseModel):
    action_id: str
    issue_id: Optional[str] = None
    action_type: str
    verified: bool
    reason: str
    verification_basis: Optional[str] = None
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
    execution_message: str
    execution_stage: str
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    dispatch_reason: Optional[str] = None


class DecisionTraceEntry(BaseModel):
    stage: str
    subject_type: str
    subject_id: Optional[str] = None
    reason: str
    detail: Optional[str] = None


class TraceBundle(BaseModel):
    entries: List[DecisionTraceEntry] = Field(default_factory=list)


class HistoryEventSummary(BaseModel):
    event_id: str
    event_type: str
    platform: str
    mode: str
    created_at: datetime
    health_score: int
    risk_score: int
    issue_count: int


class HistoryEventDetail(HistoryEventSummary):
    payload: dict


class IncidentSummary(BaseModel):
    incident_key: str
    incident_title: str
    issue_type: str
    target: str
    platform: str
    severity_summary: str
    recurrence_count: int
    last_seen_at: datetime
    related_event_ids: List[str] = Field(default_factory=list)
    recommended_attention_level: str
    trend_direction: str


class IncidentDetail(IncidentSummary):
    related_events: List[HistoryEventSummary] = Field(default_factory=list)
    incident_state: Optional[IncidentState] = None
    remediation_strategy: Optional[RemediationStrategy] = None
    strategy_selection: Optional[StrategySelection] = None
    playbook_execution: Optional[PlaybookExecution] = None
    approval_requests: List[ApprovalRequest] = Field(default_factory=list)
    approval_decisions: List[ApprovalDecision] = Field(default_factory=list)


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
    baseline_summary: Optional[BaselineSummary] = None
    runtime_observation_trace: Optional[RuntimeObservationTrace] = None
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PlanResponse(BaseModel):
    snapshot: StateSnapshot
    candidate_actions: List[Action] = Field(default_factory=list)
    allowed_actions: List[Action] = Field(default_factory=list)
    approval_required_actions: List[Action] = Field(default_factory=list)
    blocked_actions: List[Action] = Field(default_factory=list)
    remediation_strategies: List[RemediationStrategy] = Field(default_factory=list)
    strategy_selections: List[StrategySelection] = Field(default_factory=list)
    incident_states: List[IncidentState] = Field(default_factory=list)
    approvals: List[ApprovalQueueItem] = Field(default_factory=list)
    approval_summary: ApprovalSummary = Field(default_factory=ApprovalSummary)
    operator_decision_trace: List[OperatorDecisionTrace] = Field(default_factory=list)
    decision_trace: List[DecisionTraceEntry] = Field(default_factory=list)
    audit_trail: AuditTrail = Field(default_factory=AuditTrail)


class DispatchResult(BaseModel):
    executed_actions: List[ExecutionResult] = Field(default_factory=list)
    actions: List[Action] = Field(default_factory=list)


class ExecuteResponse(BaseModel):
    snapshot: StateSnapshot
    candidate_actions: List[Action] = Field(default_factory=list)
    allowed_actions: List[Action] = Field(default_factory=list)
    approval_required_actions: List[Action] = Field(default_factory=list)
    blocked_actions: List[Action] = Field(default_factory=list)
    remediation_strategies: List[RemediationStrategy] = Field(default_factory=list)
    strategy_selections: List[StrategySelection] = Field(default_factory=list)
    incident_states: List[IncidentState] = Field(default_factory=list)
    playbook_executions: List[PlaybookExecution] = Field(default_factory=list)
    approvals: List[ApprovalQueueItem] = Field(default_factory=list)
    approval_summary: ApprovalSummary = Field(default_factory=ApprovalSummary)
    operator_decision_trace: List[OperatorDecisionTrace] = Field(default_factory=list)
    execution_halted_by_approval: bool = False
    approval_halt_reasons: List[str] = Field(default_factory=list)
    dispatch: DispatchResult
    verification_results: List[VerificationResult] = Field(default_factory=list)
    decision_trace: List[DecisionTraceEntry] = Field(default_factory=list)
    audit_trail: AuditTrail = Field(default_factory=AuditTrail)
