from __future__ import annotations

from datetime import datetime, timezone

from app.models.schemas import (
    Action,
    ApprovalStatus,
    IncidentLifecycleState,
    IncidentState,
    Issue,
    Playbook,
    PlaybookExecution,
    PlaybookStep,
    RemediationStrategy,
    StepTransition,
    VerificationCheckpoint,
    VerificationResult,
)


class InvalidStateTransitionError(ValueError):
    pass


class IncidentStateMachine:
    transition_map: dict[IncidentLifecycleState, list[IncidentLifecycleState]] = {
        IncidentLifecycleState.detected: [
            IncidentLifecycleState.analyzed,
            IncidentLifecycleState.blocked,
            IncidentLifecycleState.failed,
        ],
        IncidentLifecycleState.analyzed: [
            IncidentLifecycleState.planned,
            IncidentLifecycleState.blocked,
            IncidentLifecycleState.failed,
        ],
        IncidentLifecycleState.planned: [
            IncidentLifecycleState.approval_pending,
            IncidentLifecycleState.approved,
            IncidentLifecycleState.blocked,
            IncidentLifecycleState.failed,
        ],
        IncidentLifecycleState.approval_pending: [
            IncidentLifecycleState.approved,
            IncidentLifecycleState.denied,
            IncidentLifecycleState.expired,
            IncidentLifecycleState.blocked,
            IncidentLifecycleState.failed,
        ],
        IncidentLifecycleState.denied: [
            IncidentLifecycleState.blocked,
            IncidentLifecycleState.failed,
        ],
        IncidentLifecycleState.expired: [
            IncidentLifecycleState.blocked,
            IncidentLifecycleState.failed,
        ],
        IncidentLifecycleState.approved: [
            IncidentLifecycleState.dispatched,
            IncidentLifecycleState.blocked,
            IncidentLifecycleState.failed,
        ],
        IncidentLifecycleState.blocked: [
            IncidentLifecycleState.approved,
            IncidentLifecycleState.closed,
        ],
        IncidentLifecycleState.dispatched: [
            IncidentLifecycleState.executed,
            IncidentLifecycleState.failed,
        ],
        IncidentLifecycleState.executed: [
            IncidentLifecycleState.verified,
            IncidentLifecycleState.failed,
        ],
        IncidentLifecycleState.verified: [
            IncidentLifecycleState.closed,
            IncidentLifecycleState.failed,
        ],
        IncidentLifecycleState.failed: [
            IncidentLifecycleState.planned,
            IncidentLifecycleState.closed,
        ],
        IncidentLifecycleState.closed: [],
    }

    def allowed_transitions(self, state: IncidentLifecycleState) -> list[IncidentLifecycleState]:
        return list(self.transition_map.get(state, []))

    def transition(
        self,
        *,
        current_state: IncidentLifecycleState,
        to_state: IncidentLifecycleState,
        reason: str,
        step_id: str,
    ) -> StepTransition:
        allowed = self.allowed_transitions(current_state)
        if to_state not in allowed:
            raise InvalidStateTransitionError(
                f"Invalid transition from {current_state.value} to {to_state.value}."
            )
        return StepTransition(
            step_id=step_id,
            from_state=current_state,
            to_state=to_state,
            reason=reason,
            transitioned_at=datetime.now(timezone.utc),
        )


