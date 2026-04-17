from __future__ import annotations

from dataclasses import dataclass

from app.core.policy_engine import PolicyEngine
from app.models.schemas import (
    Action,
    StrategyCandidate,
    StrategyDecisionTrace,
    StrategyEvaluationContext,
    StrategyScore,
    StrategySelection,
    StrategyTradeoff,
)


@dataclass(frozen=True)
class _StrategyTemplate:
    strategy_id: str
    name: str
    description: str
    action_types: list[str]
    ordered_step_ids: list[str]
    estimated_risk: float
    estimated_approval_burden: float
    estimated_execution_feasibility: float
    estimated_observability: float
    estimated_disruption: float
    rationale_summary: str


class StrategyEngine:
    """Deterministic, explainable multi-strategy evaluation and selection."""

    def __init__(self, policy_engine: PolicyEngine | None = None) -> None:
        self.policy_engine = policy_engine or PolicyEngine()
        self.weights = {
            "severity_alignment": 0.15,
            "confidence_support": 0.09,
            "recurrence_pressure": 0.08,
            "chronicity_pressure": 0.09,
            "baseline_deviation_support": 0.08,
            "execution_feasibility": 0.14,
            "observability_gain": 0.14,
            "risk_fit": 0.13,
            "approval_cost": 0.05,
            "disruption_cost": 0.05,
        }

    def select_for_issue(
        self,
        issue,
        *,
        platform: str,
        mode: str,
        current_incident_state: str | None = None,
    ) -> StrategySelection:
        context = StrategyEvaluationContext(
            issue_id=issue.id,
            incident_key=issue.incident_key,
            issue_type=issue.type,
            severity=issue.severity,
            confidence=issue.confidence,
            recurrence_status=issue.recurrence_status,
            recurrence_count=issue.recurrence_count,
            deviation_score=issue.deviation_score,
            priority_score=issue.priority_score,
            platform=platform,
            mode=mode,
            current_incident_state=current_incident_state,
        )
        candidates = self._build_candidates(issue.type, issue.target or issue.category)
        ranked = self._rank_candidates(candidates, context)
        winner = ranked[0]
        rejected = {
            trace.strategy.strategy_id: trace.decision_reason
            for trace in ranked[1:]
        }
        return StrategySelection(
            issue_id=issue.id,
            incident_key=issue.incident_key,
            selected_strategy_id=winner.strategy.strategy_id,
            selected_strategy=winner.strategy,
            ranked_candidates=ranked,
            winning_reason=winner.decision_reason,
            rejected_reasons=rejected,
            evaluation_context=context,
        )

    def _rank_candidates(
        self,
        candidates: list[StrategyCandidate],
        context: StrategyEvaluationContext,
    ) -> list[StrategyDecisionTrace]:
        scored: list[tuple[StrategyCandidate, StrategyScore, list[StrategyTradeoff], str]] = []
        for candidate in candidates:
            score, tradeoffs = self._score_candidate(candidate, context)
            reason = self._decision_reason(candidate, score, tradeoffs, context)
            scored.append((candidate, score, tradeoffs, reason))

        scored.sort(key=lambda item: (-item[1].total_score, item[0].strategy_id))
        traces: list[StrategyDecisionTrace] = []
        for index, (candidate, score, tradeoffs, reason) in enumerate(scored, start=1):
            traces.append(
                StrategyDecisionTrace(
                    rank=index,
                    strategy=candidate,
                    score=score,
                    decision_reason=reason,
                    tradeoffs=tradeoffs,
                )
            )
        return traces

    def _score_candidate(
        self,
        candidate: StrategyCandidate,
        context: StrategyEvaluationContext,
    ) -> tuple[StrategyScore, list[StrategyTradeoff]]:
        preview_actions = self._preview_actions(candidate, context)
        blocked_count = len([action for action in preview_actions if action.execution_mode == "blocked"])
        approval_count = len([action for action in preview_actions if action.approval_required is True])
        dispatchable_count = len(
            [
                action
                for action in preview_actions
                if action.allowed is True and action.execution_mode != "blocked"
            ]
        )
        observed_count = len(
            [action for action in preview_actions if action.execution_mode == "observe_only"]
        )
        action_count = max(1, len(preview_actions))
        blocked_ratio = blocked_count / action_count
        approval_ratio = approval_count / action_count
        dispatchable_ratio = dispatchable_count / action_count
        observability_ratio = observed_count / action_count

        severity_value = self._severity_value(context.severity)
        severity_alignment = self._severity_alignment(severity_value, candidate.estimated_risk)
        confidence_support = max(0.0, min(1.0, context.confidence))
        recurrence_pressure = min(1.0, (context.recurrence_count or 0) / 5.0)
        chronicity_pressure = 1.0 if (context.recurrence_status or "").lower() == "chronic" else recurrence_pressure * 0.65
        baseline_deviation_support = min(1.0, max(0.0, context.deviation_score))

        mode_penalty = 0.2 if context.mode == "live" and candidate.estimated_disruption > 0.5 else 0.0
        execution_feasibility = max(
            0.0,
            min(
                1.0,
                (candidate.estimated_execution_feasibility * 0.55)
                + (dispatchable_ratio * 0.35)
                + ((1.0 - blocked_ratio) * 0.1)
                - mode_penalty,
            ),
        )
        observability_gain = max(
            0.0,
            min(
                1.0,
                (candidate.estimated_observability * 0.7)
                + (observability_ratio * 0.2)
                + ((1.0 - blocked_ratio) * 0.1),
            ),
        )

        approval_cost = min(
            1.0,
            (candidate.estimated_approval_burden * 0.6)
            + (approval_ratio * 0.35)
            + (0.05 if context.mode == "live" else 0.0),
        )
        disruption_cost = min(
            1.0,
            (candidate.estimated_disruption * 0.7)
            + (blocked_ratio * 0.2)
            + (0.1 if context.mode == "live" and candidate.estimated_disruption >= 0.5 else 0.0),
        )
        risk_fit = self._risk_fit(severity_value, candidate.estimated_risk, blocked_ratio)

        high_pressure = (
            severity_value >= 0.8
            or context.recurrence_count >= 2
            or (context.recurrence_status or "").lower() == "chronic"
        )
        if context.issue_type in {"SERVICE_DOWN", "CRASH_LOOP"} and high_pressure:
            if "restart_service" in candidate.action_types:
                severity_alignment = min(1.0, severity_alignment + 0.22)
                risk_fit = min(1.0, risk_fit + 0.14)
                execution_feasibility = min(1.0, execution_feasibility + 0.04)
            else:
                severity_alignment = max(0.0, severity_alignment - 0.08)
                risk_fit = max(0.0, risk_fit - 0.06)

        if context.confidence < 0.7 and candidate.estimated_disruption > 0.5:
            disruption_cost = min(1.0, disruption_cost + 0.08)
            approval_cost = min(1.0, approval_cost + 0.05)

        weighted_total = (
            self.weights["severity_alignment"] * severity_alignment
            + self.weights["confidence_support"] * confidence_support
            + self.weights["recurrence_pressure"] * recurrence_pressure
            + self.weights["chronicity_pressure"] * chronicity_pressure
            + self.weights["baseline_deviation_support"] * baseline_deviation_support
            + self.weights["execution_feasibility"] * execution_feasibility
            + self.weights["observability_gain"] * observability_gain
            + self.weights["risk_fit"] * risk_fit
            - self.weights["approval_cost"] * approval_cost
            - self.weights["disruption_cost"] * disruption_cost
        )
        total_score = round(max(0.0, min(100.0, weighted_total * 100.0)), 2)

        dimension_reasons = {
            "severity_alignment": (
                f"Severity '{context.severity}' matched against estimated strategy risk {candidate.estimated_risk:.2f}."
            ),
            "confidence_support": (
                f"Issue confidence {context.confidence:.2f} contributes directly to strategy viability."
            ),
            "recurrence_pressure": (
                f"Recurrence count {context.recurrence_count} increases pressure for stronger remediation."
            ),
            "chronicity_pressure": (
                "Chronic recurrence boosts urgency."
                if (context.recurrence_status or "").lower() == "chronic"
                else "Non-chronic recurrence applies moderate urgency."
            ),
            "baseline_deviation_support": (
                f"Baseline deviation score {context.deviation_score:.2f} supports intervention intensity."
            ),
            "approval_cost": (
                f"Approval burden uses template estimate {candidate.estimated_approval_burden:.2f} and policy gate ratio {approval_ratio:.2f}."
            ),
            "disruption_cost": (
                f"Disruption estimate {candidate.estimated_disruption:.2f} and blocked ratio {blocked_ratio:.2f} raise cost."
            ),
            "execution_feasibility": (
                f"Dispatchable action ratio {dispatchable_ratio:.2f} and mode '{context.mode}' determine feasibility."
            ),
            "observability_gain": (
                f"Observability estimate {candidate.estimated_observability:.2f} with observe-only ratio {observability_ratio:.2f}."
            ),
            "risk_fit": (
                f"Risk fit reflects severity pressure {severity_value:.2f} with strategy risk {candidate.estimated_risk:.2f}."
            ),
        }
        score = StrategyScore(
            severity_alignment=round(severity_alignment * 100.0, 2),
            confidence_support=round(confidence_support * 100.0, 2),
            recurrence_pressure=round(recurrence_pressure * 100.0, 2),
            chronicity_pressure=round(chronicity_pressure * 100.0, 2),
            baseline_deviation_support=round(baseline_deviation_support * 100.0, 2),
            approval_cost=round(approval_cost * 100.0, 2),
            disruption_cost=round(disruption_cost * 100.0, 2),
            execution_feasibility=round(execution_feasibility * 100.0, 2),
            observability_gain=round(observability_gain * 100.0, 2),
            risk_fit=round(risk_fit * 100.0, 2),
            total_score=total_score,
            dimension_reasons=dimension_reasons,
        )
        tradeoffs = self._tradeoffs(score)
        return score, tradeoffs

    def _tradeoffs(self, score: StrategyScore) -> list[StrategyTradeoff]:
        return [
            StrategyTradeoff(
                dimension="observability_gain",
                impact="benefit",
                value=score.observability_gain,
                reason=score.dimension_reasons.get("observability_gain", ""),
            ),
            StrategyTradeoff(
                dimension="execution_feasibility",
                impact="benefit",
                value=score.execution_feasibility,
                reason=score.dimension_reasons.get("execution_feasibility", ""),
            ),
            StrategyTradeoff(
                dimension="approval_cost",
                impact="cost",
                value=score.approval_cost,
                reason=score.dimension_reasons.get("approval_cost", ""),
            ),
            StrategyTradeoff(
                dimension="disruption_cost",
                impact="cost",
                value=score.disruption_cost,
                reason=score.dimension_reasons.get("disruption_cost", ""),
            ),
        ]

    def _decision_reason(
        self,
        candidate: StrategyCandidate,
        score: StrategyScore,
        tradeoffs: list[StrategyTradeoff],
        context: StrategyEvaluationContext,
    ) -> str:
        cost_tradeoffs = [tradeoff for tradeoff in tradeoffs if tradeoff.impact == "cost"]
        benefit_tradeoffs = [tradeoff for tradeoff in tradeoffs if tradeoff.impact == "benefit"]
        largest_cost = max(cost_tradeoffs, key=lambda item: item.value)
        largest_benefit = max(benefit_tradeoffs, key=lambda item: item.value)
        return (
            f"{candidate.name} scored {score.total_score:.2f} in {context.mode} mode. "
            f"Top benefit: {largest_benefit.dimension}={largest_benefit.value:.2f}; "
            f"largest cost: {largest_cost.dimension}={largest_cost.value:.2f}."
        )

    def _preview_actions(
        self,
        candidate: StrategyCandidate,
        context: StrategyEvaluationContext,
    ) -> list[Action]:
        actions = [
            Action(
                id=f"{context.issue_id}:{candidate.strategy_id}:{action_type}",
                issue_id=context.issue_id,
                action_type=action_type,
                target=candidate.target,
                description=f"Strategy preview action {action_type}.",
            )
            for action_type in candidate.action_types
        ]
        return self.policy_engine.evaluate_actions(actions, platform=context.platform, mode=context.mode)

    def _severity_value(self, severity: str) -> float:
        mapping = {
            "critical": 1.0,
            "high": 0.8,
            "medium": 0.55,
            "low": 0.3,
        }
        return mapping.get(severity.lower(), 0.5)

    def _severity_alignment(self, severity_value: float, estimated_risk: float) -> float:
        # Safer strategies are favored when uncertainty is higher, but severe issues tolerate more risk.
        target_risk = (severity_value * 0.75) + 0.1
        distance = abs(target_risk - estimated_risk)
        return max(0.0, min(1.0, 1.0 - distance))

    def _risk_fit(self, severity_value: float, estimated_risk: float, blocked_ratio: float) -> float:
        if blocked_ratio >= 0.6:
            return max(0.0, 0.45 - blocked_ratio * 0.2)
        spread = abs(severity_value - estimated_risk)
        return max(0.0, min(1.0, 1.0 - (spread * 0.85)))

    def _build_candidates(self, issue_type: str, target: str) -> list[StrategyCandidate]:
        templates = self._strategy_templates().get(issue_type.upper(), [])
        if not templates:
            templates = [
                _StrategyTemplate(
                    strategy_id=f"{issue_type.lower()}-observe-default",
                    name="Evidence First Strategy",
                    description="Collect safe evidence and defer high-disruption changes.",
                    action_types=["inspect_process", "collect_forensic_snapshot"],
                    ordered_step_ids=["inspect", "collect-evidence", "defer-operator"],
                    estimated_risk=0.2,
                    estimated_approval_burden=0.1,
                    estimated_execution_feasibility=0.9,
                    estimated_observability=0.85,
                    estimated_disruption=0.1,
                    rationale_summary="Default strategy prioritizes safe evidence collection when no dedicated template exists.",
                )
            ]
        return [
            StrategyCandidate(
                strategy_id=template.strategy_id,
                name=template.name,
                description=template.description,
                issue_type=issue_type,
                target=target,
                ordered_step_ids=template.ordered_step_ids,
                action_types=template.action_types,
                estimated_risk=template.estimated_risk,
                estimated_approval_burden=template.estimated_approval_burden,
                estimated_execution_feasibility=template.estimated_execution_feasibility,
                estimated_observability=template.estimated_observability,
                estimated_disruption=template.estimated_disruption,
                rationale_summary=template.rationale_summary,
            )
            for template in templates
        ]

    def _strategy_templates(self) -> dict[str, list[_StrategyTemplate]]:
        return {
            "SERVICE_DOWN": [
                _StrategyTemplate(
                    strategy_id="service-down-inspect-log-restart",
                    name="Inspect + Log Review + Restart Proposal",
                    description="Gather observations then propose controlled restart.",
                    action_types=["inspect_process", "collect_forensic_snapshot", "restart_service"],
                    ordered_step_ids=["inspect-service", "review-logs", "propose-restart", "verify"],
                    estimated_risk=0.55,
                    estimated_approval_burden=0.35,
                    estimated_execution_feasibility=0.7,
                    estimated_observability=0.75,
                    estimated_disruption=0.55,
                    rationale_summary="Balances observability with remediation speed by introducing restart after evidence.",
                ),
                _StrategyTemplate(
                    strategy_id="service-down-evidence-defer-operator",
                    name="Inspect + Evidence + Operator Defer",
                    description="Stay observation-first and defer state change to operators.",
                    action_types=["inspect_process", "collect_forensic_snapshot"],
                    ordered_step_ids=["inspect-service", "collect-evidence", "operator-escalation"],
                    estimated_risk=0.2,
                    estimated_approval_burden=0.1,
                    estimated_execution_feasibility=0.95,
                    estimated_observability=0.9,
                    estimated_disruption=0.15,
                    rationale_summary="Minimizes disruption while maximizing explainable evidence before intervention.",
                ),
                _StrategyTemplate(
                    strategy_id="service-down-inspect-refresh-restart",
                    name="Inspect + Runtime Refresh + Restart Proposal",
                    description="Refresh live context before restart proposal for higher confidence.",
                    action_types=["inspect_process", "inspect_port_usage", "restart_service"],
                    ordered_step_ids=["inspect-service", "refresh-runtime-view", "propose-restart", "verify"],
                    estimated_risk=0.5,
                    estimated_approval_burden=0.4,
                    estimated_execution_feasibility=0.68,
                    estimated_observability=0.8,
                    estimated_disruption=0.58,
                    rationale_summary="Uses extra runtime observation to support restart confidence.",
                ),
            ],
            "PORT_CONFLICT": [
                _StrategyTemplate(
                    strategy_id="port-conflict-investigate-evidence",
                    name="Inspect Port + Process + Evidence",
                    description="Run low-risk diagnostics and package evidence.",
                    action_types=["inspect_port_usage", "inspect_process", "collect_forensic_snapshot"],
                    ordered_step_ids=["inspect-port", "inspect-process", "collect-evidence", "review"],
                    estimated_risk=0.25,
                    estimated_approval_burden=0.1,
                    estimated_execution_feasibility=0.95,
                    estimated_observability=0.92,
                    estimated_disruption=0.12,
                    rationale_summary="Highest observability with minimal operational disruption.",
                ),
                _StrategyTemplate(
                    strategy_id="port-conflict-stop-proposal",
                    name="Inspect Port + Stop Process Proposal",
                    description="Escalate quickly to process-stop proposal after brief validation.",
                    action_types=["inspect_port_usage", "stop_conflicting_process"],
                    ordered_step_ids=["inspect-port", "propose-stop", "approval-gate"],
                    estimated_risk=0.78,
                    estimated_approval_burden=0.85,
                    estimated_execution_feasibility=0.25,
                    estimated_observability=0.48,
                    estimated_disruption=0.82,
                    rationale_summary="Aggressive containment path with high policy and approval burden.",
                ),
                _StrategyTemplate(
                    strategy_id="port-conflict-containment-recommendation",
                    name="Inspect Port + Containment Recommendation",
                    description="Collect bounded evidence and issue containment recommendation without kill-step.",
                    action_types=["inspect_port_usage", "collect_forensic_snapshot"],
                    ordered_step_ids=["inspect-port", "collect-evidence", "recommend-containment"],
                    estimated_risk=0.3,
                    estimated_approval_burden=0.2,
                    estimated_execution_feasibility=0.9,
                    estimated_observability=0.84,
                    estimated_disruption=0.18,
                    rationale_summary="Safer than process-stop while still producing actionable containment context.",
                ),
            ],
            "SUSPICIOUS_PROCESS": [
                _StrategyTemplate(
                    strategy_id="suspicious-process-evidence-first",
                    name="Inspect + Forensic Snapshot",
                    description="Collect evidence and avoid immediate containment action.",
                    action_types=["inspect_process", "collect_forensic_snapshot"],
                    ordered_step_ids=["inspect-process", "collect-forensic", "triage"],
                    estimated_risk=0.22,
                    estimated_approval_burden=0.1,
                    estimated_execution_feasibility=0.95,
                    estimated_observability=0.93,
                    estimated_disruption=0.1,
                    rationale_summary="Ideal early strategy when confidence is moderate and evidence quality matters.",
                ),
                _StrategyTemplate(
                    strategy_id="suspicious-process-quarantine-proposal",
                    name="Inspect + Approval-Gated Quarantine",
                    description="Combine inspection with high-risk quarantine proposal.",
                    action_types=["inspect_process", "collect_forensic_snapshot", "quarantine_process"],
                    ordered_step_ids=["inspect-process", "collect-forensic", "propose-quarantine", "approval-gate"],
                    estimated_risk=0.82,
                    estimated_approval_burden=0.9,
                    estimated_execution_feasibility=0.2,
                    estimated_observability=0.75,
                    estimated_disruption=0.88,
                    rationale_summary="High containment intent but heavy approval and policy burden.",
                ),
                _StrategyTemplate(
                    strategy_id="suspicious-process-escalation-only",
                    name="Evidence-Only Escalation",
                    description="Gather evidence package and escalate without state change proposals.",
                    action_types=["collect_forensic_snapshot"],
                    ordered_step_ids=["collect-forensic", "escalate"],
                    estimated_risk=0.1,
                    estimated_approval_burden=0.05,
                    estimated_execution_feasibility=0.98,
                    estimated_observability=0.82,
                    estimated_disruption=0.05,
                    rationale_summary="Very safe escalation path when certainty is low or disruption must be minimized.",
                ),
            ],
            "DISK_PRESSURE": [
                _StrategyTemplate(
                    strategy_id="disk-pressure-observe-alert",
                    name="Inspect + Evidence + Operator Alert",
                    description="Observe pressure trend and alert operators with evidence.",
                    action_types=["inspect_process", "collect_forensic_snapshot"],
                    ordered_step_ids=["inspect-disk-pressure", "collect-evidence", "operator-alert"],
                    estimated_risk=0.2,
                    estimated_approval_burden=0.1,
                    estimated_execution_feasibility=0.95,
                    estimated_observability=0.88,
                    estimated_disruption=0.1,
                    rationale_summary="Strong observability path without cleanup side effects.",
                ),
                _StrategyTemplate(
                    strategy_id="disk-pressure-cleanup-proposal",
                    name="Inspect + Blocked Cleanup Proposal",
                    description="Inspect and propose cleanup despite policy block risk.",
                    action_types=["inspect_process", "clear_temp_files"],
                    ordered_step_ids=["inspect-disk-pressure", "propose-cleanup", "approval-gate"],
                    estimated_risk=0.65,
                    estimated_approval_burden=0.85,
                    estimated_execution_feasibility=0.2,
                    estimated_observability=0.52,
                    estimated_disruption=0.7,
                    rationale_summary="Potentially impactful but currently blocked and approval-heavy.",
                ),
                _StrategyTemplate(
                    strategy_id="disk-pressure-monitoring-trend",
                    name="Trend-Based Monitoring Strategy",
                    description="Use conservative monitoring progression with minimal intervention.",
                    action_types=["inspect_process"],
                    ordered_step_ids=["inspect-disk-pressure", "trend-monitoring", "scheduled-review"],
                    estimated_risk=0.1,
                    estimated_approval_burden=0.05,
                    estimated_execution_feasibility=0.98,
                    estimated_observability=0.72,
                    estimated_disruption=0.03,
                    rationale_summary="Lowest disruption option focused on trend confirmation and watchful waiting.",
                ),
            ],
            "HIGH_RESOURCE_USAGE": [
                _StrategyTemplate(
                    strategy_id="resource-usage-observe-evidence",
                    name="Observe + Forensic Capture",
                    description="Inspect high-usage process and collect context.",
                    action_types=["inspect_process", "collect_forensic_snapshot"],
                    ordered_step_ids=["inspect-process", "collect-forensic", "review"],
                    estimated_risk=0.2,
                    estimated_approval_burden=0.1,
                    estimated_execution_feasibility=0.94,
                    estimated_observability=0.88,
                    estimated_disruption=0.12,
                    rationale_summary="Preferred low-risk path for resource anomalies.",
                ),
                _StrategyTemplate(
                    strategy_id="resource-usage-monitor-only",
                    name="Monitor-Only Strategy",
                    description="Perform process inspection and continue monitoring.",
                    action_types=["inspect_process"],
                    ordered_step_ids=["inspect-process", "monitor-trend"],
                    estimated_risk=0.08,
                    estimated_approval_burden=0.03,
                    estimated_execution_feasibility=0.98,
                    estimated_observability=0.68,
                    estimated_disruption=0.02,
                    rationale_summary="Minimal change strategy to reduce operational noise.",
                ),
            ],
            "CRASH_LOOP": [
                _StrategyTemplate(
                    strategy_id="crash-loop-evidence-restart",
                    name="Inspect + Evidence + Restart Proposal",
                    description="Collect crash evidence and propose controlled restart.",
                    action_types=["inspect_process", "collect_forensic_snapshot", "restart_service"],
                    ordered_step_ids=["inspect-crash-loop", "collect-crash-evidence", "propose-restart", "verify"],
                    estimated_risk=0.58,
                    estimated_approval_burden=0.4,
                    estimated_execution_feasibility=0.7,
                    estimated_observability=0.78,
                    estimated_disruption=0.6,
                    rationale_summary="Balances evidence with stabilization attempt for repeated crashes.",
                ),
                _StrategyTemplate(
                    strategy_id="crash-loop-observe-escalate",
                    name="Evidence-Only Escalation",
                    description="Gather crash evidence and defer restart to operator governance.",
                    action_types=["inspect_process", "collect_forensic_snapshot"],
                    ordered_step_ids=["inspect-crash-loop", "collect-crash-evidence", "escalate"],
                    estimated_risk=0.2,
                    estimated_approval_burden=0.1,
                    estimated_execution_feasibility=0.95,
                    estimated_observability=0.9,
                    estimated_disruption=0.15,
                    rationale_summary="Safer pathway when restart confidence is limited.",
                ),
            ],
        }
