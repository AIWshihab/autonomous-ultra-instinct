from __future__ import annotations

import re
from collections import Counter

from app.models.schemas import (
    Action,
    EdgeType,
    GraphEdge,
    GraphNode,
    HostGraph,
    IncidentDetail,
    IncidentSummary,
    Issue,
    NodeType,
    PlaybookExecution,
    ProcessInfo,
    RemediationStrategy,
    StateSnapshot,
    StrategySelection,
)


class HostGraphBuilder:
    """Construct an in-memory host dependency graph from current control-plane context."""

    DEFAULT_PROCESS_PORTS: dict[str, list[int]] = {
        "nginx": [80, 443],
        "sshd": [22],
        "ssh": [22],
        "dockerd": [2375, 2376],
        "mdnsresponder": [53],
        "spooler": [445],
    }

    def build_graph(
        self,
        *,
        snapshot: StateSnapshot,
        incidents: list[IncidentSummary | IncidentDetail] | None = None,
        strategies: list[RemediationStrategy] | None = None,
        strategy_selections: list[StrategySelection] | None = None,
        actions: list[Action] | None = None,
        playbook_executions: list[PlaybookExecution] | None = None,
        incident_key: str | None = None,
    ) -> HostGraph:
        incidents = incidents or []
        strategies = strategies or []
        strategy_selections = strategy_selections or []
        actions = actions or []
        playbook_executions = playbook_executions or []

        nodes: dict[str, GraphNode] = {}
        edges: dict[tuple[str, str, EdgeType], GraphEdge] = {}

        host_id = f"host:{snapshot.system_info.hostname}"
        self._add_node(
            nodes,
            GraphNode(
                id=host_id,
                type=NodeType.host,
                label=snapshot.system_info.hostname,
                attributes={
                    "os_name": snapshot.system_info.os_name,
                    "os_version": snapshot.system_info.os_version,
                    "health_score": snapshot.health_score,
                    "risk_score": snapshot.risk_score,
                },
            ),
        )

        process_nodes = self._add_process_nodes(nodes, edges, host_id, snapshot.processes)
        service_nodes = self._add_service_nodes(nodes, edges, host_id, snapshot.services)
        port_nodes = self._add_port_nodes(nodes, edges, host_id, snapshot.open_ports)
        self._add_process_port_edges(
            nodes,
            edges,
            snapshot=snapshot,
            process_nodes=process_nodes,
            service_nodes=service_nodes,
            port_nodes=port_nodes,
        )

        incident_nodes = self._add_incident_nodes(
            nodes,
            edges,
            host_id=host_id,
            incidents=incidents,
            incident_key=incident_key,
        )

        issue_nodes = self._add_issue_nodes(
            nodes,
            edges,
            host_id=host_id,
            issues=snapshot.issues,
            service_nodes=service_nodes,
            process_nodes=process_nodes,
            port_nodes=port_nodes,
            incident_nodes=incident_nodes,
            incident_key=incident_key,
        )

        action_nodes = self._add_action_nodes(
            nodes,
            edges,
            actions=actions,
            issues=snapshot.issues,
            service_nodes=service_nodes,
            process_nodes=process_nodes,
            port_nodes=port_nodes,
            issue_nodes=issue_nodes,
            incident_nodes=incident_nodes,
            strategies=strategies,
            incident_key=incident_key,
        )
        self._add_strategy_nodes(
            nodes,
            edges,
            strategy_selections=strategy_selections,
            issue_nodes=issue_nodes,
            incident_nodes=incident_nodes,
            action_nodes=action_nodes,
            actions=actions,
            incident_key=incident_key,
        )

        self._add_runtime_observation_edges(
            edges,
            host_id=host_id,
            snapshot=snapshot,
            process_nodes=process_nodes,
            port_nodes=port_nodes,
        )
        self._add_playbook_execution_edges(
            edges,
            issue_nodes=issue_nodes,
            action_nodes=action_nodes,
            playbook_executions=playbook_executions,
            issues=snapshot.issues,
            incident_key=incident_key,
        )

        filtered_nodes, filtered_edges = self._filter_graph(nodes, edges, incident_key)
        metadata = self._build_metadata(
            filtered_nodes,
            filtered_edges,
            snapshot,
            incidents,
            actions,
            strategy_selections,
            incident_key,
        )

        return HostGraph(
            nodes=sorted(filtered_nodes.values(), key=lambda node: (node.type.value, node.label.lower(), node.id)),
            edges=sorted(
                filtered_edges.values(),
                key=lambda edge: (edge.type.value, edge.source_id, edge.target_id),
            ),
            metadata=metadata,
        )

    def _add_process_nodes(
        self,
        nodes: dict[str, GraphNode],
        edges: dict[tuple[str, str, EdgeType], GraphEdge],
        host_id: str,
        processes: list[ProcessInfo],
    ) -> dict[str, str]:
        process_nodes: dict[str, str] = {}
        for process in processes:
            node_id = f"process:{process.pid}:{process.name.lower()}"
            process_nodes[process.name.lower()] = node_id
            self._add_node(
                nodes,
                GraphNode(
                    id=node_id,
                    type=NodeType.process,
                    label=process.name,
                    attributes={
                        "pid": process.pid,
                        "cpu_percent": process.cpu_percent,
                        "memory_mb": process.memory_mb,
                        "status": process.status,
                    },
                ),
            )
            self._add_edge(
                edges,
                GraphEdge(
                    source_id=host_id,
                    target_id=node_id,
                    type=EdgeType.contains,
                    description="Host contains process.",
                ),
            )
        return process_nodes

    def _add_service_nodes(
        self,
        nodes: dict[str, GraphNode],
        edges: dict[tuple[str, str, EdgeType], GraphEdge],
        host_id: str,
        services: list,
    ) -> dict[str, str]:
        service_nodes: dict[str, str] = {}
        for service in services:
            node_id = f"service:{service.name.lower()}"
            service_nodes[service.name.lower()] = node_id
            severity = "high" if service.status.lower() in {"failed", "stopped", "unhealthy"} else None
            self._add_node(
                nodes,
                GraphNode(
                    id=node_id,
                    type=NodeType.service,
                    label=service.name,
                    attributes={
                        "status": service.status,
                        "description": service.description,
                        "restart_count": service.restart_count,
                    },
                    severity=severity,
                ),
            )
            self._add_edge(
                edges,
                GraphEdge(
                    source_id=host_id,
                    target_id=node_id,
                    type=EdgeType.contains,
                    description="Host contains service.",
                ),
            )
        return service_nodes

    def _add_port_nodes(
        self,
        nodes: dict[str, GraphNode],
        edges: dict[tuple[str, str, EdgeType], GraphEdge],
        host_id: str,
        ports: list[int],
    ) -> dict[int, str]:
        port_nodes: dict[int, str] = {}
        for port in sorted(set(ports)):
            node_id = f"port:{port}"
            port_nodes[port] = node_id
            self._add_node(
                nodes,
                GraphNode(
                    id=node_id,
                    type=NodeType.port,
                    label=str(port),
                    attributes={"port": port},
                ),
            )
            self._add_edge(
                edges,
                GraphEdge(
                    source_id=host_id,
                    target_id=node_id,
                    type=EdgeType.contains,
                    description="Host contains open/listening port.",
                ),
            )
        return port_nodes

    def _add_process_port_edges(
        self,
        nodes: dict[str, GraphNode],
        edges: dict[tuple[str, str, EdgeType], GraphEdge],
        *,
        snapshot: StateSnapshot,
        process_nodes: dict[str, str],
        service_nodes: dict[str, str],
        port_nodes: dict[int, str],
    ) -> None:
        log_text = " ".join(snapshot.recent_logs).lower()
        for process in snapshot.processes:
            process_node_id = process_nodes.get(process.name.lower())
            if process_node_id is None:
                continue
            guessed_ports = list(self.DEFAULT_PROCESS_PORTS.get(process.name.lower(), []))
            for port in port_nodes:
                if f"port {port}" in log_text and process.name.lower() in log_text:
                    guessed_ports.append(port)
            for port in sorted(set(guessed_ports)):
                port_node_id = port_nodes.get(port)
                if port_node_id is None:
                    continue
                self._add_edge(
                    edges,
                    GraphEdge(
                        source_id=process_node_id,
                        target_id=port_node_id,
                        type=EdgeType.listens_on,
                        description="Process listens on port.",
                    ),
                )

        for service_name, service_node_id in service_nodes.items():
            guessed_ports = self.DEFAULT_PROCESS_PORTS.get(service_name, [])
            for port in guessed_ports:
                port_node_id = port_nodes.get(port)
                if port_node_id is None:
                    continue
                self._add_edge(
                    edges,
                    GraphEdge(
                        source_id=service_node_id,
                        target_id=port_node_id,
                        type=EdgeType.depends_on,
                        description="Service depends on/listens via port.",
                    ),
                )
            process_node_id = process_nodes.get(service_name)
            if process_node_id is not None:
                self._add_edge(
                    edges,
                    GraphEdge(
                        source_id=service_node_id,
                        target_id=process_node_id,
                        type=EdgeType.depends_on,
                        description="Service depends on process runtime.",
                    ),
                )

    def _add_incident_nodes(
        self,
        nodes: dict[str, GraphNode],
        edges: dict[tuple[str, str, EdgeType], GraphEdge],
        *,
        host_id: str,
        incidents: list[IncidentSummary | IncidentDetail],
        incident_key: str | None,
    ) -> dict[str, str]:
        incident_nodes: dict[str, str] = {}
        for incident in incidents:
            if incident_key and incident.incident_key != incident_key:
                continue
            node_id = f"incident:{incident.incident_key}"
            incident_nodes[incident.incident_key] = node_id
            self._add_node(
                nodes,
                GraphNode(
                    id=node_id,
                    type=NodeType.incident,
                    label=incident.incident_title,
                    attributes={
                        "issue_type": incident.issue_type,
                        "target": incident.target,
                        "recurrence_count": incident.recurrence_count,
                        "trend_direction": incident.trend_direction,
                    },
                    severity=incident.severity_summary,
                ),
            )
            self._add_edge(
                edges,
                GraphEdge(
                    source_id=host_id,
                    target_id=node_id,
                    type=EdgeType.contains,
                    description="Host contains correlated incident.",
                ),
            )
        return incident_nodes

    def _add_issue_nodes(
        self,
        nodes: dict[str, GraphNode],
        edges: dict[tuple[str, str, EdgeType], GraphEdge],
        *,
        host_id: str,
        issues: list[Issue],
        service_nodes: dict[str, str],
        process_nodes: dict[str, str],
        port_nodes: dict[int, str],
        incident_nodes: dict[str, str],
        incident_key: str | None,
    ) -> dict[str, str]:
        issue_nodes: dict[str, str] = {}
        for issue in issues:
            if incident_key and issue.incident_key != incident_key:
                continue
            node_id = f"issue:{issue.id}"
            issue_nodes[issue.id] = node_id
            self._add_node(
                nodes,
                GraphNode(
                    id=node_id,
                    type=NodeType.issue,
                    label=issue.type,
                    attributes={
                        "issue_id": issue.id,
                        "category": issue.category,
                        "target": issue.target,
                        "confidence": issue.confidence,
                        "priority_score": issue.priority_score,
                    },
                    severity=issue.severity,
                ),
            )
            self._add_edge(
                edges,
                GraphEdge(
                    source_id=host_id,
                    target_id=node_id,
                    type=EdgeType.contains,
                    description="Host contains detected issue.",
                ),
            )
            if issue.incident_key and issue.incident_key in incident_nodes:
                self._add_edge(
                    edges,
                    GraphEdge(
                        source_id=incident_nodes[issue.incident_key],
                        target_id=node_id,
                        type=EdgeType.contains,
                        description="Incident contains issue.",
                    ),
                )
            target_node = self._resolve_target_node_id(
                issue=issue,
                service_nodes=service_nodes,
                process_nodes=process_nodes,
                port_nodes=port_nodes,
            )
            if target_node:
                self._add_edge(
                    edges,
                    GraphEdge(
                        source_id=node_id,
                        target_id=target_node,
                        type=EdgeType.targets,
                        description="Issue targets entity.",
                    ),
                )
        return issue_nodes

    def _add_action_nodes(
        self,
        nodes: dict[str, GraphNode],
        edges: dict[tuple[str, str, EdgeType], GraphEdge],
        *,
        actions: list[Action],
        issues: list[Issue],
        service_nodes: dict[str, str],
        process_nodes: dict[str, str],
        port_nodes: dict[int, str],
        issue_nodes: dict[str, str],
        incident_nodes: dict[str, str],
        strategies: list[RemediationStrategy],
        incident_key: str | None,
    ) -> dict[str, str]:
        issue_by_id = {issue.id: issue for issue in issues}
        incident_by_issue_id = {
            strategy.issue_id: strategy.incident_key for strategy in strategies
        }
        action_nodes: dict[str, str] = {}
        for action in actions:
            linked_issue = issue_by_id.get(action.issue_id or "")
            linked_incident_key = incident_by_issue_id.get(action.issue_id or "") or (
                linked_issue.incident_key if linked_issue else None
            )
            if incident_key and linked_incident_key != incident_key:
                continue

            node_id = f"action:{action.id}"
            action_nodes[action.id] = node_id
            self._add_node(
                nodes,
                GraphNode(
                    id=node_id,
                    type=NodeType.action,
                    label=action.action_type,
                    attributes={
                        "action_id": action.id,
                        "allowed": action.allowed,
                        "risk_tier": action.risk_tier,
                        "approval_required": action.approval_required,
                        "execution_mode": action.execution_mode,
                        "target": action.target,
                    },
                    severity=self._action_severity(action.risk_tier),
                ),
            )
            if action.issue_id and action.issue_id in issue_nodes:
                self._add_edge(
                    edges,
                    GraphEdge(
                        source_id=issue_nodes[action.issue_id],
                        target_id=node_id,
                        type=EdgeType.executes,
                        description="Issue remediation executes through action.",
                    ),
                )
            if linked_incident_key and linked_incident_key in incident_nodes:
                self._add_edge(
                    edges,
                    GraphEdge(
                        source_id=incident_nodes[linked_incident_key],
                        target_id=node_id,
                        type=EdgeType.contains,
                        description="Incident playbook contains action.",
                    ),
                )
            target_node = self._resolve_action_target(
                action=action,
                service_nodes=service_nodes,
                process_nodes=process_nodes,
                port_nodes=port_nodes,
            )
            if target_node:
                self._add_edge(
                    edges,
                    GraphEdge(
                        source_id=node_id,
                        target_id=target_node,
                        type=EdgeType.targets,
                        description="Action targets entity.",
                    ),
                )
        return action_nodes

    def _add_runtime_observation_edges(
        self,
        edges: dict[tuple[str, str, EdgeType], GraphEdge],
        *,
        host_id: str,
        snapshot: StateSnapshot,
        process_nodes: dict[str, str],
        port_nodes: dict[int, str],
    ) -> None:
        trace = snapshot.runtime_observation_trace
        if trace is None:
            return
        artifact_types = {result.parsed_artifact_type for result in trace.results if result.success}
        if "process_list" in artifact_types:
            for process_node_id in process_nodes.values():
                self._add_edge(
                    edges,
                    GraphEdge(
                        source_id=host_id,
                        target_id=process_node_id,
                        type=EdgeType.related_to,
                        description="Runtime observation collected process artifact.",
                    ),
                )
        if "open_ports" in artifact_types:
            for port_node_id in port_nodes.values():
                self._add_edge(
                    edges,
                    GraphEdge(
                        source_id=host_id,
                        target_id=port_node_id,
                        type=EdgeType.related_to,
                        description="Runtime observation collected open-port artifact.",
                    ),
                )

    def _add_strategy_nodes(
        self,
        nodes: dict[str, GraphNode],
        edges: dict[tuple[str, str, EdgeType], GraphEdge],
        *,
        strategy_selections: list[StrategySelection],
        issue_nodes: dict[str, str],
        incident_nodes: dict[str, str],
        action_nodes: dict[str, str],
        actions: list[Action],
        incident_key: str | None,
    ) -> None:
        action_by_id = {action.id: action for action in actions}
        for selection in strategy_selections:
            if incident_key and selection.incident_key != incident_key:
                continue
            node_id = f"strategy:{selection.issue_id}:{selection.selected_strategy_id}"
            self._add_node(
                nodes,
                GraphNode(
                    id=node_id,
                    type=NodeType.strategy,
                    label=selection.selected_strategy.name,
                    attributes={
                        "strategy_id": selection.selected_strategy.strategy_id,
                        "issue_id": selection.issue_id,
                        "incident_key": selection.incident_key,
                        "total_score": (
                            selection.ranked_candidates[0].score.total_score
                            if selection.ranked_candidates
                            else None
                        ),
                        "winning_reason": selection.winning_reason,
                    },
                    severity=selection.evaluation_context.severity,
                ),
            )
            issue_node_id = issue_nodes.get(selection.issue_id)
            if issue_node_id:
                self._add_edge(
                    edges,
                    GraphEdge(
                        source_id=issue_node_id,
                        target_id=node_id,
                        type=EdgeType.related_to,
                        description="Issue selected remediation strategy.",
                    ),
                )
            if selection.incident_key and selection.incident_key in incident_nodes:
                self._add_edge(
                    edges,
                    GraphEdge(
                        source_id=incident_nodes[selection.incident_key],
                        target_id=node_id,
                        type=EdgeType.contains,
                        description="Incident contains selected strategy.",
                    ),
                )
            for action_type in selection.selected_strategy.action_types:
                matching_action = next(
                    (
                        action
                        for action in action_by_id.values()
                        if action.issue_id == selection.issue_id and action.action_type == action_type
                    ),
                    None,
                )
                if matching_action is None:
                    continue
                action_node_id = f"action:{matching_action.id}"
                if action_node_id not in nodes:
                    continue
                self._add_edge(
                    edges,
                    GraphEdge(
                        source_id=node_id,
                        target_id=action_node_id,
                        type=EdgeType.executes,
                        description="Strategy maps to planned action.",
                    ),
                )
    def _add_playbook_execution_edges(
        self,
        edges: dict[tuple[str, str, EdgeType], GraphEdge],
        *,
        issue_nodes: dict[str, str],
        action_nodes: dict[str, str],
        playbook_executions: list[PlaybookExecution],
        issues: list[Issue],
        incident_key: str | None,
    ) -> None:
        issue_by_id = {issue.id: issue for issue in issues}
        for execution in playbook_executions:
            issue_id = execution.issue_id
            if not issue_id or issue_id not in issue_nodes:
                continue
            if incident_key:
                issue = issue_by_id.get(issue_id)
                if issue is None or issue.incident_key != incident_key:
                    continue
            for action_node_id in action_nodes.values():
                if not action_node_id.startswith(f"action:{issue_id}:"):
                    continue
                self._add_edge(
                    edges,
                    GraphEdge(
                        source_id=issue_nodes[issue_id],
                        target_id=action_node_id,
                        type=EdgeType.related_to,
                        description="Playbook execution timeline references action.",
                    ),
                )

    def _resolve_target_node_id(
        self,
        *,
        issue: Issue,
        service_nodes: dict[str, str],
        process_nodes: dict[str, str],
        port_nodes: dict[int, str],
    ) -> str | None:
        target = (issue.target or "").strip().lower()
        if not target:
            return None
        if target in service_nodes:
            return service_nodes[target]
        if target in process_nodes:
            return process_nodes[target]
        port = self._extract_port(target)
        if port is not None and port in port_nodes:
            return port_nodes[port]
        if issue.type in {"SERVICE_DOWN", "CRASH_LOOP"} and target in service_nodes:
            return service_nodes[target]
        if issue.type in {"SUSPICIOUS_PROCESS", "HIGH_RESOURCE_USAGE"} and target in process_nodes:
            return process_nodes[target]
        return None

    def _resolve_action_target(
        self,
        *,
        action: Action,
        service_nodes: dict[str, str],
        process_nodes: dict[str, str],
        port_nodes: dict[int, str],
    ) -> str | None:
        target = (action.target or "").strip().lower()
        if not target:
            return None
        if target in service_nodes:
            return service_nodes[target]
        if target in process_nodes:
            return process_nodes[target]
        port = self._extract_port(target)
        if port is not None and port in port_nodes:
            return port_nodes[port]
        return None

    def _extract_port(self, text: str) -> int | None:
        match = re.search(r"(\d{1,5})", text)
        if not match:
            return None
        port = int(match.group(1))
        if 0 < port <= 65535:
            return port
        return None

    def _build_metadata(
        self,
        nodes: dict[str, GraphNode],
        edges: dict[tuple[str, str, EdgeType], GraphEdge],
        snapshot: StateSnapshot,
        incidents: list[IncidentSummary | IncidentDetail],
        actions: list[Action],
        strategy_selections: list[StrategySelection],
        incident_key: str | None,
    ) -> dict:
        node_types = Counter(node.type.value for node in nodes.values())
        edge_types = Counter(edge.type.value for edge in edges.values())
        return {
            "host": snapshot.system_info.hostname,
            "platform": snapshot.system_info.os_name.lower(),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "node_type_counts": dict(node_types),
            "edge_type_counts": dict(edge_types),
            "issue_count": len([node for node in nodes.values() if node.type == NodeType.issue]),
            "incident_count": len([node for node in nodes.values() if node.type == NodeType.incident]),
            "action_count": len([node for node in nodes.values() if node.type == NodeType.action]),
            "strategy_count": len([node for node in nodes.values() if node.type == NodeType.strategy]),
            "source_incident_count": len(incidents),
            "source_action_count": len(actions),
            "source_strategy_count": len(strategy_selections),
            "incident_key": incident_key,
        }

    def _filter_graph(
        self,
        nodes: dict[str, GraphNode],
        edges: dict[tuple[str, str, EdgeType], GraphEdge],
        incident_key: str | None,
    ) -> tuple[dict[str, GraphNode], dict[tuple[str, str, EdgeType], GraphEdge]]:
        if not incident_key:
            return nodes, edges
        incident_node_id = f"incident:{incident_key}"
        if incident_node_id not in nodes:
            return nodes, edges

        keep_ids = {incident_node_id}
        queue = [incident_node_id]
        while queue:
            node_id = queue.pop(0)
            for edge in edges.values():
                if edge.source_id == node_id:
                    if node_id.startswith("host:") and edge.type == EdgeType.contains:
                        continue
                    other_id = edge.target_id
                elif edge.target_id == node_id:
                    other_id = edge.source_id
                else:
                    continue
                if other_id not in keep_ids:
                    keep_ids.add(other_id)
                    queue.append(other_id)

        filtered_nodes = {node_id: node for node_id, node in nodes.items() if node_id in keep_ids}
        filtered_edges = {
            key: edge
            for key, edge in edges.items()
            if edge.source_id in keep_ids and edge.target_id in keep_ids
        }
        return filtered_nodes, filtered_edges

    def _action_severity(self, risk_tier: str | None) -> str | None:
        if risk_tier in {"high", "blocked"}:
            return "high"
        if risk_tier == "medium":
            return "medium"
        if risk_tier in {"low", "observe"}:
            return "low"
        return None

    def _add_node(self, nodes: dict[str, GraphNode], node: GraphNode) -> None:
        nodes.setdefault(node.id, node)

    def _add_edge(
        self,
        edges: dict[tuple[str, str, EdgeType], GraphEdge],
        edge: GraphEdge,
    ) -> None:
        key = (edge.source_id, edge.target_id, edge.type)
        edges.setdefault(key, edge)
