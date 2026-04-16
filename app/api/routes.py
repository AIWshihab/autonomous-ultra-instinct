from fastapi import APIRouter, HTTPException

from app.core.dispatcher import Dispatcher
from app.core.planner import Planner
from app.core.policy_engine import PolicyEngine
from app.core.state_manager import InvalidModeError, InvalidPlatformError, StateManager
from app.core.verifier import Verifier
from app.models.schemas import (
    DecisionTraceEntry,
    ExecuteResponse,
    PlanResponse,
    StateSnapshot,
)

router = APIRouter()
state_manager = StateManager()
planner = Planner()
policy_engine = PolicyEngine()
dispatcher = Dispatcher()
verifier = Verifier()


def _collect_snapshot_for_request(platform: str | None, mode: str | None) -> StateSnapshot:
    try:
        return state_manager.collect_snapshot(platform=platform, mode=mode)
    except (InvalidPlatformError, InvalidModeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _build_plan_trace(snapshot: StateSnapshot, actions: list[object]) -> list[DecisionTraceEntry]:
    trace: list[DecisionTraceEntry] = []

    for issue in snapshot.issues:
        detail = "; ".join(issue.evidence) if issue.evidence else None
        trace.append(
            DecisionTraceEntry(
                stage="detection",
                subject_type="issue",
                subject_id=issue.id,
                reason=issue.detection_reason or f"Detected issue {issue.type}.",
                detail=detail,
            )
        )

    for action in actions:
        trace.append(
            DecisionTraceEntry(
                stage="planning",
                subject_type="action",
                subject_id=action.id,
                reason=action.planning_reason or f"Planned action {action.action_type}.",
                detail=f"Issue {action.issue_id} -> {action.action_type}",
            )
        )
        trace.append(
            DecisionTraceEntry(
                stage="policy",
                subject_type="action",
                subject_id=action.id,
                reason=action.policy_reason or f"Policy evaluated action {action.action_type}.",
                detail=f"allowed={action.allowed}, mode={action.execution_mode}",
            )
        )

    return trace


def _build_execute_trace(
    snapshot: StateSnapshot,
    actions: list[object],
    dispatch_result,
    verification_results,
) -> list[DecisionTraceEntry]:
    trace = _build_plan_trace(snapshot, actions)

    for action in dispatch_result.actions:
        trace.append(
            DecisionTraceEntry(
                stage="dispatch",
                subject_type="action",
                subject_id=action.id,
                reason=action.dispatch_reason or "Dispatch decision recorded.",
                detail=f"allowed={action.allowed}, execution_mode={action.execution_mode}",
            )
        )

    for execution in dispatch_result.executed_actions:
        trace.append(
            DecisionTraceEntry(
                stage="execution",
                subject_type="execution",
                subject_id=execution.action_id,
                reason=execution.message,
                detail=execution.dispatch_reason,
            )
        )

    for verification in verification_results:
        trace.append(
            DecisionTraceEntry(
                stage="verification",
                subject_type="execution",
                subject_id=verification.action_id,
                reason=verification.reason,
            )
        )

    return trace


@router.get("/snapshot", response_model=StateSnapshot, tags=["snapshot"])
async def get_snapshot(platform: str | None = None, mode: str | None = None):
    return _collect_snapshot_for_request(platform, mode)


@router.get("/plan", response_model=PlanResponse, tags=["planning"])
async def get_plan(platform: str | None = None, mode: str | None = None):
    snapshot = _collect_snapshot_for_request(platform, mode)
    candidate_actions = planner.plan(snapshot.issues)
    evaluated_actions = policy_engine.evaluate_actions(
        candidate_actions,
        platform=platform or state_manager.default_platform,
        mode=mode or state_manager.default_mode,
    )
    allowed_actions = policy_engine.allowed_actions(evaluated_actions)
    decision_trace = _build_plan_trace(snapshot, evaluated_actions)

    return PlanResponse(
        snapshot=snapshot,
        candidate_actions=evaluated_actions,
        allowed_actions=allowed_actions,
        approval_required_actions=policy_engine.approval_required_actions(evaluated_actions),
        blocked_actions=policy_engine.blocked_actions(evaluated_actions),
        decision_trace=decision_trace,
    )


@router.get("/execute", response_model=ExecuteResponse, tags=["execution"])
async def get_execute(platform: str | None = None, mode: str | None = None):
    snapshot = _collect_snapshot_for_request(platform, mode)
    candidate_actions = planner.plan(snapshot.issues)
    evaluated_actions = policy_engine.evaluate_actions(
        candidate_actions,
        platform=platform or state_manager.default_platform,
        mode=mode or state_manager.default_mode,
    )
    allowed_actions = policy_engine.allowed_actions(evaluated_actions)
    dispatch_result = dispatcher.dispatch(evaluated_actions)
    verification_results = [
        verifier.verify(execution_result) for execution_result in dispatch_result.executed_actions
    ]
    decision_trace = _build_execute_trace(snapshot, evaluated_actions, dispatch_result, verification_results)

    return ExecuteResponse(
        snapshot=snapshot,
        candidate_actions=dispatch_result.actions,
        allowed_actions=allowed_actions,
        approval_required_actions=policy_engine.approval_required_actions(evaluated_actions),
        blocked_actions=policy_engine.blocked_actions(evaluated_actions),
        dispatch=dispatch_result,
        verification_results=verification_results,
        decision_trace=decision_trace,
    )
