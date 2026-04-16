from fastapi import APIRouter, HTTPException

from app.core.approval_repository import ApprovalRepository, InvalidApprovalTransitionError
from app.core.approval_service import ApprovalService
from app.core.baseline_service import BaselineService
from app.core.correlation_service import CorrelationService
from app.core.dispatcher import Dispatcher
from app.core.history_service import HistoryService
from app.core.planner import Planner
from app.core.policy_engine import PolicyEngine
from app.core.runtime_observation_repository import RuntimeObservationRepository
from app.core.runtime_observation_service import RuntimeObservationService
from app.core.state_manager import InvalidModeError, InvalidPlatformError, StateManager
from app.core.verifier import Verifier
from app.models.schemas import (
    Action,
    ApprovalDecision,
    ApprovalDecisionInput,
    ApprovalQueueItem,
    ApprovalRequest,
    ApprovalRequestDetail,
    ApprovalStatus,
    ApprovalSummary,
    AuditStage,
    AuditTrail,
    BaselineSummary,
    CommandResult,
    DecisionTraceEntry,
    ExecuteResponse,
    HostBaseline,
    HistoryEventDetail,
    HistoryEventSummary,
    IncidentDetail,
    IncidentState,
    IncidentSummary,
    OperatorDecisionTrace,
    PlanResponse,
    Playbook,
    PlaybookExecution,
    RemediationStrategy,
    RuntimeObservationTrace,
    StateSnapshot,
    TraceStage,
    VerificationResult,
)

router = APIRouter()
state_manager = StateManager()
planner = Planner()
playbook_engine = planner.playbook_engine
policy_engine = PolicyEngine()
dispatcher = Dispatcher()
verifier = Verifier()
history_service = HistoryService()
runtime_observation_repository = RuntimeObservationRepository(db_path=history_service.repository.db_path)
runtime_observation_service = RuntimeObservationService(repository=runtime_observation_repository)
baseline_service = BaselineService(repository=history_service.repository)
correlation_service = CorrelationService(repository=history_service.repository)
approval_service = ApprovalService(
    repository=ApprovalRepository(db_path=history_service.repository.db_path)
)
macos_adapter = state_manager.adapters.get("macos")
if macos_adapter is not None and hasattr(macos_adapter, "runtime_observation_service"):
    macos_adapter.runtime_observation_service = runtime_observation_service


