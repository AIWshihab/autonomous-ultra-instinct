from datetime import datetime, timezone

from app.core.graph_builder import HostGraphBuilder
from app.core.planner import Planner
from app.core.policy_engine import PolicyEngine
from app.core.state_manager import StateManager
from app.models.schemas import IncidentSummary


def _build_graph_context():
    state_manager = StateManager()
    planner = Planner()
    policy_engine = PolicyEngine()
    snapshot = state_manager.collect_snapshot(platform="linux", mode="mock")
    candidate_actions, strategies, selections = planner.plan_with_strategy_selection(
        snapshot.issues,
        platform="linux",
        mode="mock",
    )
    actions = policy_engine.evaluate_actions(candidate_actions, platform="linux", mode="mock")
    return snapshot, actions, strategies, selections


def test_graph_node_creation_contains_host_service_process_port_issue_action():
    snapshot, actions, strategies, selections = _build_graph_context()
    graph = HostGraphBuilder().build_graph(
        snapshot=snapshot,
        incidents=[],
        strategies=strategies,
        strategy_selections=selections,
        actions=actions,
    )

    node_types = {node.type.value for node in graph.nodes}
    assert "host" in node_types
    assert "service" in node_types
    assert "process" in node_types
    assert "port" in node_types
    assert "issue" in node_types
    assert "action" in node_types
    assert "strategy" in node_types


def test_graph_process_to_port_mapping_creates_listens_on_edges():
    snapshot, actions, strategies, selections = _build_graph_context()
    graph = HostGraphBuilder().build_graph(
        snapshot=snapshot,
        incidents=[],
        strategies=strategies,
        strategy_selections=selections,
        actions=actions,
    )

    assert any(
        edge.type.value == "listens_on"
        and edge.target_id == "port:80"
        and edge.source_id.startswith("process:")
        for edge in graph.edges
    )


def test_graph_issue_to_target_mapping():
    snapshot, actions, strategies, selections = _build_graph_context()
    service_down_issue = next(issue for issue in snapshot.issues if issue.type == "SERVICE_DOWN")
    graph = HostGraphBuilder().build_graph(
        snapshot=snapshot,
        incidents=[],
        strategies=strategies,
        strategy_selections=selections,
        actions=actions,
    )

    assert any(
        edge.source_id == f"issue:{service_down_issue.id}"
        and edge.type.value == "targets"
        and edge.target_id.startswith("service:")
        for edge in graph.edges
    )


def test_graph_incident_contains_issue_mapping():
    snapshot, actions, strategies, selections = _build_graph_context()
    issue = snapshot.issues[0]
    incident_key = f"linux:{issue.type}:{issue.target or issue.category}"
    snapshot = snapshot.model_copy(
        update={
            "issues": [
                issue.model_copy(update={"incident_key": incident_key}),
                *snapshot.issues[1:],
            ]
        }
    )
    incident = IncidentSummary(
        incident_key=incident_key,
        incident_title=f"{issue.type} on {issue.target or issue.category}",
        issue_type=issue.type,
        target=issue.target or issue.category,
        platform="linux",
        severity_summary=issue.severity,
        recurrence_count=2,
        last_seen_at=datetime.now(timezone.utc),
        related_event_ids=["evt-1", "evt-2"],
        recommended_attention_level="medium",
        trend_direction="worsening",
    )
    graph = HostGraphBuilder().build_graph(
        snapshot=snapshot,
        incidents=[incident],
        strategies=strategies,
        strategy_selections=selections,
        actions=actions,
        incident_key=incident_key,
    )

    assert any(node.id == f"incident:{incident_key}" for node in graph.nodes)
    assert any(
        edge.source_id == f"incident:{incident_key}"
        and edge.target_id == f"issue:{issue.id}"
        and edge.type.value == "contains"
        for edge in graph.edges
    )


def test_graph_links_incident_to_selected_strategy_and_strategy_to_actions():
    snapshot, _, _, _ = _build_graph_context()
    issue = snapshot.issues[0]
    incident_key = issue.incident_key or f"linux:{issue.type}:{issue.target or issue.category}"
    snapshot = snapshot.model_copy(
        update={
            "issues": [
                issue.model_copy(update={"incident_key": incident_key}),
                *snapshot.issues[1:],
            ]
        }
    )
    planner = Planner()
    policy_engine = PolicyEngine()
    candidate_actions, strategies, selections = planner.plan_with_strategy_selection(
        snapshot.issues,
        platform="linux",
        mode="mock",
    )
    actions = policy_engine.evaluate_actions(candidate_actions, platform="linux", mode="mock")
    selection = next(
        strategy_selection.model_copy(update={"incident_key": incident_key})
        for strategy_selection in selections
        if strategy_selection.issue_id == issue.id
    )
    incident = IncidentSummary(
        incident_key=incident_key,
        incident_title=f"{issue.type} on {issue.target or issue.category}",
        issue_type=issue.type,
        target=issue.target or issue.category,
        platform="linux",
        severity_summary=issue.severity,
        recurrence_count=2,
        last_seen_at=datetime.now(timezone.utc),
        related_event_ids=["evt-1", "evt-2"],
        recommended_attention_level="medium",
        trend_direction="worsening",
    )
    graph = HostGraphBuilder().build_graph(
        snapshot=snapshot,
        incidents=[incident],
        strategies=strategies,
        strategy_selections=[selection],
        actions=actions,
        incident_key=incident_key,
    )

    strategy_node_id = f"strategy:{selection.issue_id}:{selection.selected_strategy_id}"
    assert any(node.id == strategy_node_id for node in graph.nodes)
    assert any(
        edge.source_id == f"incident:{incident_key}"
        and edge.target_id == strategy_node_id
        and edge.type.value == "contains"
        for edge in graph.edges
    )
    assert any(
        edge.source_id == strategy_node_id
        and edge.type.value == "executes"
        and edge.target_id.startswith("action:")
        for edge in graph.edges
    )
