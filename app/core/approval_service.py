from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.approval_policy import ApprovalPolicyEngine
from app.core.approval_repository import (
    ApprovalRepository,
    InvalidApprovalTransitionError,
)
from app.models.schemas import (
    Action,
    ApprovalDecision,
    ApprovalPolicy,
    ApprovalQueueItem,
    ApprovalRequest,
    ApprovalRequestDetail,
    ApprovalStatus,
    ApprovalSummary,
    IncidentState,
    OperatorAction,
    OperatorDecisionTrace,
    PlaybookStep,
    RemediationStrategy,
)


class ApprovalService:
    def __init__(
        self,
        repository: ApprovalRepository | None = None,
        policy_engine: ApprovalPolicyEngine | None = None,
    ) -> None:
        self.repository = repository or ApprovalRepository()
        self.policy_engine = policy_engine or ApprovalPolicyEngine()

    def _build_trace(
        self,
        *,
        event_type: str,
        request: ApprovalRequest,
        detail: str,
        created_at: datetime | None = None,
    ) -> OperatorDecisionTrace:
        return OperatorDecisionTrace(
            trace_id=f"{request.request_id}:{event_type}:{int((created_at or datetime.now(timezone.utc)).timestamp())}",
            event_type=event_type,
            request_id=request.request_id,
            incident_key=request.incident_key,
            action_id=request.action_id,
            detail=detail,
            created_at=created_at or datetime.now(timezone.utc),
        )

    def _step_lookup(self, strategies: list[RemediationStrategy]) -> dict[str, tuple[RemediationStrategy, PlaybookStep]]:
        lookup: dict[str, tuple[RemediationStrategy, PlaybookStep]] = {}
        for strategy in strategies:
            for step in strategy.playbook.steps:
                if step.action_id:
                    lookup[step.action_id] = (strategy, step)
        return lookup

    def _incident_state_lookup(self, incident_states: list[IncidentState]) -> dict[str, IncidentState]:
        return {state.incident_key: state for state in incident_states}

    def _request_justification(
        self,
        *,
        strategy: RemediationStrategy,
        step: PlaybookStep,
        action: Action,
        approval_policy: ApprovalPolicy,
    ) -> str:
        return (
            f"{approval_policy.approval_reason} "
            f"Issue={strategy.issue_type}, step={step.step_id}, risk={action.risk_tier}, "
            f"confidence={action.action_confidence}."
        )

    def ensure_requests_for_strategies(
        self,
        *,
        strategies: list[RemediationStrategy],
        incident_states: list[IncidentState],
        actions: list[Action],
        platform: str,
        mode: str,
    ) -> tuple[list[ApprovalRequest], list[OperatorDecisionTrace], dict[str, ApprovalStatus]]:
        self.repository.expire_outdated_pending()
        action_by_id = {action.id: action for action in actions}
        state_lookup = self._incident_state_lookup(incident_states)
        requests: dict[str, ApprovalRequest] = {}
        traces: list[OperatorDecisionTrace] = []
        approval_status_by_action_id: dict[str, ApprovalStatus] = {}

        for strategy in strategies:
            incident_state = state_lookup.get(strategy.incident_key)
            incident_state_text = incident_state.current_state.value if incident_state else "planned"

            for step in strategy.playbook.steps:
                if not step.action_id:
                    continue
                action = action_by_id.get(step.action_id)
                if action is None:
                    continue

                approval_policy = self.policy_engine.evaluate(
                    action=action,
                    platform=platform,
                    mode=mode,
                    step=step,
                )
                if not approval_policy.approval_required:
                    continue

                existing = self.repository.get_latest_for_action(
                    incident_key=strategy.incident_key,
                    playbook_id=strategy.playbook.playbook_id,
                    step_id=step.step_id,
                    action_id=action.id,
                )
                if existing is None:
                    expires_at = datetime.now(timezone.utc) + timedelta(hours=8)
                    request = self.repository.build_request(
                        incident_key=strategy.incident_key,
                        playbook_id=strategy.playbook.playbook_id,
                        step_id=step.step_id,
                        action_id=action.id,
                        action_type=action.action_type,
                        target=action.target,
                        platform=platform,
                        mode=mode,
                        risk_tier=action.risk_tier,
                        action_confidence=action.action_confidence,
                        policy_reason=action.policy_reason,
                        justification_summary=self._request_justification(
                            strategy=strategy,
                            step=step,
                            action=action,
                            approval_policy=approval_policy,
                        ),
                        current_incident_state=incident_state_text,
                        current_step_state=step.status,
                        expires_at=expires_at,
                    )
                    created = self.repository.create_request(request)
                    requests[created.request_id] = created
                    approval_status_by_action_id[action.id] = created.status
                    traces.append(
                        self._build_trace(
                            event_type="approval_requested",
                            request=created,
                            detail=created.justification_summary,
                            created_at=created.created_at,
                        )
                    )
                else:
                    requests[existing.request_id] = existing
                    approval_status_by_action_id[action.id] = existing.status

        return list(requests.values()), traces, approval_status_by_action_id

    def approval_status_by_action(
        self,
        strategies: list[RemediationStrategy],
    ) -> dict[str, ApprovalStatus]:
        status_by_action: dict[str, ApprovalStatus] = {}
        for strategy in strategies:
            for step in strategy.playbook.steps:
                if not step.action_id:
                    continue
                latest = self.repository.get_latest_for_action(
                    incident_key=strategy.incident_key,
                    playbook_id=strategy.playbook.playbook_id,
                    step_id=step.step_id,
                    action_id=step.action_id,
                )
                if latest is not None:
                    status_by_action[step.action_id] = latest.status
        return status_by_action

    def gate_actions_for_execution(
        self,
        *,
        actions: list[Action],
        strategies: list[RemediationStrategy],
        incident_states: list[IncidentState],
        platform: str,
        mode: str,
    ) -> tuple[list[Action], list[str], list[OperatorDecisionTrace]]:
        self.repository.expire_outdated_pending()
        step_lookup = self._step_lookup(strategies)
        state_lookup = self._incident_state_lookup(incident_states)
        gated_actions: list[Action] = []
        halt_reasons: list[str] = []
        traces: list[OperatorDecisionTrace] = []

        for action in actions:
            strategy_step = step_lookup.get(action.id)
            if strategy_step is None:
                gated_actions.append(action)
                continue
            strategy, step = strategy_step
            incident_state = state_lookup.get(strategy.incident_key)
            incident_state_text = incident_state.current_state.value if incident_state else "planned"

            approval_policy = self.policy_engine.evaluate(
                action=action,
                platform=platform,
                mode=mode,
                step=step,
            )
            if not approval_policy.approval_required:
                gated_actions.append(action)
                continue

            request = self.repository.get_latest_for_action(
                incident_key=strategy.incident_key,
                playbook_id=strategy.playbook.playbook_id,
                step_id=step.step_id,
                action_id=action.id,
            )
            if request is None:
                expires_at = datetime.now(timezone.utc) + timedelta(hours=8)
                request = self.repository.build_request(
                    incident_key=strategy.incident_key,
                    playbook_id=strategy.playbook.playbook_id,
                    step_id=step.step_id,
                    action_id=action.id,
                    action_type=action.action_type,
                    target=action.target,
                    platform=platform,
                    mode=mode,
                    risk_tier=action.risk_tier,
                    action_confidence=action.action_confidence,
                    policy_reason=action.policy_reason,
                    justification_summary=self._request_justification(
                        strategy=strategy,
                        step=step,
                        action=action,
                        approval_policy=approval_policy,
                    ),
                    current_incident_state=incident_state_text,
                    current_step_state=step.status,
                    expires_at=expires_at,
                )
                request = self.repository.create_request(request)
                traces.append(
                    self._build_trace(
                        event_type="approval_requested",
                        request=request,
                        detail=request.justification_summary,
                        created_at=request.created_at,
                    )
                )

            if request.status == ApprovalStatus.approved:
                gated_actions.append(action)
                traces.append(
                    self._build_trace(
                        event_type="approval_granted",
                        request=request,
                        detail="Approval request is approved; action may proceed to dispatch.",
                    )
                )
                continue

            if request.status == ApprovalStatus.denied:
                reason = f"Execution blocked because approval {request.request_id} was denied."
                halt_reasons.append(reason)
                gated_actions.append(
                    action.model_copy(
                        update={
                            "allowed": False,
                            "execution_mode": "blocked",
                            "dispatch_reason": reason,
                        }
                    )
                )
                traces.append(
                    self._build_trace(
                        event_type="approval_denied",
                        request=request,
                        detail=reason,
                    )
                )
                continue

            if request.status == ApprovalStatus.expired:
                reason = f"Execution blocked because approval {request.request_id} expired."
                halt_reasons.append(reason)
                gated_actions.append(
                    action.model_copy(
                        update={
                            "allowed": False,
                            "execution_mode": "blocked",
                            "dispatch_reason": reason,
                        }
                    )
                )
                traces.append(
                    self._build_trace(
                        event_type="execution_blocked_waiting_for_approval",
                        request=request,
                        detail=reason,
                    )
                )
                continue

            reason = f"Execution blocked waiting for approval request {request.request_id}."
            halt_reasons.append(reason)
            gated_actions.append(
                action.model_copy(
                    update={
                        "allowed": False,
                        "dispatch_reason": reason,
                    }
                )
            )
            traces.append(
                self._build_trace(
                    event_type="execution_blocked_waiting_for_approval",
                    request=request,
                    detail=reason,
                )
            )

        return gated_actions, sorted(set(halt_reasons)), traces

    def list_approvals(
        self,
        *,
        status: ApprovalStatus | None = None,
        platform: str | None = None,
        mode: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ApprovalRequest]:
        self.repository.expire_outdated_pending()
        return self.repository.list_requests(
            status=status,
            platform=platform,
            mode=mode,
            limit=limit,
            offset=offset,
        )

    def list_recent_decisions(self, limit: int = 20) -> list[ApprovalDecision]:
        return self.repository.list_decisions(limit=limit)

    def list_requests_for_incident(self, incident_key: str, limit: int = 50) -> list[ApprovalRequest]:
        self.repository.expire_outdated_pending()
        return self.repository.list_requests_for_incident(incident_key, limit=limit)

    def list_decisions_for_request(self, request_id: str, limit: int = 50) -> list[ApprovalDecision]:
        return self.repository.list_decisions(request_id=request_id, limit=limit)

    def get_request_detail(self, request_id: str) -> ApprovalRequestDetail | None:
        self.repository.expire_outdated_pending()
        request = self.repository.get_request(request_id)
        if request is None:
            return None
        decisions = self.repository.list_decisions(request_id=request_id, limit=50)
        return ApprovalRequestDetail(request=request, decisions=decisions)

    def approve_request(self, request_id: str, decision_reason: str) -> tuple[ApprovalDecision, OperatorDecisionTrace]:
        decision = self.repository.decide(
            request_id=request_id,
            operator_action=OperatorAction.approve,
            decision_reason=decision_reason,
        )
        request = self.repository.get_request(request_id)
        if request is None:
            raise KeyError(f"Approval request {request_id} not found after decision.")
        trace = self._build_trace(
            event_type="approval_granted",
            request=request,
            detail=decision.decision_reason,
            created_at=decision.decided_at,
        )
        return decision, trace

    def deny_request(self, request_id: str, decision_reason: str) -> tuple[ApprovalDecision, OperatorDecisionTrace]:
        decision = self.repository.decide(
            request_id=request_id,
            operator_action=OperatorAction.deny,
            decision_reason=decision_reason,
        )
        request = self.repository.get_request(request_id)
        if request is None:
            raise KeyError(f"Approval request {request_id} not found after decision.")
        trace = self._build_trace(
            event_type="approval_denied",
            request=request,
            detail=decision.decision_reason,
            created_at=decision.decided_at,
        )
        return decision, trace

    def summary(self, *, platform: str | None = None, mode: str | None = None) -> ApprovalSummary:
        counts = self.repository.approval_summary(platform=platform, mode=mode)
        return ApprovalSummary(
            pending_count=counts.get(ApprovalStatus.pending.value, 0),
            approved_count=counts.get(ApprovalStatus.approved.value, 0),
            denied_count=counts.get(ApprovalStatus.denied.value, 0),
            expired_count=counts.get(ApprovalStatus.expired.value, 0),
            cancelled_count=counts.get(ApprovalStatus.cancelled.value, 0),
            total_count=sum(counts.values()),
        )

    def queue_items(
        self,
        requests: list[ApprovalRequest],
        *,
        strategies: list[RemediationStrategy] | None = None,
    ) -> list[ApprovalQueueItem]:
        strategy_lookup: dict[tuple[str, str], RemediationStrategy] = {}
        if strategies:
            for strategy in strategies:
                strategy_lookup[(strategy.incident_key, strategy.playbook.playbook_id)] = strategy

        queue_items: list[ApprovalQueueItem] = []
        for request in requests:
            strategy = strategy_lookup.get((request.incident_key, request.playbook_id))
            step_name = None
            playbook_name = None
            incident_title = None
            if strategy is not None:
                playbook_name = strategy.playbook.name
                incident_title = f"{strategy.issue_type} on {request.target or 'target'}"
                for step in strategy.playbook.steps:
                    if step.step_id == request.step_id:
                        step_name = step.name
                        break
            queue_items.append(
                ApprovalQueueItem(
                    request=request,
                    incident_title=incident_title,
                    playbook_name=playbook_name,
                    step_name=step_name,
                )
            )
        return queue_items