def _collect_snapshot_for_request(platform: str | None, mode: str | None) -> StateSnapshot:
    try:
        return state_manager.collect_snapshot(platform=platform, mode=mode)
    except (InvalidPlatformError, InvalidModeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _distinct_strings(values: list[str]) -> list[str]:
    return sorted(set(values))


def _build_plan_trace(snapshot: StateSnapshot, actions: list[Action], platform: str, mode: str) -> list[DecisionTraceEntry]:
    trace: list[DecisionTraceEntry] = []
    issue_types = _distinct_strings([issue.type for issue in snapshot.issues])
    action_types = _distinct_strings([action.action_type for action in actions])

    if snapshot.runtime_observation_trace is not None:
        runtime_trace = snapshot.runtime_observation_trace
        trace.append(
            DecisionTraceEntry(
                stage=TraceStage.runtime_observation_collected,
                subject_type="runtime_observation",
                subject_id=runtime_trace.batch.batch_id,
                reason="Governed runtime observation tasks were executed through strict command policy.",
                detail=(
                    f"tasks={len(runtime_trace.tasks)}, commands={len(runtime_trace.results)}, "
                    f"partial_failure={runtime_trace.batch.partial_failure}"
                ),
            )
        )

    trace.append(
        DecisionTraceEntry(
            stage=TraceStage.snapshot_collected,
            subject_type="request",
            subject_id=None,
            reason=f"Snapshot collected for {platform} in {mode} mode.",
            detail=f"{len(snapshot.issues)} issues detected, {len(snapshot.processes)} processes surveyed.",
        )
    )
    trace.append(
        DecisionTraceEntry(
            stage=TraceStage.issues_detected,
            subject_type="request",
            subject_id=None,
            reason="Issue detection completed with concrete evidence and rule-based signals.",
            detail=f"Detected issue types: {', '.join(issue_types) if issue_types else 'none'}.",
        )
    )
    trace.append(
        DecisionTraceEntry(
            stage=TraceStage.issues_scored,
            subject_type="request",
            subject_id=None,
            reason="Issue severity, confidence, and priority scores were assigned deterministically.",
            detail=f"Scored {len(snapshot.issues)} issues with explicit severity and confidence reasons.",
        )
    )

    for issue in snapshot.issues:
        detail = "; ".join(issue.evidence) if issue.evidence else None
        trace.append(
            DecisionTraceEntry(
                stage="issues_detected",
                subject_type="issue",
                subject_id=issue.id,
                reason=issue.detection_reason or f"Detected issue {issue.type}.",
                detail=detail,
            )
        )

    for action in actions:
        trace.append(
            DecisionTraceEntry(
                stage=TraceStage.actions_planned,
                subject_type="action",
                subject_id=action.id,
                reason=action.planning_reason or f"Planned action {action.action_type}.",
                detail=f"Issue {action.issue_id} -> {action.action_type}",
            )
        )
        trace.append(
            DecisionTraceEntry(
                stage=TraceStage.actions_policy_classified,
                subject_type="action",
                subject_id=action.id,
                reason=action.policy_reason or f"Policy classified action {action.action_type}.",
                detail=f"allowed={action.allowed}, execution_mode={action.execution_mode}",
            )
        )

    trace.append(
        DecisionTraceEntry(
            stage=TraceStage.actions_planned,
            subject_type="request",
            subject_id=None,
            reason="Planning phase completed.",
            detail=f"Candidate actions evaluated: {len(action_types)} unique action types.",
        )
    )

    return trace


def _build_audit_stage(
    stage: TraceStage,
    platform: str,
    mode: str,
    summary: str,
    issue_count: int = 0,
    action_count: int = 0,
    important_issue_types: list[str] | None = None,
    important_action_types: list[str] | None = None,
) -> AuditStage:
    return AuditStage(
        stage=stage,
        platform=platform,
        mode=mode,
        summary=summary,
        issue_count=issue_count,
        action_count=action_count,
        important_issue_types=important_issue_types or [],
        important_action_types=important_action_types or [],
    )


def _build_audit_trail(
    snapshot: StateSnapshot,
    actions: list[Action],
    dispatch_result: object | None,
    verification_results: list[VerificationResult],
    platform: str,
    mode: str,
    approval_requests: list[ApprovalRequest] | None = None,
    approval_decisions: list[ApprovalDecision] | None = None,
    execution_halted_by_approval: bool = False,
) -> AuditTrail:
    issue_types = _distinct_strings([issue.type for issue in snapshot.issues])
    action_types = _distinct_strings([action.action_type for action in actions])
    dispatched_types = _distinct_strings([action.action_type for action in dispatch_result.actions]) if dispatch_result is not None else []
    executed_types = _distinct_strings([result.action_type for result in dispatch_result.executed_actions]) if dispatch_result is not None else []
    verified_types = _distinct_strings([result.action_type for result in verification_results])

    stages = [
        _build_audit_stage(
            TraceStage.runtime_observation_collected,
            platform,
            mode,
            (
                "Runtime observation collected via strict allowlisted command orchestration."
                if snapshot.runtime_observation_trace
                else "Runtime command orchestration not used for this snapshot."
            ),
            issue_count=0,
            action_count=(len(snapshot.runtime_observation_trace.results) if snapshot.runtime_observation_trace else 0),
            important_action_types=(
                _distinct_strings([result.command_name for result in snapshot.runtime_observation_trace.results])
                if snapshot.runtime_observation_trace
                else []
            ),
        ),
        _build_audit_stage(
            TraceStage.snapshot_collected,
            platform,
            mode,
            f"Collected snapshot with {len(snapshot.issues)} issues and {len(snapshot.processes)} processes.",
            issue_count=len(snapshot.issues),
            action_count=0,
            important_issue_types=issue_types,
        ),
        _build_audit_stage(
            TraceStage.issues_detected,
            platform,
            mode,
            f"Detected {len(snapshot.issues)} issues by rule-based detectors.",
            issue_count=len(snapshot.issues),
            important_issue_types=issue_types,
        ),
        _build_audit_stage(
            TraceStage.issues_scored,
            platform,
            mode,
            "Assigned severity, confidence, and priority to detected issues.",
            issue_count=len(snapshot.issues),
            important_issue_types=issue_types,
        ),
        _build_audit_stage(
            TraceStage.actions_planned,
            platform,
            mode,
            f"Planned {len(actions)} candidate actions from detected issues.",
            issue_count=len(snapshot.issues),
            action_count=len(actions),
            important_action_types=action_types,
        ),
        _build_audit_stage(
            TraceStage.actions_policy_classified,
            platform,
            mode,
            f"Classified {len(actions)} actions by policy into allowed, approval required, and blocked groups.",
            issue_count=len(snapshot.issues),
            action_count=len(actions),
            important_action_types=action_types,
        ),
    ]

    approval_requests = approval_requests or []
    approval_decisions = approval_decisions or []
    if approval_requests:
        stages.append(
            _build_audit_stage(
                TraceStage.approval_requested,
                platform,
                mode,
                f"Approval workflow has {len(approval_requests)} tracked request(s).",
                action_count=len(approval_requests),
                important_action_types=_distinct_strings([request.action_type for request in approval_requests]),
            )
        )

    if approval_decisions:
        stages.append(
            _build_audit_stage(
                TraceStage.approval_decided,
                platform,
                mode,
                f"Recorded {len(approval_decisions)} operator approval decision(s).",
                action_count=len(approval_decisions),
                important_action_types=[],
            )
        )

    if execution_halted_by_approval:
        stages.append(
            _build_audit_stage(
                TraceStage.execution_blocked_waiting_for_approval,
                platform,
                mode,
                "Execution was halted because approval-gated actions are pending or not approved.",
                action_count=0,
                important_action_types=[],
            )
        )

    if dispatch_result is not None:
        stages.extend([
            _build_audit_stage(
                TraceStage.actions_dispatched,
                platform,
                mode,
                f"Dispatch evaluated {len(dispatch_result.actions)} actions with policy-aware decisions.",
                action_count=len(dispatch_result.actions),
                important_action_types=dispatched_types,
            ),
            _build_audit_stage(
                TraceStage.actions_executed,
                platform,
                mode,
                f"Executed {len(dispatch_result.executed_actions)} allowed simulation actions.",
                action_count=len(dispatch_result.executed_actions),
                important_action_types=executed_types,
            ),
            _build_audit_stage(
                TraceStage.actions_verified,
                platform,
                mode,
                f"Verified outcomes for {len(verification_results)} actions.",
                action_count=len(verification_results),
                important_action_types=verified_types,
            ),
        ])

    return AuditTrail(stages=stages)


def _enrich_snapshot_with_baseline(snapshot: StateSnapshot, platform: str, mode: str) -> StateSnapshot:
    baseline = baseline_service.compute_baseline(platform, mode, hostname=snapshot.system_info.hostname)
    baseline_summary = baseline_service.build_baseline_summary(snapshot, baseline)
    enriched_snapshot = snapshot.model_copy(
        update={
            "baseline_summary": baseline_summary,
            "issues": baseline_service.enrich_issues(snapshot.issues, snapshot, baseline_summary),
        }
    )
    return enriched_snapshot


def _build_playbook_plan(
    evaluated_actions: list[Action],
    strategies: list[RemediationStrategy],
    approval_status_by_action_id: dict[str, ApprovalStatus] | None = None,
) -> tuple[list[RemediationStrategy], list[IncidentState]]:
    return playbook_engine.apply_policy_classification(
        strategies,
        evaluated_actions,
        approval_status_by_action_id=approval_status_by_action_id or {},
    )


def _build_playbook_execute(
    strategies: list[RemediationStrategy],
    dispatch_actions: list[Action],
    verification_results: list[VerificationResult],
    approval_status_by_action_id: dict[str, ApprovalStatus] | None = None,
) -> tuple[list[IncidentState], list[PlaybookExecution], list[RemediationStrategy]]:
    return playbook_engine.simulate_execution(
        strategies,
        dispatch_actions,
        verification_results,
        approval_status_by_action_id=approval_status_by_action_id or {},
    )


def _collect_approval_decisions_for_requests(
    requests: list[ApprovalRequest],
) -> list[ApprovalDecision]:
    decisions: list[ApprovalDecision] = []
    for request in requests:
        decisions.extend(approval_service.list_decisions_for_request(request.request_id, limit=10))
    decisions.sort(key=lambda decision: decision.decided_at, reverse=True)
    return decisions


def _operator_trace_to_decision_entries(
    operator_trace: list[OperatorDecisionTrace],
) -> list[DecisionTraceEntry]:
    converted: list[DecisionTraceEntry] = []
    for entry in operator_trace:
        stage = (
            TraceStage.approval_requested
            if entry.event_type == "approval_requested"
            else TraceStage.approval_decided
            if entry.event_type in {"approval_granted", "approval_denied"}
            else TraceStage.execution_blocked_waiting_for_approval
        )
        converted.append(
            DecisionTraceEntry(
                stage=stage,
                subject_type="approval",
                subject_id=entry.request_id,
                reason=entry.detail,
                detail=f"event={entry.event_type}, incident={entry.incident_key}, action={entry.action_id}",
            )
        )
    return converted


def _approval_decisions_to_operator_trace(
    decisions: list[ApprovalDecision],
) -> list[OperatorDecisionTrace]:
    traces: list[OperatorDecisionTrace] = []
    for decision in decisions:
        detail = approval_service.get_request_detail(decision.request_id)
        if detail is None:
            continue
        request = detail.request
        event_type = "approval_granted" if decision.operator_action.value == "approve" else "approval_denied"
        traces.append(
            OperatorDecisionTrace(
                trace_id=f"{decision.decision_id}:{event_type}",
                event_type=event_type,
                request_id=decision.request_id,
                incident_key=request.incident_key,
                action_id=request.action_id,
                detail=decision.decision_reason,
                created_at=decision.decided_at,
            )
        )
    return traces


def _build_incident_detail_playbook(
    incident: IncidentDetail,
) -> tuple[RemediationStrategy | None, IncidentState | None, PlaybookExecution | None]:
    synthetic_issue = next(
        (
            issue
            for issue in state_manager.collect_snapshot(platform=incident.platform, mode="mock").issues
            if issue.type == incident.issue_type
        ),
        None,
    )
    if synthetic_issue is None:
        return None, None, None

    synthetic_issue = synthetic_issue.model_copy(
        update={
            "id": f"incident-{incident.incident_key}",
            "target": incident.target,
            "incident_key": incident.incident_key,
            "severity": incident.severity_summary,
            "recurrence_count": incident.recurrence_count,
            "recurrence_status": "chronic" if incident.recurrence_count >= 3 else "recurring",
        }
    )
    candidate_actions, strategies = planner.plan_with_strategies([synthetic_issue])
    evaluated_actions = policy_engine.evaluate_actions(candidate_actions, platform=incident.platform, mode="mock")
    plan_strategies, _ = _build_playbook_plan(evaluated_actions, strategies)
    approval_status_by_action_id = approval_service.approval_status_by_action(plan_strategies)
    plan_strategies, _ = _build_playbook_plan(
        evaluated_actions,
        plan_strategies,
        approval_status_by_action_id=approval_status_by_action_id,
    )
    incident_states, executions, enriched_strategies = _build_playbook_execute(
        plan_strategies,
        evaluated_actions,
        [],
        approval_status_by_action_id=approval_status_by_action_id,
    )
    strategy = enriched_strategies[0] if enriched_strategies else None
    incident_state = incident_states[0] if incident_states else None
    execution = executions[0] if executions else None
    return strategy, incident_state, execution


def _build_execute_trace(
    snapshot: StateSnapshot,
    actions: list[Action],
    dispatch_result,
    verification_results: list[VerificationResult],
    platform: str,
    mode: str,
) -> list[DecisionTraceEntry]:
    trace = _build_plan_trace(snapshot, actions, platform, mode)

    for action in dispatch_result.actions:
        trace.append(
            DecisionTraceEntry(
                stage=TraceStage.actions_dispatched,
                subject_type="action",
                subject_id=action.id,
                reason=action.dispatch_reason or "Dispatch decision recorded.",
                detail=f"allowed={action.allowed}, execution_mode={action.execution_mode}",
            )
        )

    for execution in dispatch_result.executed_actions:
        trace.append(
            DecisionTraceEntry(
                stage=TraceStage.actions_executed,
                subject_type="execution",
                subject_id=execution.action_id,
                reason=execution.execution_message,
                detail=f"execution_stage={execution.execution_stage}, success={execution.success}",
            )
        )

    for verification in verification_results:
        trace.append(
            DecisionTraceEntry(
                stage=TraceStage.actions_verified,
                subject_type="execution",
                subject_id=verification.action_id,
                reason=verification.reason,
                detail=verification.verification_basis,
            )
        )

    return trace


def _persist_snapshot_event(snapshot: StateSnapshot, platform: str, mode: str) -> None:
    history_service.record_snapshot_event(snapshot, platform, mode)


def _persist_plan_event(plan_response: PlanResponse, platform: str, mode: str) -> None:
    history_service.record_plan_event(plan_response, platform, mode)


def _persist_execute_event(execute_response: ExecuteResponse, platform: str, mode: str) -> None:
    history_service.record_execute_event(execute_response, platform, mode)


@router.get("/snapshot", response_model=StateSnapshot, tags=["snapshot"])
async def get_snapshot(platform: str | None = None, mode: str | None = None):
    normalized_platform = platform or state_manager.default_platform
    normalized_mode = mode or state_manager.default_mode
    snapshot = _collect_snapshot_for_request(platform, mode)
    snapshot = _enrich_snapshot_with_baseline(snapshot, normalized_platform, normalized_mode)
    snapshot = snapshot.model_copy(
        update={
            "issues": correlation_service.enrich_issues(
                snapshot.issues,
                normalized_platform,
                normalized_mode,
                event_snapshot=snapshot.model_dump(),
            )
        }
    )
    _persist_snapshot_event(snapshot, normalized_platform, normalized_mode)
    return snapshot


@router.get("/plan", response_model=PlanResponse, tags=["planning"])
async def get_plan(platform: str | None = None, mode: str | None = None):
    normalized_platform = platform or state_manager.default_platform
    normalized_mode = mode or state_manager.default_mode
    snapshot = _collect_snapshot_for_request(platform, mode)
    snapshot = _enrich_snapshot_with_baseline(snapshot, normalized_platform, normalized_mode)
    snapshot = snapshot.model_copy(
        update={
            "issues": correlation_service.enrich_issues(
                snapshot.issues,
                normalized_platform,
                normalized_mode,
                event_snapshot=snapshot.model_dump(),
            )
        }
    )
    candidate_actions, remediation_strategies = planner.plan_with_strategies(snapshot.issues)
    evaluated_actions = policy_engine.evaluate_actions(
        candidate_actions,
        platform=normalized_platform,
        mode=normalized_mode,
    )
    remediation_strategies, incident_states = _build_playbook_plan(
        evaluated_actions,
        remediation_strategies,
    )
    approval_requests, operator_trace, approval_status_by_action_id = approval_service.ensure_requests_for_strategies(
        strategies=remediation_strategies,
        incident_states=incident_states,
        actions=evaluated_actions,
        platform=normalized_platform,
        mode=normalized_mode,
    )
    remediation_strategies, incident_states = _build_playbook_plan(
        evaluated_actions,
        remediation_strategies,
        approval_status_by_action_id=approval_status_by_action_id,
    )
    allowed_actions = policy_engine.allowed_actions(evaluated_actions)
    pending_requests = approval_service.list_approvals(
        status=ApprovalStatus.pending,
        platform=normalized_platform,
        mode=normalized_mode,
        limit=50,
    )
    approvals = approval_service.queue_items(
        pending_requests,
        strategies=remediation_strategies,
    )
    approval_summary = approval_service.summary(platform=normalized_platform, mode=normalized_mode)
    approval_decisions = _collect_approval_decisions_for_requests(approval_requests)
    decision_operator_trace = _approval_decisions_to_operator_trace(approval_decisions)
    combined_operator_trace = [*operator_trace, *decision_operator_trace]
    decision_trace = _build_plan_trace(
        snapshot,
        evaluated_actions,
        platform=normalized_platform,
        mode=normalized_mode,
    )
    decision_trace.extend(_operator_trace_to_decision_entries(combined_operator_trace))
    audit_trail = _build_audit_trail(
        snapshot,
        evaluated_actions,
        dispatch_result=None,
        verification_results=[],
        platform=normalized_platform,
        mode=normalized_mode,
        approval_requests=approval_requests,
        approval_decisions=approval_decisions,
    )
    plan_response = PlanResponse(
        snapshot=snapshot,
        candidate_actions=evaluated_actions,
        allowed_actions=allowed_actions,
        approval_required_actions=policy_engine.approval_required_actions(evaluated_actions),
        blocked_actions=policy_engine.blocked_actions(evaluated_actions),
        remediation_strategies=remediation_strategies,
        incident_states=incident_states,
        approvals=approvals,
        approval_summary=approval_summary,
        operator_decision_trace=combined_operator_trace,
        decision_trace=decision_trace,
        audit_trail=audit_trail,
    )
    _persist_plan_event(plan_response, normalized_platform, normalized_mode)
    return plan_response


@router.get("/execute", response_model=ExecuteResponse, tags=["execution"])
async def get_execute(platform: str | None = None, mode: str | None = None):
    normalized_platform = platform or state_manager.default_platform
    normalized_mode = mode or state_manager.default_mode
    snapshot = _collect_snapshot_for_request(platform, mode)
    snapshot = _enrich_snapshot_with_baseline(snapshot, normalized_platform, normalized_mode)
    snapshot = snapshot.model_copy(
        update={
            "issues": correlation_service.enrich_issues(
                snapshot.issues,
                normalized_platform,
                normalized_mode,
                event_snapshot=snapshot.model_dump(),
            )
        }
    )
    candidate_actions, remediation_strategies = planner.plan_with_strategies(snapshot.issues)
    evaluated_actions = policy_engine.evaluate_actions(
        candidate_actions,
        platform=normalized_platform,
        mode=normalized_mode,
    )
    remediation_strategies, planned_incident_states = _build_playbook_plan(
        evaluated_actions,
        remediation_strategies,
    )
    approval_requests, plan_operator_trace, approval_status_by_action_id = approval_service.ensure_requests_for_strategies(
        strategies=remediation_strategies,
        incident_states=planned_incident_states,
        actions=evaluated_actions,
        platform=normalized_platform,
        mode=normalized_mode,
    )
    remediation_strategies, planned_incident_states = _build_playbook_plan(
        evaluated_actions,
        remediation_strategies,
        approval_status_by_action_id=approval_status_by_action_id,
    )
    allowed_actions = policy_engine.allowed_actions(evaluated_actions)
    gated_actions, approval_halt_reasons, execute_operator_trace = approval_service.gate_actions_for_execution(
        actions=evaluated_actions,
        strategies=remediation_strategies,
        incident_states=planned_incident_states,
        platform=normalized_platform,
        mode=normalized_mode,
    )
    dispatch_result = dispatcher.dispatch(gated_actions)
    verification_results = [
        verifier.verify(execution_result) for execution_result in dispatch_result.executed_actions
    ]
    approval_status_by_action_id = approval_service.approval_status_by_action(remediation_strategies)
    decision_trace = _build_execute_trace(
        snapshot,
        gated_actions,
        dispatch_result,
        verification_results,
        platform=normalized_platform,
        mode=normalized_mode,
    )
    combined_operator_trace = [*plan_operator_trace, *execute_operator_trace]
    approval_decisions = _collect_approval_decisions_for_requests(approval_requests)
    combined_operator_trace.extend(_approval_decisions_to_operator_trace(approval_decisions))
    decision_trace.extend(_operator_trace_to_decision_entries(combined_operator_trace))
    incident_states, playbook_executions, remediation_strategies = _build_playbook_execute(
        remediation_strategies,
        dispatch_result.actions,
        verification_results,
        approval_status_by_action_id=approval_status_by_action_id,
    )
    if not incident_states:
        incident_states = planned_incident_states
    pending_requests = approval_service.list_approvals(
        status=ApprovalStatus.pending,
        platform=normalized_platform,
        mode=normalized_mode,
        limit=50,
    )
    approvals = approval_service.queue_items(
        pending_requests,
        strategies=remediation_strategies,
    )
    approval_summary = approval_service.summary(platform=normalized_platform, mode=normalized_mode)
    audit_trail = _build_audit_trail(
        snapshot,
        gated_actions,
        dispatch_result=dispatch_result,
        verification_results=verification_results,
        platform=normalized_platform,
        mode=normalized_mode,
        approval_requests=approval_requests,
        approval_decisions=approval_decisions,
        execution_halted_by_approval=bool(approval_halt_reasons),
    )
    execute_response = ExecuteResponse(
        snapshot=snapshot,
        candidate_actions=dispatch_result.actions,
        allowed_actions=allowed_actions,
        approval_required_actions=policy_engine.approval_required_actions(evaluated_actions),
        blocked_actions=policy_engine.blocked_actions(evaluated_actions),
        remediation_strategies=remediation_strategies,
        incident_states=incident_states,
        playbook_executions=playbook_executions,
        approvals=approvals,
        approval_summary=approval_summary,
        operator_decision_trace=combined_operator_trace,
        execution_halted_by_approval=bool(approval_halt_reasons),
        approval_halt_reasons=approval_halt_reasons,
        dispatch=dispatch_result,
        verification_results=verification_results,
        decision_trace=decision_trace,
        audit_trail=audit_trail,
    )
    _persist_execute_event(execute_response, normalized_platform, normalized_mode)
    return execute_response


@router.get("/incidents", response_model=list[IncidentSummary], tags=["incidents"])
async def get_incidents(
    limit: int = 50,
    platform: str | None = None,
    mode: str | None = None,
):
    return correlation_service.list_incidents(limit=limit, platform=platform, mode=mode)


@router.get("/incidents/recent", response_model=list[IncidentSummary], tags=["incidents"])
async def get_recent_incidents(
    limit: int = 10,
    platform: str | None = None,
    mode: str | None = None,
):
    return correlation_service.list_incidents(limit=limit, platform=platform, mode=mode)


@router.get("/baseline/current", response_model=BaselineSummary, tags=["baseline"])
async def get_current_baseline(platform: str | None = None, mode: str | None = None):
    normalized_platform = platform or state_manager.default_platform
    normalized_mode = mode or state_manager.default_mode
    snapshot = _collect_snapshot_for_request(platform, mode)
    baseline = baseline_service.compute_baseline(
        normalized_platform,
        normalized_mode,
        hostname=snapshot.system_info.hostname,
    )
    return baseline_service.build_baseline_summary(snapshot, baseline)


@router.get("/incidents/{incident_key}", response_model=IncidentDetail, tags=["incidents"])
async def get_incident(incident_key: str):
    incident = correlation_service.get_incident(incident_key)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Incident {incident_key} not found.")
    strategy, incident_state, execution = _build_incident_detail_playbook(incident)
    approval_requests = approval_service.list_requests_for_incident(incident_key, limit=100)
    approval_decisions: list[ApprovalDecision] = []
    for request in approval_requests:
        approval_decisions.extend(approval_service.list_decisions_for_request(request.request_id, limit=10))
    approval_decisions.sort(key=lambda decision: decision.decided_at, reverse=True)
    return incident.model_copy(
        update={
            "incident_state": incident_state,
            "remediation_strategy": strategy,
            "playbook_execution": execution,
            "approval_requests": approval_requests,
            "approval_decisions": approval_decisions,
        }
    )


@router.get("/playbooks", response_model=list[Playbook], tags=["playbooks"])
async def get_playbooks():
    return playbook_engine.list_playbooks()


@router.get("/playbooks/{issue_type}", response_model=Playbook, tags=["playbooks"])
async def get_playbook(issue_type: str):
    playbook = playbook_engine.get_playbook(issue_type)
    if playbook is None:
        raise HTTPException(status_code=404, detail=f"No playbook found for issue type '{issue_type.upper()}'.")
    return playbook


@router.get("/runtime/observations/recent", response_model=list[RuntimeObservationTrace], tags=["runtime"])
async def get_recent_runtime_observations(
    limit: int = 20,
    platform: str | None = None,
    mode: str | None = None,
):
    return runtime_observation_service.list_recent_observations(
        limit=limit,
        platform=platform,
        mode=mode,
    )


@router.get("/runtime/observations/{invocation_id}", response_model=CommandResult, tags=["runtime"])
async def get_runtime_observation_invocation(invocation_id: str):
    result = runtime_observation_service.get_invocation_result(invocation_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Runtime observation invocation {invocation_id} not found.")
    return result


@router.get("/approvals", response_model=list[ApprovalQueueItem], tags=["approvals"])
async def get_approvals(
    status: str | None = "pending",
    platform: str | None = None,
    mode: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    status_enum: ApprovalStatus | None = None
    if status:
        try:
            status_enum = ApprovalStatus(status)
        except ValueError as exc:
            valid = ", ".join([value.value for value in ApprovalStatus])
            raise HTTPException(status_code=400, detail=f"Unsupported approval status '{status}'. Valid values: {valid}.") from exc
    approvals = approval_service.list_approvals(
        status=status_enum,
        platform=platform,
        mode=mode,
        limit=limit,
        offset=offset,
    )
    return approval_service.queue_items(approvals)


@router.get("/approvals/recent", response_model=list[ApprovalDecision], tags=["approvals"])
async def get_recent_approval_decisions(limit: int = 20):
    return approval_service.list_recent_decisions(limit=limit)


@router.get("/approvals/{request_id}", response_model=ApprovalRequestDetail, tags=["approvals"])
async def get_approval(request_id: str):
    detail = approval_service.get_request_detail(request_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Approval request {request_id} not found.")
    return detail


@router.post("/approvals/{request_id}/approve", response_model=ApprovalDecision, tags=["approvals"])
async def approve_request(request_id: str, payload: ApprovalDecisionInput):
    try:
        decision, _ = approval_service.approve_request(request_id, payload.decision_reason)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidApprovalTransitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return decision


@router.post("/approvals/{request_id}/deny", response_model=ApprovalDecision, tags=["approvals"])
async def deny_request(request_id: str, payload: ApprovalDecisionInput):
    try:
        decision, _ = approval_service.deny_request(request_id, payload.decision_reason)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidApprovalTransitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return decision


@router.get("/history", response_model=list[HistoryEventSummary], tags=["history"])
async def get_history(
    limit: int = 50,
    offset: int = 0,
    platform: str | None = None,
    mode: str | None = None,
    event_type: str | None = None,
):
    return history_service.list_events(limit=limit, offset=offset, platform=platform, mode=mode, event_type=event_type)


@router.get("/history/recent", response_model=list[HistoryEventSummary], tags=["history"])
async def get_recent_history(
    limit: int = 10,
    platform: str | None = None,
    mode: str | None = None,
    event_type: str | None = None,
):
    return history_service.recent_events(limit=limit, platform=platform, mode=mode, event_type=event_type)


@router.get("/history/{event_id}", response_model=HistoryEventDetail, tags=["history"])
async def get_history_event(event_id: str):
    event = history_service.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"History event {event_id} not found.")
    return event