class PlaybookEngine:
    def __init__(self, state_machine: IncidentStateMachine | None = None) -> None:
        self.state_machine = state_machine or IncidentStateMachine()

    def list_playbooks(self) -> list[Playbook]:
        return [playbook.model_copy(deep=True) for playbook in self._playbook_map().values()]

    def get_playbook(self, issue_type: str) -> Playbook | None:
        return self._playbook_map().get(issue_type.upper())

    def build_strategy(self, issue: Issue) -> RemediationStrategy:
        playbook = self.get_playbook(issue.type)
        if playbook is None:
            playbook = self._default_playbook(issue.type)

        recurrence = issue.recurrence_status or "new"
        deviation_hint = (
            f"deviation={issue.deviation_score:.2f}" if issue.deviation_score else "deviation=baseline"
        )
        selection_reason = (
            f"Selected {playbook.playbook_id} for {issue.type} with severity {issue.severity}, "
            f"recurrence {recurrence}, and {deviation_hint}."
        )
        return RemediationStrategy(
            incident_key=issue.incident_key or f"incident:{issue.id}",
            issue_id=issue.id,
            issue_type=issue.type,
            severity=issue.severity,
            priority_score=issue.priority_score,
            recurrence_status=issue.recurrence_status,
            baseline_context=issue.baseline_summary,
            selection_reason=selection_reason,
            playbook=playbook.model_copy(deep=True),
            candidate_action_ids=[],
        )

    def apply_policy_classification(
        self,
        strategies: list[RemediationStrategy],
        evaluated_actions: list[Action],
        approval_status_by_action_id: dict[str, ApprovalStatus] | None = None,
    ) -> tuple[list[RemediationStrategy], list[IncidentState]]:
        actions_by_issue: dict[str, list[Action]] = {}
        for action in evaluated_actions:
            actions_by_issue.setdefault(action.issue_id or "", []).append(action)

        updated_strategies: list[RemediationStrategy] = []
        incident_states: list[IncidentState] = []
        for strategy in strategies:
            issue_actions = actions_by_issue.get(strategy.issue_id, [])
            updated_playbook = self._apply_policy_to_steps(
                strategy.playbook,
                issue_actions,
                approval_status_by_action_id=approval_status_by_action_id or {},
            )
            candidate_action_ids = [action.id for action in issue_actions]
            state = self._build_plan_incident_state(
                strategy,
                issue_actions,
                approval_status_by_action_id=approval_status_by_action_id or {},
            )
            updated_strategies.append(
                strategy.model_copy(
                    update={
                        "playbook": updated_playbook,
                        "candidate_action_ids": candidate_action_ids,
                    }
                )
            )
            incident_states.append(state)

        return updated_strategies, incident_states

    def simulate_execution(
        self,
        strategies: list[RemediationStrategy],
        dispatched_actions: list[Action],
        verification_results: list[VerificationResult],
        approval_status_by_action_id: dict[str, ApprovalStatus] | None = None,
    ) -> tuple[list[IncidentState], list[PlaybookExecution], list[RemediationStrategy]]:
        dispatched_by_issue: dict[str, list[Action]] = {}
        for action in dispatched_actions:
            dispatched_by_issue.setdefault(action.issue_id or "", []).append(action)

        verification_by_action_id = {result.action_id: result for result in verification_results}

        incident_states: list[IncidentState] = []
        executions: list[PlaybookExecution] = []
        enriched_strategies: list[RemediationStrategy] = []

        for strategy in strategies:
            issue_actions = dispatched_by_issue.get(strategy.issue_id, [])
            playbook = self._apply_execution_to_steps(
                strategy.playbook,
                issue_actions,
                verification_by_action_id,
                approval_status_by_action_id=approval_status_by_action_id or {},
            )
            incident_state = self._build_execution_incident_state(
                strategy,
                issue_actions,
                verification_by_action_id,
                approval_status_by_action_id=approval_status_by_action_id or {},
            )
            checkpoints, completed_step_ids, failed_step_ids, blocked_step_ids = self._collect_checkpoints(playbook)
            current_step_id = self._next_open_step_id(playbook)
            execution = PlaybookExecution(
                incident_key=strategy.incident_key,
                issue_id=strategy.issue_id,
                playbook_id=playbook.playbook_id,
                current_step_id=current_step_id,
                completed_step_ids=completed_step_ids,
                failed_step_ids=failed_step_ids,
                blocked_step_ids=blocked_step_ids,
                verification_checkpoints=checkpoints,
                current_state=incident_state.current_state,
                previous_state=incident_state.previous_state,
                allowed_transitions=incident_state.allowed_transitions,
                transition_reason=incident_state.transition_reason,
                updated_at=incident_state.updated_at,
                transitions=incident_state.transitions,
            )
            incident_states.append(incident_state)
            executions.append(execution)
            enriched_strategies.append(strategy.model_copy(update={"playbook": playbook}))

        return incident_states, executions, enriched_strategies

    def _build_plan_incident_state(
        self,
        strategy: RemediationStrategy,
        issue_actions: list[Action],
        approval_status_by_action_id: dict[str, ApprovalStatus],
    ) -> IncidentState:
        transitions: list[StepTransition] = []
        state = IncidentLifecycleState.detected
        previous_state: IncidentLifecycleState | None = None
        transition_reason = "Issue detected by deterministic detector rules."

        def advance(to_state: IncidentLifecycleState, reason: str, step_id: str) -> None:
            nonlocal state, previous_state, transition_reason
            transition = self.state_machine.transition(
                current_state=state,
                to_state=to_state,
                reason=reason,
                step_id=step_id,
            )
            transitions.append(transition)
            previous_state = state
            state = to_state
            transition_reason = reason

        advance(
            IncidentLifecycleState.analyzed,
            "Issue context analyzed for recurrence, severity, and baseline deviations.",
            "analysis",
        )
        advance(
            IncidentLifecycleState.planned,
            f"Playbook {strategy.playbook.playbook_id} selected and steps planned.",
            "planning",
        )

        has_blocked = any(action.execution_mode == "blocked" or action.allowed is not True for action in issue_actions)
        approval_actions = [
            action
            for action in issue_actions
            if action.approval_required is True and action.execution_mode != "blocked"
        ]
        if approval_actions:
            approval_statuses = [
                approval_status_by_action_id.get(action.id, ApprovalStatus.pending)
                for action in approval_actions
            ]
            advance(
                IncidentLifecycleState.approval_pending,
                "Approval-gated steps were detected and routed to operator control.",
                "approval_gate",
            )
            if any(status == ApprovalStatus.denied for status in approval_statuses):
                advance(
                    IncidentLifecycleState.denied,
                    "At least one approval request was denied by an operator.",
                    "approval_decision",
                )
            elif any(status == ApprovalStatus.expired for status in approval_statuses):
                advance(
                    IncidentLifecycleState.expired,
                    "At least one approval request expired before execution.",
                    "approval_expiry",
                )
            elif all(status == ApprovalStatus.approved for status in approval_statuses):
                advance(
                    IncidentLifecycleState.approved,
                    "All approval-gated steps have operator approval.",
                    "approval_decision",
                )
        elif has_blocked:
            advance(
                IncidentLifecycleState.blocked,
                "One or more proposed steps are policy blocked.",
                "policy_gate",
            )
        else:
            advance(
                IncidentLifecycleState.approved,
                "All candidate actions are policy-approved for controlled simulation.",
                "policy_gate",
            )

        return IncidentState(
            incident_key=strategy.incident_key,
            issue_id=strategy.issue_id,
            issue_type=strategy.issue_type,
            current_state=state,
            previous_state=previous_state,
            allowed_transitions=self.state_machine.allowed_transitions(state),
            transition_reason=transition_reason,
            updated_at=datetime.now(timezone.utc),
            transitions=transitions,
        )

    def _build_execution_incident_state(
        self,
        strategy: RemediationStrategy,
        issue_actions: list[Action],
        verification_by_action_id: dict[str, VerificationResult],
        approval_status_by_action_id: dict[str, ApprovalStatus],
    ) -> IncidentState:
        transitions: list[StepTransition] = []
        state = IncidentLifecycleState.detected
        previous_state: IncidentLifecycleState | None = None
        transition_reason = "Issue detected by deterministic detector rules."

        def advance(to_state: IncidentLifecycleState, reason: str, step_id: str) -> None:
            nonlocal state, previous_state, transition_reason
            transition = self.state_machine.transition(
                current_state=state,
                to_state=to_state,
                reason=reason,
                step_id=step_id,
            )
            transitions.append(transition)
            previous_state = state
            state = to_state
            transition_reason = reason

        advance(IncidentLifecycleState.analyzed, "Issue context analyzed before execution.", "analysis")
        advance(
            IncidentLifecycleState.planned,
            f"Playbook {strategy.playbook.playbook_id} selected and staged.",
            "planning",
        )

        blocked_actions = [a for a in issue_actions if a.execution_mode == "blocked" or a.allowed is not True]
        approval_actions = [
            a
            for a in issue_actions
            if a.id in approval_status_by_action_id
            or (a.approval_required is True and a.execution_mode != "blocked")
        ]
        dispatchable_actions = [a for a in issue_actions if a.allowed is True and a.execution_mode != "blocked"]

        if blocked_actions and not dispatchable_actions:
            advance(
                IncidentLifecycleState.blocked,
                "All actionable steps are blocked by policy; execution halted.",
                "policy_gate",
            )
            return IncidentState(
                incident_key=strategy.incident_key,
                issue_id=strategy.issue_id,
                issue_type=strategy.issue_type,
                current_state=state,
                previous_state=previous_state,
                allowed_transitions=self.state_machine.allowed_transitions(state),
                transition_reason=transition_reason,
                updated_at=datetime.now(timezone.utc),
                transitions=transitions,
            )

        if approval_actions:
            approval_statuses = [
                approval_status_by_action_id.get(action.id, ApprovalStatus.pending)
                for action in approval_actions
            ]
            advance(
                IncidentLifecycleState.approval_pending,
                "Execution includes approval-gated steps requiring operator decisions.",
                "approval_gate",
            )
            if any(status == ApprovalStatus.denied for status in approval_statuses):
                advance(
                    IncidentLifecycleState.denied,
                    "Execution halted because an approval request was denied.",
                    "approval_decision",
                )
                advance(
                    IncidentLifecycleState.blocked,
                    "Denied approval routed the incident into blocked state.",
                    "approval_block",
                )
                return IncidentState(
                    incident_key=strategy.incident_key,
                    issue_id=strategy.issue_id,
                    issue_type=strategy.issue_type,
                    current_state=state,
                    previous_state=previous_state,
                    allowed_transitions=self.state_machine.allowed_transitions(state),
                    transition_reason=transition_reason,
                    updated_at=datetime.now(timezone.utc),
                    transitions=transitions,
                )
            if any(status == ApprovalStatus.expired for status in approval_statuses):
                advance(
                    IncidentLifecycleState.expired,
                    "Execution halted because an approval request expired.",
                    "approval_expiry",
                )
                advance(
                    IncidentLifecycleState.blocked,
                    "Expired approval routed the incident into blocked state.",
                    "approval_block",
                )
                return IncidentState(
                    incident_key=strategy.incident_key,
                    issue_id=strategy.issue_id,
                    issue_type=strategy.issue_type,
                    current_state=state,
                    previous_state=previous_state,
                    allowed_transitions=self.state_machine.allowed_transitions(state),
                    transition_reason=transition_reason,
                    updated_at=datetime.now(timezone.utc),
                    transitions=transitions,
                )
            if not all(status == ApprovalStatus.approved for status in approval_statuses):
                return IncidentState(
                    incident_key=strategy.incident_key,
                    issue_id=strategy.issue_id,
                    issue_type=strategy.issue_type,
                    current_state=state,
                    previous_state=previous_state,
                    allowed_transitions=self.state_machine.allowed_transitions(state),
                    transition_reason=transition_reason,
                    updated_at=datetime.now(timezone.utc),
                    transitions=transitions,
                )
            advance(
                IncidentLifecycleState.approved,
                "All approval-gated steps were approved by operators.",
                "approval_decision",
            )
        else:
            advance(
                IncidentLifecycleState.approved,
                "All dispatchable actions are approved for deterministic simulation.",
                "policy_gate",
            )

        if not dispatchable_actions:
            advance(
                IncidentLifecycleState.failed,
                "No dispatchable actions remained after policy evaluation.",
                "dispatch",
            )
            return IncidentState(
                incident_key=strategy.incident_key,
                issue_id=strategy.issue_id,
                issue_type=strategy.issue_type,
                current_state=state,
                previous_state=previous_state,
                allowed_transitions=self.state_machine.allowed_transitions(state),
                transition_reason=transition_reason,
                updated_at=datetime.now(timezone.utc),
                transitions=transitions,
            )

        advance(
            IncidentLifecycleState.dispatched,
            f"Dispatched {len(dispatchable_actions)} actions to simulation executor.",
            "dispatch",
        )

        has_execution_evidence = any(
            action.id in verification_by_action_id for action in dispatchable_actions
        )
        if not has_execution_evidence:
            advance(
                IncidentLifecycleState.failed,
                "Actions were approved but not executed by the simulator.",
                "execution",
            )
            return IncidentState(
                incident_key=strategy.incident_key,
                issue_id=strategy.issue_id,
                issue_type=strategy.issue_type,
                current_state=state,
                previous_state=previous_state,
                allowed_transitions=self.state_machine.allowed_transitions(state),
                transition_reason=transition_reason,
                updated_at=datetime.now(timezone.utc),
                transitions=transitions,
            )

        advance(
            IncidentLifecycleState.executed,
            "Simulation executor reported action outcomes.",
            "execution",
        )

        verification_items = [
            verification_by_action_id[action.id]
            for action in dispatchable_actions
            if action.id in verification_by_action_id
        ]
        if verification_items and all(result.verified for result in verification_items):
            advance(
                IncidentLifecycleState.verified,
                "All simulated actions passed verification checkpoints.",
                "verification",
            )
            advance(
                IncidentLifecycleState.closed,
                "Playbook simulation completed and incident is ready to close.",
                "closure",
            )
        else:
            advance(
                IncidentLifecycleState.failed,
                "One or more actions did not pass verification checkpoints.",
                "verification",
            )

        return IncidentState(
            incident_key=strategy.incident_key,
            issue_id=strategy.issue_id,
            issue_type=strategy.issue_type,
            current_state=state,
            previous_state=previous_state,
            allowed_transitions=self.state_machine.allowed_transitions(state),
            transition_reason=transition_reason,
            updated_at=datetime.now(timezone.utc),
            transitions=transitions,
        )

    def _apply_policy_to_steps(
        self,
        playbook: Playbook,
        issue_actions: list[Action],
        approval_status_by_action_id: dict[str, ApprovalStatus],
    ) -> Playbook:
        action_by_type: dict[str, Action] = {action.action_type: action for action in issue_actions}
        updated_steps: list[PlaybookStep] = []
        for step in playbook.steps:
            if step.action_type is None:
                updated_steps.append(step.model_copy(update={"status": "pending"}))
                continue

            action = action_by_type.get(step.action_type)
            if action is None:
                updated_steps.append(
                    step.model_copy(
                        update={
                            "status": "pending",
                            "status_reason": "Planner did not generate a matching action for this step.",
                        }
                    )
                )
                continue

            approval_status = approval_status_by_action_id.get(action.id)

            if action.execution_mode == "blocked" or action.allowed is not True:
                status = "blocked"
            elif action.approval_required:
                if approval_status == ApprovalStatus.approved:
                    status = "approved"
                elif approval_status == ApprovalStatus.denied:
                    status = "denied"
                elif approval_status == ApprovalStatus.expired:
                    status = "expired"
                else:
                    status = "approval_pending"
            else:
                status = "ready"

            updated_steps.append(
                step.model_copy(
                    update={
                        "status": status,
                        "status_reason": (
                            f"Approval status is {approval_status.value}."
                            if approval_status is not None and action.approval_required
                            else action.policy_reason
                        ),
                        "action_id": action.id,
                        "target": action.target,
                        "execution_mode": action.execution_mode,
                        "approval_required": action.approval_required,
                        "risk_tier": action.risk_tier,
                        "policy_reason": action.policy_reason,
                    }
                )
            )

        return playbook.model_copy(update={"steps": updated_steps})

    def _apply_execution_to_steps(
        self,
        playbook: Playbook,
        issue_actions: list[Action],
        verification_by_action_id: dict[str, VerificationResult],
        approval_status_by_action_id: dict[str, ApprovalStatus],
    ) -> Playbook:
        action_by_id: dict[str, Action] = {action.id: action for action in issue_actions}
        issue_action_ids = set(action_by_id.keys())
        updated_steps: list[PlaybookStep] = []
        for step in playbook.steps:
            checkpoint = self._build_checkpoint_from_step(step)
            if step.action_id and step.action_id in action_by_id:
                action = action_by_id[step.action_id]
                if step.status == "blocked":
                    checkpoint = checkpoint.model_copy(
                        update={
                            "verified": False,
                            "reason": "Blocked by policy and not dispatched.",
                            "updated_at": datetime.now(timezone.utc),
                        }
                    )
                    updated_steps.append(step.model_copy(update={"checkpoint": checkpoint}))
                    continue

                approval_status = approval_status_by_action_id.get(action.id)
                if step.status in {"approval_pending", "denied", "expired", "approved"}:
                    if approval_status == ApprovalStatus.denied:
                        checkpoint = checkpoint.model_copy(
                            update={
                                "verified": False,
                                "reason": "Execution stopped because approval was denied.",
                                "updated_at": datetime.now(timezone.utc),
                            }
                        )
                        updated_steps.append(
                            step.model_copy(
                                update={
                                    "status": "denied",
                                    "status_reason": "Approval denied by operator.",
                                    "checkpoint": checkpoint,
                                }
                            )
                        )
                        continue
                    if approval_status == ApprovalStatus.expired:
                        checkpoint = checkpoint.model_copy(
                            update={
                                "verified": False,
                                "reason": "Execution stopped because approval expired.",
                                "updated_at": datetime.now(timezone.utc),
                            }
                        )
                        updated_steps.append(
                            step.model_copy(
                                update={
                                    "status": "expired",
                                    "status_reason": "Approval request expired before execution.",
                                    "checkpoint": checkpoint,
                                }
                            )
                        )
                        continue
                    if approval_status != ApprovalStatus.approved:
                        checkpoint = checkpoint.model_copy(
                            update={
                                "verified": None,
                                "reason": "Awaiting operator approval.",
                                "updated_at": datetime.now(timezone.utc),
                            }
                        )
                        updated_steps.append(
                            step.model_copy(
                                update={
                                    "status": "approval_pending",
                                    "status_reason": "Waiting for operator approval before execution.",
                                    "checkpoint": checkpoint,
                                }
                            )
                        )
                        continue

                verification = verification_by_action_id.get(action.id)
                if verification:
                    step_status = "verified" if verification.verified else "failed"
                    checkpoint = checkpoint.model_copy(
                        update={
                            "verified": verification.verified,
                            "reason": verification.reason,
                            "updated_at": datetime.now(timezone.utc),
                        }
                    )
                    updated_steps.append(
                        step.model_copy(
                            update={
                                "status": step_status,
                                "status_reason": verification.reason,
                                "checkpoint": checkpoint,
                            }
                        )
                    )
                    continue

                updated_steps.append(
                    step.model_copy(
                        update={
                            "checkpoint": checkpoint.model_copy(
                                update={
                                    "verified": None,
                                    "reason": "Awaiting verification result for dispatched step.",
                                    "updated_at": datetime.now(timezone.utc),
                                }
                            )
                        }
                    )
                )
                continue

            if step.action_type is None and step.step_id.startswith("verify-"):
                related_results = [
                    verification
                    for verification in verification_by_action_id.values()
                    if verification.action_id in issue_action_ids
                ]
                if related_results:
                    all_verified = all(result.verified for result in related_results)
                    reason = (
                        "All relevant action results passed verification."
                        if all_verified
                        else "At least one action result failed verification."
                    )
                    checkpoint = checkpoint.model_copy(
                        update={
                            "verified": all_verified,
                            "reason": reason,
                            "updated_at": datetime.now(timezone.utc),
                        }
                    )
                    status = "verified" if all_verified else "failed"
                    updated_steps.append(
                        step.model_copy(
                            update={
                                "status": status,
                                "status_reason": reason,
                                "checkpoint": checkpoint,
                            }
                        )
                    )
                    continue

            updated_steps.append(step.model_copy(update={"checkpoint": checkpoint}))

        return playbook.model_copy(update={"steps": updated_steps})

    def _build_checkpoint_from_step(self, step: PlaybookStep) -> VerificationCheckpoint:
        if step.checkpoint is not None:
            return step.checkpoint
        return VerificationCheckpoint(
            checkpoint_id=f"{step.step_id}-checkpoint",
            step_id=step.step_id,
            success_condition=step.success_condition,
            failure_condition=step.failure_condition,
            verified=None,
            reason=None,
            updated_at=datetime.now(timezone.utc),
        )

    def _collect_checkpoints(
        self,
        playbook: Playbook,
    ) -> tuple[list[VerificationCheckpoint], list[str], list[str], list[str]]:
        checkpoints: list[VerificationCheckpoint] = []
        completed_step_ids: list[str] = []
        failed_step_ids: list[str] = []
        blocked_step_ids: list[str] = []

        for step in playbook.steps:
            if step.checkpoint:
                checkpoints.append(step.checkpoint)
            if step.status in {"ready", "approval_pending", "pending", "approved", "expired", "denied"}:
                continue
            if step.status in {"verified", "completed"}:
                completed_step_ids.append(step.step_id)
            elif step.status == "blocked":
                blocked_step_ids.append(step.step_id)
            elif step.status == "failed":
                failed_step_ids.append(step.step_id)

        return checkpoints, completed_step_ids, failed_step_ids, blocked_step_ids

    def _next_open_step_id(self, playbook: Playbook) -> str | None:
        for step in playbook.steps:
            if step.status in {"pending", "ready", "approval_pending", "approved"}:
                return step.step_id
        return None

    def _playbook_map(self) -> dict[str, Playbook]:
        return {
            "SERVICE_DOWN": self._service_down_playbook(),
            "PORT_CONFLICT": self._port_conflict_playbook(),
            "DISK_PRESSURE": self._disk_pressure_playbook(),
            "SUSPICIOUS_PROCESS": self._suspicious_process_playbook(),
            "HIGH_RESOURCE_USAGE": self._high_resource_usage_playbook(),
            "CRASH_LOOP": self._crash_loop_playbook(),
        }

    def _service_down_playbook(self) -> Playbook:
        return Playbook(
            playbook_id="service-down-v1",
            issue_type="SERVICE_DOWN",
            name="Service Recovery",
            description="Inspect service posture, collect context, propose restart, then verify service health.",
            steps=[
                PlaybookStep(
                    step_id="inspect-service-health",
                    name="Inspect Service Health",
                    description="Inspect runtime process indicators for the impacted service.",
                    action_type="inspect_process",
                    success_condition="Service process metadata is collected.",
                    failure_condition="Process metadata cannot be collected for the service.",
                    retryable=True,
                    next_step_on_success="inspect-service-logs",
                    next_step_on_failure="close-service-down",
                ),
                PlaybookStep(
                    step_id="inspect-service-logs",
                    name="Inspect Recent Service Logs",
                    description="Collect safe forensic context for service health investigation.",
                    action_type="collect_forensic_snapshot",
                    success_condition="Recent log context is captured.",
                    failure_condition="No usable log context can be collected.",
                    retryable=True,
                    next_step_on_success="propose-restart",
                    next_step_on_failure="propose-restart",
                ),
                PlaybookStep(
                    step_id="propose-restart",
                    name="Propose Service Restart",
                    description="Propose restarting the affected service in controlled simulation mode.",
                    action_type="restart_service",
                    success_condition="Restart action is approved for simulation.",
                    failure_condition="Restart action is blocked by policy.",
                    retryable=False,
                    next_step_on_success="verify-service-running",
                    next_step_on_failure="close-service-down",
                ),
                PlaybookStep(
                    step_id="verify-service-running",
                    name="Verify Service Running",
                    description="Checkpoint to validate service health after restart simulation.",
                    success_condition="Verification reports service remediation success.",
                    failure_condition="Verification indicates unresolved service health.",
                    retryable=False,
                    next_step_on_success="close-service-down",
                    next_step_on_failure="close-service-down",
                ),
                PlaybookStep(
                    step_id="close-service-down",
                    name="Close Or Mark Failed",
                    description="Close the incident if verified, otherwise preserve failed state.",
                    success_condition="Incident is closed after successful verification.",
                    failure_condition="Incident remains open or failed after verification.",
                    retryable=False,
                ),
            ],
        )

    def _port_conflict_playbook(self) -> Playbook:
        return Playbook(
            playbook_id="port-conflict-v1",
            issue_type="PORT_CONFLICT",
            name="Port Conflict Investigation",
            description="Inspect conflict evidence, collect context, and gate high-risk process termination.",
            steps=[
                PlaybookStep(
                    step_id="inspect-port-usage",
                    name="Inspect Port Usage",
                    description="Inspect active listeners for the conflicted port.",
                    action_type="inspect_port_usage",
                    success_condition="Port usage evidence is captured.",
                    failure_condition="Port inspection does not return conflict evidence.",
                    retryable=True,
                    next_step_on_success="identify-conflicting-process",
                    next_step_on_failure="collect-port-evidence",
                ),
                PlaybookStep(
                    step_id="identify-conflicting-process",
                    name="Identify Conflicting Process",
                    description="Inspect process metadata associated with the conflicted port.",
                    action_type="inspect_process",
                    success_condition="Conflicting process identity is discovered.",
                    failure_condition="Conflicting process cannot be determined.",
                    retryable=True,
                    next_step_on_success="collect-port-evidence",
                    next_step_on_failure="collect-port-evidence",
                ),
                PlaybookStep(
                    step_id="collect-port-evidence",
                    name="Collect Safe Evidence",
                    description="Capture forensic context before proposing any disruptive action.",
                    action_type="collect_forensic_snapshot",
                    success_condition="Conflict evidence package is collected.",
                    failure_condition="Evidence package is incomplete.",
                    retryable=True,
                    next_step_on_success="propose-stop-conflicting-process",
                    next_step_on_failure="propose-stop-conflicting-process",
                ),
                PlaybookStep(
                    step_id="propose-stop-conflicting-process",
                    name="Propose Process Stop",
                    description="Propose high-risk process stop and route it through policy gate.",
                    action_type="stop_conflicting_process",
                    success_condition="Action is approved by policy.",
                    failure_condition="Action is blocked or requires escalation.",
                    retryable=False,
                    next_step_on_success="verify-port-healthy",
                    next_step_on_failure="verify-port-healthy",
                ),
                PlaybookStep(
                    step_id="verify-port-healthy",
                    name="Verification Checkpoint",
                    description="Confirm whether port conflict remains after simulated steps.",
                    success_condition="Port conflict verification passes.",
                    failure_condition="Port conflict verification fails or remains unresolved.",
                    retryable=False,
                ),
            ],
        )

    def _disk_pressure_playbook(self) -> Playbook:
        return Playbook(
            playbook_id="disk-pressure-v1",
            issue_type="DISK_PRESSURE",
            name="Disk Pressure Mitigation",
            description="Inspect disk pressure evidence and gate cleanup actions under strict policy.",
            steps=[
                PlaybookStep(
                    step_id="inspect-disk-usage",
                    name="Inspect Disk Usage",
                    description="Inspect processes and pressure indicators linked to disk saturation.",
                    action_type="inspect_process",
                    success_condition="Disk pressure context is collected.",
                    failure_condition="Disk pressure context cannot be collected.",
                    retryable=True,
                    next_step_on_success="collect-disk-evidence",
                    next_step_on_failure="collect-disk-evidence",
                ),
                PlaybookStep(
                    step_id="collect-disk-evidence",
                    name="Collect Disk Evidence",
                    description="Capture conservative forensic data for disk-pressure analysis.",
                    action_type="collect_forensic_snapshot",
                    success_condition="Forensic disk evidence is captured.",
                    failure_condition="Disk evidence capture fails.",
                    retryable=True,
                    next_step_on_success="propose-clear-temp-files",
                    next_step_on_failure="propose-clear-temp-files",
                ),
                PlaybookStep(
                    step_id="propose-clear-temp-files",
                    name="Propose Temp Cleanup",
                    description="Propose clear_temp_files as a high-risk gated action.",
                    action_type="clear_temp_files",
                    success_condition="Cleanup action is approved for execution.",
                    failure_condition="Cleanup action is blocked by policy.",
                    retryable=False,
                    next_step_on_success="verify-disk-pressure",
                    next_step_on_failure="verify-disk-pressure",
                ),
                PlaybookStep(
                    step_id="verify-disk-pressure",
                    name="Verification Checkpoint",
                    description="Verify whether disk pressure indicators improved after simulation.",
                    success_condition="Disk pressure verification passes.",
                    failure_condition="Disk pressure persists after simulated remediation.",
                    retryable=False,
                ),
            ],
        )

    def _suspicious_process_playbook(self) -> Playbook:
        return Playbook(
            playbook_id="suspicious-process-v1",
            issue_type="SUSPICIOUS_PROCESS",
            name="Suspicious Process Containment",
            description="Inspect and collect evidence, then gate containment action behind policy.",
            steps=[
                PlaybookStep(
                    step_id="inspect-suspicious-process",
                    name="Inspect Process",
                    description="Inspect suspicious process metadata and runtime context.",
                    action_type="inspect_process",
                    success_condition="Process metadata is captured.",
                    failure_condition="Process metadata is unavailable.",
                    retryable=True,
                    next_step_on_success="collect-forensic-snapshot",
                    next_step_on_failure="collect-forensic-snapshot",
                ),
                PlaybookStep(
                    step_id="collect-forensic-snapshot",
                    name="Collect Forensic Snapshot",
                    description="Capture forensic evidence bundle for suspicious process review.",
                    action_type="collect_forensic_snapshot",
                    success_condition="Forensic snapshot is collected.",
                    failure_condition="Forensic snapshot collection fails.",
                    retryable=True,
                    next_step_on_success="propose-quarantine",
                    next_step_on_failure="propose-quarantine",
                ),
                PlaybookStep(
                    step_id="propose-quarantine",
                    name="Propose Quarantine",
                    description="Propose quarantine action and elevate high-risk policy handling.",
                    action_type="quarantine_process",
                    success_condition="Quarantine action is approved.",
                    failure_condition="Quarantine action is blocked by policy.",
                    retryable=False,
                    next_step_on_success="verify-containment",
                    next_step_on_failure="verify-containment",
                ),
                PlaybookStep(
                    step_id="verify-containment",
                    name="Verification Checkpoint",
                    description="Verify if suspicious behavior risk is reduced after simulated steps.",
                    success_condition="Containment verification passes.",
                    failure_condition="Suspicious process risk remains unresolved.",
                    retryable=False,
                ),
            ],
        )

    def _high_resource_usage_playbook(self) -> Playbook:
        return Playbook(
            playbook_id="high-resource-v1",
            issue_type="HIGH_RESOURCE_USAGE",
            name="High Resource Usage Response",
            description="Investigate resource spikes, collect evidence, and verify stability recovery.",
            steps=[
                PlaybookStep(
                    step_id="inspect-resource-process",
                    name="Inspect Resource Heavy Process",
                    description="Inspect process metrics causing elevated CPU or memory pressure.",
                    action_type="inspect_process",
                    success_condition="Resource-heavy process metadata is collected.",
                    failure_condition="Unable to inspect resource-heavy process metadata.",
                    retryable=True,
                    next_step_on_success="collect-resource-evidence",
                    next_step_on_failure="collect-resource-evidence",
                ),
                PlaybookStep(
                    step_id="collect-resource-evidence",
                    name="Collect Resource Evidence",
                    description="Collect conservative forensic context for resource trend analysis.",
                    action_type="collect_forensic_snapshot",
                    success_condition="Resource evidence package is captured.",
                    failure_condition="Resource evidence package is unavailable.",
                    retryable=True,
                    next_step_on_success="verify-resource-normalization",
                    next_step_on_failure="verify-resource-normalization",
                ),
                PlaybookStep(
                    step_id="verify-resource-normalization",
                    name="Verification Checkpoint",
                    description="Verify if resource pressure normalizes after simulated response steps.",
                    success_condition="Resource verification passes.",
                    failure_condition="Resource pressure remains above policy thresholds.",
                    retryable=False,
                ),
            ],
        )

    def _crash_loop_playbook(self) -> Playbook:
        return Playbook(
            playbook_id="crash-loop-v1",
            issue_type="CRASH_LOOP",
            name="Crash Loop Recovery",
            description="Investigate restart churn, collect logs, propose restart, and verify service stabilization.",
            steps=[
                PlaybookStep(
                    step_id="inspect-crash-loop-process",
                    name="Inspect Crash-Loop Process",
                    description="Inspect process runtime state for the crash-looping service.",
                    action_type="inspect_process",
                    success_condition="Crash-loop process context is captured.",
                    failure_condition="Crash-loop process context cannot be collected.",
                    retryable=True,
                    next_step_on_success="collect-crash-loop-evidence",
                    next_step_on_failure="collect-crash-loop-evidence",
                ),
                PlaybookStep(
                    step_id="collect-crash-loop-evidence",
                    name="Collect Crash-Loop Evidence",
                    description="Collect forensic context and restart indicators for the service.",
                    action_type="collect_forensic_snapshot",
                    success_condition="Crash-loop evidence package is captured.",
                    failure_condition="Crash-loop evidence package is incomplete.",
                    retryable=True,
                    next_step_on_success="propose-restart-after-crash-loop",
                    next_step_on_failure="propose-restart-after-crash-loop",
                ),
                PlaybookStep(
                    step_id="propose-restart-after-crash-loop",
                    name="Propose Service Restart",
                    description="Propose restart for crash-loop stabilization under policy controls.",
                    action_type="restart_service",
                    success_condition="Restart proposal is approved for simulation.",
                    failure_condition="Restart proposal is blocked by policy.",
                    retryable=False,
                    next_step_on_success="verify-crash-loop-stability",
                    next_step_on_failure="verify-crash-loop-stability",
                ),
                PlaybookStep(
                    step_id="verify-crash-loop-stability",
                    name="Verification Checkpoint",
                    description="Verify whether restart churn is reduced after simulated steps.",
                    success_condition="Crash-loop verification passes.",
                    failure_condition="Crash-loop persists after simulation.",
                    retryable=False,
                ),
            ],
        )

    def _default_playbook(self, issue_type: str) -> Playbook:
        return Playbook(
            playbook_id=f"{issue_type.lower()}-fallback-v1",
            issue_type=issue_type,
            name="Fallback Observability Playbook",
            description="Fallback strategy when no dedicated playbook exists.",
            steps=[
                PlaybookStep(
                    step_id="fallback-inspect-process",
                    name="Inspect Process",
                    description="Collect basic process-level context for unknown issue types.",
                    action_type="inspect_process",
                    success_condition="Process context was captured.",
                    failure_condition="Process context capture failed.",
                    retryable=True,
                ),
                PlaybookStep(
                    step_id="fallback-verify",
                    name="Verification Checkpoint",
                    description="Verify whether fallback inspection produced actionable evidence.",
                    success_condition="Fallback inspection produced actionable evidence.",
                    failure_condition="Fallback inspection produced no actionable evidence.",
                    retryable=False,
                ),
            ],
        )
