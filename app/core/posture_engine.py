from __future__ import annotations

from typing import List, Optional

from app.models.schemas import Issue, ResponsePosture, ResponsePostureCategory, StrategySelection


class ResponsePostureEngine:
    """Deterministic response posture reasoning for containment and isolation planning."""

    def __init__(self) -> None:
        self.severity_map = {
            "critical": 1.0,
            "high": 0.8,
            "medium": 0.55,
            "low": 0.3,
        }

    def assess_issue_posture(
        self,
        issue: Issue,
        selection: StrategySelection | None,
        *,
        platform: str,
        mode: str,
    ) -> ResponsePosture:
        severity = (issue.severity or "low").lower()
        severity_value = self.severity_map.get(severity, 0.5)
        confidence = max(0.0, min(1.0, issue.confidence or 0.0))
        recurrence_count = issue.recurrence_count or 0
        recurrence_factor = min(1.0, recurrence_count / 5.0)
        chronic = (issue.recurrence_status or "").lower() == "chronic"
        deviation = max(0.0, min(1.0, issue.deviation_score or 0.0))

        selected_strategy = selection.selected_strategy if selection is not None else None
        strategy_name = selected_strategy.name if selected_strategy is not None else "Default evidence-first"
        strategy_disruption = selected_strategy.estimated_disruption if selected_strategy is not None else 0.1
        approval_burden = selected_strategy.estimated_approval_burden if selected_strategy is not None else 0.1
        action_types = set(selected_strategy.action_types if selected_strategy is not None else [])
        high_risk_actions = {"quarantine_process", "stop_conflicting_process", "restart_service", "clear_temp_files"}
        observe_only = action_types.issubset({"inspect_process", "inspect_port_usage", "collect_forensic_snapshot"})
        has_isolation_action = bool(action_types & {"quarantine_process", "stop_conflicting_process"})
        has_remediation_action = bool(action_types & {"restart_service", "clear_temp_files", "quarantine_process", "stop_conflicting_process"})

        if issue.type == "SUSPICIOUS_PROCESS" and confidence >= 0.55 and has_isolation_action:
            category = ResponsePostureCategory.isolate
        elif severity_value >= 0.8 and (chronic or deviation >= 0.4 or approval_burden >= 0.7):
            category = ResponsePostureCategory.contain
        elif strategy_disruption >= 0.75 and confidence < 0.7:
            category = ResponsePostureCategory.defer
        elif observe_only or severity_value <= 0.35 or confidence < 0.45:
            category = ResponsePostureCategory.observe
        elif has_remediation_action and severity_value >= 0.6:
            category = ResponsePostureCategory.contain
        elif strategy_disruption <= 0.3 and approval_burden <= 0.35:
            category = ResponsePostureCategory.stabilize
        else:
            category = ResponsePostureCategory.stabilize

        posture_label = {
            ResponsePostureCategory.observe: "Observation",
            ResponsePostureCategory.stabilize: "Stabilization",
            ResponsePostureCategory.contain: "Containment",
            ResponsePostureCategory.isolate: "Isolation",
            ResponsePostureCategory.defer: "Human Review",
        }[category]

        defense_focus = {
            ResponsePostureCategory.observe: "Monitor and gather evidence before intervention.",
            ResponsePostureCategory.stabilize: "Stabilize the host with low-impact actions.",
            ResponsePostureCategory.contain: "Contain the issue and enable controlled remediation.",
            ResponsePostureCategory.isolate: "Isolate suspicious activity and limit blast radius.",
            ResponsePostureCategory.defer: "Escalate to human operators before further action.",
        }[category]

        escalation_recommendation = (
            "Require operator review and approval gating before containment actions."
            if category in {ResponsePostureCategory.isolate, ResponsePostureCategory.contain, ResponsePostureCategory.defer}
            else "Continue evidence-driven observation and safe monitoring."
        )

        risk_alignment = (
            "Aligns high-risk posture to critical issue signal and strategy disruption profile."
            if category in {ResponsePostureCategory.contain, ResponsePostureCategory.isolate}
            else "Keeps posture conservative while preserving operator oversight."
        )

        supporting_factors: List[str] = [
            f"Severity={severity.upper()} ({severity_value:.2f})",
            f"Confidence={confidence:.2f}",
            f"Recurrence count={recurrence_count}",
            f"Baseline deviation={deviation:.2f}",
            f"Strategy='{strategy_name}' disruption={strategy_disruption:.2f}",
            f"Approval burden estimate={approval_burden:.2f}",
        ]
        if chronic:
            supporting_factors.append("Chronic recurrence detected.")
        if has_isolation_action:
            supporting_factors.append("Strategy includes isolation or containment action.")
        if observe_only:
            supporting_factors.append("Selected strategy avoids high-disruption actions.")

        rationale = (
            f"Response posture derived from {issue.type} attributes, selected strategy, and issue lifecycle pressure. "
            f"Strategy '{strategy_name}' was evaluated for platform={platform} / mode={mode}."
        )

        return ResponsePosture(
            posture_label=posture_label,
            posture_category=category,
            defense_focus=defense_focus,
            escalation_recommendation=escalation_recommendation,
            rationale=rationale,
            confidence=round(confidence, 2),
            risk_alignment=risk_alignment,
            approval_pressure=round(approval_burden, 2),
            disruption_cost=round(strategy_disruption, 2),
            supporting_factors=supporting_factors,
        )

    def assess_overall_posture(self, postures: List[ResponsePosture]) -> ResponsePosture:
        if not postures:
            return ResponsePosture(
                posture_label="Observation",
                posture_category=ResponsePostureCategory.observe,
                defense_focus="No specific posture computed.",
                escalation_recommendation="Await issue evaluation before posture recommendation.",
                rationale="No issues were available for posture assessment.",
                confidence=0.0,
                risk_alignment="No posture alignment available.",
                approval_pressure=0.0,
                disruption_cost=0.0,
                supporting_factors=[],
            )

        sorted_postures = sorted(
            postures,
            key=lambda item: (self._category_rank(item.posture_category), item.confidence),
            reverse=True,
        )
        top_posture = sorted_postures[0]
        average_confidence = round(sum(item.confidence for item in postures) / len(postures), 2)
        average_approval = round(sum(item.approval_pressure for item in postures) / len(postures), 2)
        average_disruption = round(sum(item.disruption_cost for item in postures) / len(postures), 2)
        consensus = sorted({item.posture_label for item in postures}, key=lambda label: label)

        return ResponsePosture(
            posture_label=top_posture.posture_label,
            posture_category=top_posture.posture_category,
            defense_focus=top_posture.defense_focus,
            escalation_recommendation=(
                "Escalate high-risk containment intents to operators when any issue posture is containment or isolation."
                if any(item.posture_category in {ResponsePostureCategory.contain, ResponsePostureCategory.isolate, ResponsePostureCategory.defer} for item in postures)
                else "Maintain observation and remediation readiness across current issues."
            ),
            rationale=(
                f"Aggregated posture from {len(postures)} issues with top posture {top_posture.posture_label}. "
                f"Consensus postures: {', '.join(consensus)}."
            ),
            confidence=average_confidence,
            risk_alignment="Aggregate posture prioritizes the most urgent issue posture and approval constraints.",
            approval_pressure=average_approval,
            disruption_cost=average_disruption,
            supporting_factors=[
                f"Primary posture: {top_posture.posture_label}",
                f"Average confidence: {average_confidence:.2f}",
                f"Average approval pressure: {average_approval:.2f}",
                f"Average disruption cost: {average_disruption:.2f}",
            ],
        )

    def _category_rank(self, category: ResponsePostureCategory) -> int:
        return {
            ResponsePostureCategory.observe: 1,
            ResponsePostureCategory.stabilize: 2,
            ResponsePostureCategory.defer: 3,
            ResponsePostureCategory.contain: 4,
            ResponsePostureCategory.isolate: 5,
        }[category]
