from app.core.strategy_engine import StrategyEngine
from app.models.schemas import Issue


def build_issue(issue_type: str, *, issue_id: str = "issue-1", severity: str = "high", confidence: float = 0.78) -> Issue:
    return Issue(
        id=issue_id,
        type=issue_type,
        category="test",
        description=f"{issue_type} observed",
        target="target-1",
        severity=severity,
        confidence=confidence,
        priority_score=82,
        recurrence_status="recurring",
        recurrence_count=2,
        deviation_score=0.45,
    )


def test_strategy_engine_generates_multiple_candidates_for_selected_issue_types():
    engine = StrategyEngine()
    issue = build_issue("PORT_CONFLICT")

    selection = engine.select_for_issue(issue, platform="linux", mode="mock")

    assert len(selection.ranked_candidates) >= 3
    assert selection.selected_strategy_id


def test_strategy_engine_ranking_is_deterministic():
    engine = StrategyEngine()
    issue = build_issue("SUSPICIOUS_PROCESS")

    selection_a = engine.select_for_issue(issue, platform="linux", mode="mock")
    selection_b = engine.select_for_issue(issue, platform="linux", mode="mock")

    assert [item.strategy.strategy_id for item in selection_a.ranked_candidates] == [
        item.strategy.strategy_id for item in selection_b.ranked_candidates
    ]
    assert selection_a.selected_strategy_id == selection_b.selected_strategy_id


def test_strategy_selection_includes_winning_reason_and_rejected_reasons():
    engine = StrategyEngine()
    issue = build_issue("DISK_PRESSURE")

    selection = engine.select_for_issue(issue, platform="linux", mode="mock")

    assert selection.winning_reason
    assert selection.rejected_reasons
    assert all(reason for reason in selection.rejected_reasons.values())


def test_mode_aware_scoring_penalizes_restart_heavy_strategy_in_live_mode():
    engine = StrategyEngine()
    issue = build_issue("SERVICE_DOWN", severity="medium", confidence=0.62)

    mock_selection = engine.select_for_issue(issue, platform="linux", mode="mock")
    live_selection = engine.select_for_issue(issue, platform="linux", mode="live")

    mock_restart = next(
        candidate for candidate in mock_selection.ranked_candidates
        if candidate.strategy.strategy_id == "service-down-inspect-log-restart"
    )
    live_restart = next(
        candidate for candidate in live_selection.ranked_candidates
        if candidate.strategy.strategy_id == "service-down-inspect-log-restart"
    )

    assert live_restart.score.total_score < mock_restart.score.total_score
    assert live_restart.score.approval_cost >= mock_restart.score.approval_cost


def test_approval_burden_affects_total_score_for_port_conflict():
    engine = StrategyEngine()
    issue = build_issue("PORT_CONFLICT", severity="high", confidence=0.74)

    selection = engine.select_for_issue(issue, platform="linux", mode="live")
    evidence_first = next(
        candidate for candidate in selection.ranked_candidates
        if candidate.strategy.strategy_id == "port-conflict-investigate-evidence"
    )
    stop_proposal = next(
        candidate for candidate in selection.ranked_candidates
        if candidate.strategy.strategy_id == "port-conflict-stop-proposal"
    )

    assert stop_proposal.score.approval_cost > evidence_first.score.approval_cost
    assert stop_proposal.score.total_score < evidence_first.score.total_score
