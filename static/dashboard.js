const state = {
    platform: "linux",
    mode: "mock",
    lastAction: "snapshot",
    loading: false,
    data: null,
    lastRefresh: null,
    history: [],
    selectedHistoryEvent: null,
    incidents: [],
    baselineSummary: null,
    approvals: [],
    approvalDecisions: [],
    runtimeRecent: [],
    currentGraph: null,
    incidentGraph: null,
    selectedGraphNodeId: null,
    selectedIncidentKey: null,
};

const els = {};

document.addEventListener("DOMContentLoaded", () => {
    cacheElements();
    bindControls();
    applyControlState();
    loadView("snapshot");
});

function cacheElements() {
    const ids = [
        "platform-select",
        "mode-select",
        "refresh-btn",
        "snapshot-btn",
        "plan-btn",
        "execute-btn",
        "feedback-banner",
        "status-pill",
        "live-pill",
        "active-view-label",
        "status-copy",
        "risk-score",
        "risk-summary",
        "hero-platform",
        "hero-mode",
        "last-refresh",
        "health-summary",
        "summary-os",
        "summary-hostname",
        "summary-cpu",
        "summary-memory",
        "summary-disk",
        "summary-issues",
        "summary-critical",
        "summary-high",
        "summary-medium",
        "summary-low",
        "summary-health",
        "issues-panel",
        "issues-meta",
        "processes-panel",
        "processes-meta",
        "services-panel",
        "services-meta",
        "ports-panel",
        "logs-panel",
        "plan-meta",
        "candidate-count",
        "allowed-count",
        "approval-required-count",
        "blocked-count",
        "candidate-actions-panel",
        "allowed-actions-panel",
        "approval-required-actions-panel",
        "blocked-actions-panel",
        "strategy-count",
        "strategy-panel",
        "incident-state-count",
        "incident-state-panel",
        "strategy-selection-meta",
        "strategy-selected-count",
        "strategy-selected-panel",
        "strategy-alt-count",
        "strategy-alt-panel",
        "execute-meta",
        "executed-count",
        "verification-count",
        "executed-actions-panel",
        "verification-panel",
        "playbook-execution-count",
        "playbook-execution-panel",
        "approval-meta",
        "approval-pending-count",
        "approval-recent-count",
        "approval-queue-panel",
        "approval-recent-panel",
        "history-recent-meta",
        "history-list",
        "history-details",
        "baseline-panel",
        "baseline-meta",
        "runtime-meta",
        "runtime-tasks-panel",
        "runtime-policy-panel",
        "runtime-results-panel",
        "runtime-recent-panel",
        "graph-meta",
        "graph-summary",
        "graph-node-groups",
        "graph-node-detail",
        "graph-edge-panel",
        "incident-meta",
        "incident-list",
    ];

    ids.forEach((id) => {
        els[id] = document.getElementById(id);
    });
}

function bindControls() {
    els["platform-select"].addEventListener("change", (event) => {
        state.platform = event.target.value;
        applyControlState();
        loadView(state.lastAction);
    });

    els["mode-select"].addEventListener("change", (event) => {
        state.mode = event.target.value;
        applyControlState();
        loadView(state.lastAction);
    });

    els["refresh-btn"].addEventListener("click", () => loadView(state.lastAction));
    els["snapshot-btn"].addEventListener("click", () => loadView("snapshot"));
    els["plan-btn"].addEventListener("click", () => loadView("plan"));
    els["execute-btn"].addEventListener("click", () => loadView("execute"));
}

function applyControlState() {
    els["platform-select"].value = state.platform;
    els["mode-select"].value = state.mode;

    [
        ["snapshot-btn", "snapshot"],
        ["plan-btn", "plan"],
        ["execute-btn", "execute"],
    ].forEach(([id, action]) => {
        const button = els[id];
        const isActive = state.lastAction === action;
        button.classList.toggle("ring-2", isActive);
        button.classList.toggle("ring-white/40", isActive);
    });

    if (state.loading) {
        ["refresh-btn", "snapshot-btn", "plan-btn", "execute-btn"].forEach((id) => {
            els[id].disabled = true;
            els[id].classList.add("opacity-60", "cursor-not-allowed");
        });
    } else {
        ["refresh-btn", "snapshot-btn", "plan-btn", "execute-btn"].forEach((id) => {
            els[id].disabled = false;
            els[id].classList.remove("opacity-60", "cursor-not-allowed");
        });
    }
}

async function loadView(action) {
    state.lastAction = action;
    state.loading = true;
    state.incidentGraph = null;
    state.selectedIncidentKey = null;
    applyControlState();
    setBanner(`Loading ${action} telemetry for ${state.platform} in ${state.mode} mode...`, "info");
    renderLoadingState(action);

    try {
        const response = await fetch(buildUrl(action), {
            headers: {
                Accept: "application/json",
            },
        });

        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.detail || `Request failed with status ${response.status}`);
        }

        state.data = normalizeData(action, payload);
        state.lastRefresh = new Date();
        state.loading = false;
        applyControlState();
        renderAll();
        await loadHistoryTimeline();
        await loadRecentIncidents();
        await loadCurrentGraph();
        await loadApprovalCenter();
        await loadRuntimeRecent();
        setBanner(`${capitalize(action)} telemetry updated successfully.`, "info");
    } catch (error) {
        state.loading = false;
        applyControlState();
        setBanner(error.message || "Unable to load telemetry.", "error");
        renderErrorState(error.message || "Unable to load telemetry.");
    }
}

function buildUrl(action) {
    const params = new URLSearchParams({
        platform: state.platform,
        mode: state.mode,
    });
    return `/${action}?${params.toString()}`;
}

async function loadHistoryTimeline() {
    try {
        const params = new URLSearchParams({
            platform: state.platform,
            mode: state.mode,
            limit: 8,
        });
        const response = await fetch(`/history/recent?${params.toString()}`, {
            headers: { Accept: "application/json" },
        });
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.detail || `History request failed with status ${response.status}`);
        }

        state.history = payload || [];
        state.selectedHistoryEvent = state.history[0] || null;
        renderHistoryTimeline();
        if (state.selectedHistoryEvent) {
            await loadHistoryEventDetails(state.selectedHistoryEvent.event_id);
        }
    } catch (error) {
        console.error(error);
        els["history-list"].innerHTML = `<div class="empty-state">Unable to load history.</div>`;
        els["history-details"].innerHTML = `<div class="empty-state">History timeline unavailable.</div>`;
    }
}

async function loadHistoryEventDetails(eventId) {
    try {
        const response = await fetch(`/history/${encodeURIComponent(eventId)}`, {
            headers: { Accept: "application/json" },
        });
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.detail || `History event failed with status ${response.status}`);
        }
        state.selectedHistoryEvent = payload;
        renderHistoryDetails(payload);
    } catch (error) {
        console.error(error);
        els["history-details"].innerHTML = `<div class="empty-state">Unable to load event details.</div>`;
    }
}

async function loadRecentIncidents() {
    try {
        const params = new URLSearchParams({
            platform: state.platform,
            mode: state.mode,
            limit: 5,
        });
        const response = await fetch(`/incidents/recent?${params.toString()}`, {
            headers: { Accept: "application/json" },
        });
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.detail || `Incidents request failed with status ${response.status}`);
        }

        state.incidents = payload || [];
        renderIncidentList();
    } catch (error) {
        console.error(error);
        els["incident-meta"].textContent = "Recurring issue clusters";
        els["incident-list"].innerHTML = `<div class="empty-state">Unable to load incidents.</div>`;
    }
}

async function loadApprovalCenter() {
    try {
        const queueParams = new URLSearchParams({
            status: "pending",
            platform: state.platform,
            mode: state.mode,
            limit: 20,
        });
        const queueResponse = await fetch(`/approvals?${queueParams.toString()}`, {
            headers: { Accept: "application/json" },
        });
        const queuePayload = await queueResponse.json();
        if (!queueResponse.ok) {
            throw new Error(queuePayload.detail || `Approval queue request failed with status ${queueResponse.status}`);
        }

        const decisionResponse = await fetch("/approvals/recent?limit=20", {
            headers: { Accept: "application/json" },
        });
        const decisionPayload = await decisionResponse.json();
        if (!decisionResponse.ok) {
            throw new Error(decisionPayload.detail || `Approval decisions request failed with status ${decisionResponse.status}`);
        }

        state.approvals = queuePayload || [];
        state.approvalDecisions = decisionPayload || [];
        renderApprovalCenter();
    } catch (error) {
        console.error(error);
        els["approval-meta"].textContent = "Approval workflow unavailable";
        els["approval-queue-panel"].innerHTML = `<div class="empty-state">Unable to load pending approvals.</div>`;
        els["approval-recent-panel"].innerHTML = `<div class="empty-state">Unable to load approval decisions.</div>`;
    }
}

async function loadRuntimeRecent() {
    try {
        const params = new URLSearchParams({
            platform: state.platform,
            mode: state.mode,
            limit: 6,
        });
        const response = await fetch(`/runtime/observations/recent?${params.toString()}`, {
            headers: { Accept: "application/json" },
        });
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.detail || `Runtime observation request failed with status ${response.status}`);
        }
        state.runtimeRecent = payload || [];
        renderRuntimeObservation(state.data?.snapshot?.runtime_observation_trace || null, state.runtimeRecent);
    } catch (error) {
        console.error(error);
        els["runtime-meta"].textContent = "Runtime observation history unavailable";
        els["runtime-recent-panel"].innerHTML = `<div class="empty-state">Unable to load recent runtime observation batches.</div>`;
    }
}

async function loadCurrentGraph() {
    try {
        const params = new URLSearchParams({
            platform: state.platform,
            mode: state.mode,
        });
        const response = await fetch(`/graph/current?${params.toString()}`, {
            headers: { Accept: "application/json" },
        });
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.detail || `Graph request failed with status ${response.status}`);
        }
        state.currentGraph = payload;
        if (!state.selectedGraphNodeId || !graphHasNode(payload, state.selectedGraphNodeId)) {
            state.selectedGraphNodeId = payload.nodes?.find((node) => node.type === "host")?.id || payload.nodes?.[0]?.id || null;
        }
        renderGraphPanel();
    } catch (error) {
        console.error(error);
        els["graph-meta"].textContent = "Graph service unavailable";
        els["graph-summary"].innerHTML = emptyState("Unable to load host graph summary.");
        els["graph-node-groups"].innerHTML = emptyState("Unable to load dependency node topology.");
        els["graph-node-detail"].innerHTML = emptyState("No graph node selected.");
        els["graph-edge-panel"].innerHTML = emptyState("No dependency edges available.");
    }
}

async function loadIncidentGraph(incidentKey) {
    if (!incidentKey) return;
    try {
        const params = new URLSearchParams({ mode: state.mode });
        const response = await fetch(`/graph/incident/${encodeURIComponent(incidentKey)}?${params.toString()}`, {
            headers: { Accept: "application/json" },
        });
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.detail || `Incident graph request failed with status ${response.status}`);
        }
        state.selectedIncidentKey = incidentKey;
        state.incidentGraph = payload;
        state.selectedGraphNodeId = `incident:${incidentKey}`;
        if (!graphHasNode(payload, state.selectedGraphNodeId)) {
            state.selectedGraphNodeId = payload.nodes?.[0]?.id || null;
        }
        renderIncidentList();
        renderGraphPanel();
    } catch (error) {
        console.error(error);
        setBanner(error.message || "Unable to load incident graph context.", "error");
    }
}

function renderIncidentList() {
    if (!state.incidents || state.incidents.length === 0) {
        els["incident-meta"].textContent = "No recurring incident clusters detected";
        els["incident-list"].innerHTML = emptyState("No recurring incidents have been correlated yet.");
        return;
    }

    els["incident-meta"].textContent = `${state.incidents.length} recurring incident clusters detected`;
    els["incident-list"].innerHTML = state.incidents
        .map((incident) => {
            const badgeClass = getIncidentSeverityClass(incident.severity_summary);
            const lastSeen = formatDateTime(new Date(incident.last_seen_at));
            const eventCount = incident.related_event_ids?.length ?? 0;
            const isActive = state.selectedIncidentKey === incident.incident_key;
            return `
                <article class="incident-card ${isActive ? "incident-card-active" : ""}" data-incident-key="${escapeHtml(incident.incident_key)}">
                    <div class="incident-card-head">
                        <div>
                            <p class="text-xs uppercase tracking-[0.22em] text-slate-400">${escapeHtml(incident.issue_type)}</p>
                            <h4 class="mt-2 text-lg font-semibold text-white">${escapeHtml(incident.incident_title)}</h4>
                        </div>
                        <span class="status-badge ${badgeClass}">${escapeHtml(incident.severity_summary)}</span>
                    </div>
                    <p class="mt-3 text-sm leading-6 text-slate-300">Target: ${escapeHtml(incident.target || "global")} · Attention: ${escapeHtml(incident.recommended_attention_level)}</p>
                    <div class="mt-4 grid gap-3 sm:grid-cols-2">
                        <div class="result-column">
                            <p class="summary-label">Occurrences</p>
                            <p class="summary-value">${escapeHtml(String(incident.recurrence_count))}</p>
                        </div>
                        <div class="result-column">
                            <p class="summary-label">Last seen</p>
                            <p class="summary-value">${escapeHtml(lastSeen)}</p>
                        </div>
                    </div>
                    <div class="mt-4 flex flex-wrap gap-2 text-xs">
                        <span class="status-badge status-neutral">Trend: ${escapeHtml(incident.trend_direction)}</span>
                        <span class="status-badge status-neutral">Events: ${escapeHtml(String(eventCount))}</span>
                    </div>
                    <div class="mt-4">
                        <button type="button" class="btn-secondary incident-graph-btn" data-incident-key="${escapeHtml(incident.incident_key)}">
                            View Incident Graph
                        </button>
                    </div>
                </article>
            `;
        })
        .join("");

    els["incident-list"].querySelectorAll(".incident-graph-btn").forEach((button) => {
        button.addEventListener("click", () => {
            loadIncidentGraph(button.dataset.incidentKey);
        });
    });
}

function getIncidentSeverityClass(severitySummary) {
    const summary = String(severitySummary || "").toLowerCase();
    if (summary.includes("critical")) return "status-critical";
    if (summary.includes("high")) return "status-elevated";
    if (summary.includes("medium")) return "status-neutral";
    return "status-success";
}

function formatDateTime(date) {
    if (!(date instanceof Date) || Number.isNaN(date.getTime())) {
        return "--";
    }

    return new Intl.DateTimeFormat([], {
        year: "numeric",
        month: "short",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
    }).format(date);
}

function renderHistoryTimeline() {
    if (!state.history || state.history.length === 0) {
        els["history-list"].innerHTML = `<div class="empty-state">No history events available.</div>`;
        els["history-details"].innerHTML = `<div class="empty-state">Select an event to inspect a replay.</div>`;
        return;
    }

    const items = state.history
        .map((event) => {
            const isActive = state.selectedHistoryEvent && state.selectedHistoryEvent.event_id === event.event_id;
            return `
                <button type="button" data-event-id="${escapeHtml(event.event_id)}" class="history-item ${isActive ? "history-item-active" : ""}">
                    <div class="history-item-header">
                        <span class="history-event-type">${escapeHtml(event.event_type)}</span>
                        <span class="history-event-badge ${getHealthBadge(event.health_score)}">${escapeHtml(event.platform.toUpperCase())}</span>
                    </div>
                    <p class="history-item-copy">${escapeHtml(event.mode)} · ${escapeHtml(event.created_at)}</p>
                    <div class="history-item-stats">
                        <span>${escapeHtml(String(event.issue_count))} issues</span>
                        <span>${escapeHtml(String(event.risk_score))} risk</span>
                    </div>
                </button>
            `;
        })
        .join("");

    els["history-list"].innerHTML = items;
    els["history-list"].querySelectorAll("button[data-event-id]").forEach((button) => {
        button.addEventListener("click", () => loadHistoryEventDetails(button.dataset.eventId));
    });
}

function renderHistoryDetails(event) {
    if (!event) {
        els["history-details"].innerHTML = `<div class="empty-state">No event selected.</div>`;
        return;
    }

    els["history-details"].innerHTML = `
        <div class="history-details-shell">
            <p class="section-kicker">Event Replay</p>
            <h4 class="section-title">${escapeHtml(event.event_type)} · ${escapeHtml(event.platform)} / ${escapeHtml(event.mode)}</h4>
            <div class="mt-4 grid gap-3 sm:grid-cols-2">
                <div class="result-column">
                    <p class="summary-label">Recorded</p>
                    <p class="summary-value">${escapeHtml(event.created_at)}</p>
                </div>
                <div class="result-column">
                    <p class="summary-label">Issues</p>
                    <p class="summary-value">${escapeHtml(String(event.issue_count))}</p>
                </div>
                <div class="result-column">
                    <p class="summary-label">Health</p>
                    <p class="summary-value">${escapeHtml(String(event.health_score))}</p>
                </div>
                <div class="result-column">
                    <p class="summary-label">Risk</p>
                    <p class="summary-value">${escapeHtml(String(event.risk_score))}</p>
                </div>
            </div>
            <div class="mt-4 rounded-2xl border border-white/10 bg-black/10 p-4">
                <pre class="history-json">${escapeHtml(JSON.stringify(event.payload, null, 2))}</pre>
            </div>
        </div>
    `;
}

function getHealthBadge(healthScore) {
    if (healthScore >= 85) return "status-success";
    if (healthScore >= 55) return "status-neutral";
    return "status-critical";
}

function normalizeData(action, payload) {
    if (action === "snapshot") {
        return {
            snapshot: payload,
            candidate_actions: [],
            allowed_actions: [],
            remediation_strategies: [],
            incident_states: [],
            playbook_executions: [],
            dispatch: { executed_actions: [] },
            verification_results: [],
            view: action,
        };
    }

    return {
        ...payload,
        dispatch: payload.dispatch || { executed_actions: [] },
        verification_results: payload.verification_results || [],
        strategy_selections: payload.strategy_selections || [],
        view: action,
    };
}

function renderAll() {
    const snapshot = state.data.snapshot;
    const issues = snapshot.issues || [];
    const candidateActions = state.data.candidate_actions || [];
    const allowedActions = state.data.allowed_actions || [];
    const approvalRequiredActions = state.data.approval_required_actions || [];
    const blockedActions = state.data.blocked_actions || [];
    const remediationStrategies = state.data.remediation_strategies || [];
    const strategySelections = state.data.strategy_selections || [];
    const incidentStates = state.data.incident_states || [];
    const playbookExecutions = state.data.playbook_executions || [];
    const executedActions = state.data.dispatch.executed_actions || [];
    const verificationResults = state.data.verification_results || [];
    const risk = computeRisk(snapshot);

    renderHero(snapshot, risk, issues, candidateActions, allowedActions);
    renderSummary(snapshot, issues, candidateActions, allowedActions);
    renderIssues(issues);
    renderProcesses(snapshot.processes || []);
    renderServices(snapshot.services || []);
    renderBaselineSummary(snapshot.baseline_summary);
    renderPorts(snapshot.open_ports || []);
    renderLogs(snapshot.recent_logs || []);
    renderPlan(candidateActions, allowedActions, approvalRequiredActions, blockedActions);
    renderStrategySelectionBoard(strategySelections);
    renderExecution(executedActions, verificationResults);
    renderStrategies(remediationStrategies, incidentStates);
    renderPlaybookExecutions(playbookExecutions);
    renderApprovalCenter();
    renderRuntimeObservation(snapshot.runtime_observation_trace || null, state.runtimeRecent || []);
    renderGraphPanel();
    renderHistoryTimeline();
}

function renderLoadingState(action) {
    const loadingBlock = `<div class="empty-state">Streaming ${escapeHtml(action)} view...</div>`;
    [
        "issues-panel",
        "processes-panel",
        "services-panel",
        "baseline-panel",
        "runtime-tasks-panel",
        "runtime-policy-panel",
        "runtime-results-panel",
        "runtime-recent-panel",
        "graph-summary",
        "graph-node-groups",
        "graph-node-detail",
        "graph-edge-panel",
        "ports-panel",
        "logs-panel",
        "candidate-actions-panel",
        "allowed-actions-panel",
        "approval-required-actions-panel",
        "blocked-actions-panel",
        "strategy-panel",
        "incident-state-panel",
        "strategy-selected-panel",
        "strategy-alt-panel",
        "executed-actions-panel",
        "verification-panel",
        "playbook-execution-panel",
        "approval-queue-panel",
        "approval-recent-panel",
    ].forEach((id) => {
        els[id].innerHTML = loadingBlock;
    });
    els["graph-meta"].textContent = "Loading graph topology...";
    els["strategy-selection-meta"].textContent = "Evaluating deterministic strategy competition...";
    els["status-pill"].textContent = "Loading";
    els["status-pill"].className = "status-pill status-idle";
    els["active-view-label"].textContent = capitalize(action);
    els["status-copy"].textContent = "Collecting the latest telemetry and rebuilding dashboard panels.";
}

function renderErrorState(message) {
    const errorBlock = `<div class="empty-state">${escapeHtml(message)}</div>`;
    [
        "issues-panel",
        "processes-panel",
        "services-panel",
        "baseline-panel",
        "runtime-tasks-panel",
        "runtime-policy-panel",
        "runtime-results-panel",
        "runtime-recent-panel",
        "graph-summary",
        "graph-node-groups",
        "graph-node-detail",
        "graph-edge-panel",
        "ports-panel",
        "logs-panel",
        "candidate-actions-panel",
        "allowed-actions-panel",
        "approval-required-actions-panel",
        "blocked-actions-panel",
        "strategy-panel",
        "incident-state-panel",
        "strategy-selected-panel",
        "strategy-alt-panel",
        "executed-actions-panel",
        "verification-panel",
        "playbook-execution-panel",
        "approval-queue-panel",
        "approval-recent-panel",
    ].forEach((id) => {
        els[id].innerHTML = errorBlock;
    });
    els["graph-meta"].textContent = "Graph unavailable";
    els["strategy-selection-meta"].textContent = "Strategy board unavailable";
    els["status-pill"].textContent = "Attention";
    els["status-pill"].className = "status-pill status-critical";
    els["status-copy"].textContent = message;
}

function renderApprovalCenter() {
    const approvals = state.approvals || [];
    const decisions = state.approvalDecisions || [];
    els["approval-pending-count"].textContent = `${approvals.length}`;
    els["approval-recent-count"].textContent = `${decisions.length}`;
    els["approval-meta"].textContent = approvals.length
        ? `${approvals.length} pending operator approval request(s)`
        : "No pending approval requests for the selected target";

    if (!approvals.length) {
        els["approval-queue-panel"].innerHTML = emptyState("Approval queue is clear.");
    } else {
        els["approval-queue-panel"].innerHTML = approvals
            .map((item) => {
                const request = item.request || {};
                return `
                    <article class="approval-card">
                        <div class="flex flex-wrap items-start justify-between gap-3">
                            <div>
                                <p class="text-xs uppercase tracking-[0.2em] text-slate-400">${escapeHtml(item.incident_title || request.incident_key)}</p>
                                <h4 class="mt-2 text-lg font-semibold text-white">${escapeHtml(request.action_type || "unknown_action")}</h4>
                            </div>
                            <span class="status-badge status-warning">${escapeHtml(request.status || "pending")}</span>
                        </div>
                        <p class="mt-3 text-sm leading-6 text-slate-300">${escapeHtml(request.justification_summary || request.policy_reason || "No justification provided.")}</p>
                        <div class="mt-3 flex flex-wrap gap-2 text-xs">
                            <span class="status-badge status-neutral">Playbook: ${escapeHtml(item.playbook_name || request.playbook_id || "unknown")}</span>
                            <span class="status-badge status-neutral">Step: ${escapeHtml(item.step_name || request.step_id || "unknown")}</span>
                            <span class="status-badge status-neutral">Risk: ${escapeHtml(request.risk_tier || "unknown")}</span>
                            <span class="status-badge status-neutral">Confidence: ${escapeHtml(formatConfidence(request.action_confidence || 0))}</span>
                            <span class="status-badge status-neutral">Created: ${escapeHtml(formatDateTime(new Date(request.created_at)))}</span>
                        </div>
                        <div class="mt-4 flex flex-wrap gap-3">
                            <button type="button" class="btn-primary btn-approve" data-request-id="${escapeHtml(request.request_id)}">Approve</button>
                            <button type="button" class="btn-danger btn-deny" data-request-id="${escapeHtml(request.request_id)}">Deny</button>
                        </div>
                    </article>
                `;
            })
            .join("");

        els["approval-queue-panel"].querySelectorAll(".btn-approve").forEach((button) => {
            button.addEventListener("click", () => handleApprovalDecision(button.dataset.requestId, "approve"));
        });
        els["approval-queue-panel"].querySelectorAll(".btn-deny").forEach((button) => {
            button.addEventListener("click", () => handleApprovalDecision(button.dataset.requestId, "deny"));
        });
    }

    if (!decisions.length) {
        els["approval-recent-panel"].innerHTML = emptyState("No recent approval decisions recorded.");
    } else {
        els["approval-recent-panel"].innerHTML = decisions
            .map((decision) => `
                <article class="approval-decision-card">
                    <div class="flex flex-wrap items-start justify-between gap-3">
                        <h4 class="text-lg font-semibold text-white">${escapeHtml(decision.operator_action)}</h4>
                        <span class="status-badge ${decision.operator_action === "approve" ? "status-success" : "status-unhealthy"}">${escapeHtml(decision.resulting_status)}</span>
                    </div>
                    <p class="mt-3 text-sm leading-6 text-slate-300">${escapeHtml(decision.decision_reason || "No reason provided.")}</p>
                    <div class="mt-3 flex flex-wrap gap-2 text-xs">
                        <span class="status-badge status-neutral">Request: ${escapeHtml(decision.request_id)}</span>
                        <span class="status-badge status-neutral">At: ${escapeHtml(formatDateTime(new Date(decision.decided_at)))}</span>
                    </div>
                </article>
            `)
            .join("");
    }
}

async function handleApprovalDecision(requestId, action) {
    const actionLabel = action === "approve" ? "approve" : "deny";
    const defaultReason =
        action === "approve"
            ? "Operator approved this remediation step after review."
            : "Operator denied this remediation step pending further investigation.";
    const decisionReason = window.prompt(`Reason to ${actionLabel} request ${requestId}:`, defaultReason);
    if (!decisionReason || !decisionReason.trim()) {
        return;
    }

    try {
        const response = await fetch(`/approvals/${encodeURIComponent(requestId)}/${action}`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                Accept: "application/json",
            },
            body: JSON.stringify({ decision_reason: decisionReason.trim() }),
        });
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.detail || `Approval decision failed with status ${response.status}`);
        }
        setBanner(`Approval ${actionLabel}d for request ${requestId}.`, "info");
        await loadView(state.lastAction);
    } catch (error) {
        setBanner(error.message || "Unable to submit approval decision.", "error");
    }
}

function renderRuntimeObservation(trace, recentBatches) {
    if (!trace) {
        els["runtime-meta"].textContent = "No runtime observation trace for current snapshot";
        els["runtime-tasks-panel"].innerHTML = emptyState("Runtime observation trace is available for macOS live mode snapshots.");
        els["runtime-policy-panel"].innerHTML = emptyState("No command policy decisions for this snapshot.");
        els["runtime-results-panel"].innerHTML = emptyState("No command invocation results for this snapshot.");
    } else {
        const taskCount = (trace.tasks || []).length;
        const decisionCount = (trace.policy_decisions || []).length;
        const resultCount = (trace.results || []).length;
        const partialFailure = Boolean(trace.batch?.partial_failure);
        els["runtime-meta"].textContent = `Batch ${trace.batch?.batch_id || "unknown"} · ${taskCount} tasks · ${resultCount} command results${partialFailure ? " · partial failure" : ""}`;

        els["runtime-tasks-panel"].innerHTML = (trace.tasks || []).length
            ? (trace.tasks || [])
                .map((task) => `
                    <article class="runtime-card">
                        <div class="flex flex-wrap items-center justify-between gap-3">
                            <h4 class="text-lg font-semibold text-white">${escapeHtml(task.task_name)}</h4>
                            <span class="status-badge ${task.status === "success" ? "status-success" : task.status === "partial_failure" ? "status-warning" : "status-unhealthy"}">${escapeHtml(task.status)}</span>
                        </div>
                        <p class="mt-2 text-sm text-slate-300">${escapeHtml(task.status_reason || "No task status reason.")}</p>
                        <div class="mt-3 flex flex-wrap gap-2 text-xs">
                            <span class="status-badge status-neutral">Task ID: ${escapeHtml(task.task_id)}</span>
                            <span class="status-badge status-neutral">Parsed: ${escapeHtml(task.parsed_artifact_type || "none")}</span>
                        </div>
                    </article>
                `)
                .join("")
            : emptyState("No observation tasks were recorded.");

        els["runtime-policy-panel"].innerHTML = decisionCount
            ? (trace.policy_decisions || [])
                .slice(0, 20)
                .map((decision) => `
                    <article class="runtime-card">
                        <div class="flex flex-wrap items-center justify-between gap-3">
                            <h4 class="text-lg font-semibold text-white">${escapeHtml(decision.command_name)} ${escapeHtml((decision.args || []).join(" "))}</h4>
                            <span class="status-badge ${decision.allowed ? "status-success" : "status-unhealthy"}">${decision.allowed ? "allowed" : "blocked"}</span>
                        </div>
                        <p class="mt-2 text-sm text-slate-300">${escapeHtml(decision.reason)}</p>
                        <div class="mt-3 flex flex-wrap gap-2 text-xs">
                            <span class="status-badge status-neutral">Safety: ${escapeHtml(decision.safety_class || "unknown")}</span>
                            <span class="status-badge status-neutral">${escapeHtml(decision.platform)} / ${escapeHtml(decision.mode)}</span>
                        </div>
                    </article>
                `)
                .join("")
            : emptyState("No command policy decisions available.");

        els["runtime-results-panel"].innerHTML = resultCount
            ? (trace.results || [])
                .slice(0, 20)
                .map((result) => `
                    <article class="runtime-card">
                        <div class="flex flex-wrap items-center justify-between gap-3">
                            <h4 class="text-lg font-semibold text-white">${escapeHtml(result.command_name)} ${escapeHtml((result.args || []).join(" "))}</h4>
                            <span class="status-badge ${result.success ? "status-success" : "status-unhealthy"}">${result.success ? "success" : "failed"}</span>
                        </div>
                        <p class="mt-2 text-sm text-slate-300">${escapeHtml(result.parsed_artifact_summary || result.stdout_summary || "No parsed summary.")}</p>
                        <div class="mt-3 flex flex-wrap gap-2 text-xs">
                            <span class="status-badge status-neutral">Invocation: ${escapeHtml(result.invocation_id)}</span>
                            <span class="status-badge status-neutral">Exit: ${escapeHtml(String(result.exit_code))}</span>
                            <span class="status-badge status-neutral">Artifact: ${escapeHtml(result.parsed_artifact_type || "none")}</span>
                        </div>
                    </article>
                `)
                .join("")
            : emptyState("No command result rows recorded.");
    }

    els["runtime-recent-panel"].innerHTML = recentBatches && recentBatches.length
        ? recentBatches
            .map((batchTrace) => `
                <article class="runtime-card">
                    <div class="flex flex-wrap items-center justify-between gap-3">
                        <h4 class="text-lg font-semibold text-white">${escapeHtml(batchTrace.batch?.batch_id || "unknown")}</h4>
                        <span class="status-badge ${batchTrace.batch?.partial_failure ? "status-warning" : "status-success"}">${batchTrace.batch?.partial_failure ? "partial failure" : "success"}</span>
                    </div>
                    <div class="mt-3 flex flex-wrap gap-2 text-xs">
                        <span class="status-badge status-neutral">Tasks: ${escapeHtml(String(batchTrace.batch?.task_count || 0))}</span>
                        <span class="status-badge status-neutral">Commands: ${escapeHtml(String((batchTrace.results || []).length))}</span>
                        <span class="status-badge status-neutral">Started: ${escapeHtml(formatDateTime(new Date(batchTrace.batch?.requested_at)))}</span>
                    </div>
                </article>
            `)
            .join("")
        : emptyState("No recent runtime observation batches persisted.");
}

function getActiveGraph() {
    return state.incidentGraph || state.currentGraph;
}

function graphHasNode(graph, nodeId) {
    if (!graph || !nodeId) return false;
    return (graph.nodes || []).some((node) => node.id === nodeId);
}

function selectGraphNodeForIssue(issueId, target) {
    const graph = getActiveGraph();
    if (!graph || !issueId) return;
    const issueNodeId = `issue:${issueId}`;
    if (graphHasNode(graph, issueNodeId)) {
        state.selectedGraphNodeId = issueNodeId;
        renderGraphPanel();
        return;
    }
    const targetNodeId = findNodeIdByTarget(graph, target);
    if (targetNodeId) {
        state.selectedGraphNodeId = targetNodeId;
        renderGraphPanel();
    }
}

function findNodeIdByTarget(graph, target) {
    const normalizedTarget = String(target || "").trim().toLowerCase();
    if (!normalizedTarget) return null;
    const maybePort = Number.parseInt(normalizedTarget, 10);
    const directPortNode = Number.isFinite(maybePort) ? `port:${maybePort}` : null;
    if (directPortNode && graphHasNode(graph, directPortNode)) return directPortNode;

    const candidateService = `service:${normalizedTarget}`;
    if (graphHasNode(graph, candidateService)) return candidateService;

    const processNode = (graph.nodes || []).find(
        (node) =>
            node.type === "process" &&
            String(node.label || "").toLowerCase() === normalizedTarget
    );
    return processNode?.id || null;
}

function graphNodeSeverityClass(severity) {
    const normalized = String(severity || "").toLowerCase();
    if (!normalized) return "";
    if (normalized.includes("critical")) return "graph-node-chip-critical";
    if (normalized.includes("high")) return "graph-node-chip-high";
    if (normalized.includes("medium")) return "graph-node-chip-medium";
    return "graph-node-chip-low";
}

function renderGraphPanel() {
    const graph = getActiveGraph();
    if (!graph) {
        els["graph-meta"].textContent = "No graph telemetry loaded yet";
        els["graph-summary"].innerHTML = emptyState("Load a snapshot, plan, or execute view to build a graph model.");
        els["graph-node-groups"].innerHTML = emptyState("Graph node topology will appear after graph data is loaded.");
        els["graph-node-detail"].innerHTML = emptyState("Select a node to inspect dependencies and related entities.");
        els["graph-edge-panel"].innerHTML = emptyState("No dependency edges available.");
        return;
    }

    const metadata = graph.metadata || {};
    const nodeCount = graph.nodes?.length || 0;
    const edgeCount = graph.edges?.length || 0;
    const incidentScope = state.incidentGraph
        ? `incident scope ${state.selectedIncidentKey || metadata.incident_key || "selected"}`
        : "current host scope";
    els["graph-meta"].textContent = `${nodeCount} nodes · ${edgeCount} edges · ${incidentScope}`;

    const summaryCards = [
        ["Nodes", nodeCount],
        ["Edges", edgeCount],
        ["Issues", metadata.issue_count || 0],
        ["Incidents", metadata.incident_count || 0],
        ["Actions", metadata.action_count || 0],
        ["Risk", state.data?.snapshot?.risk_score ?? "--"],
    ];
    els["graph-summary"].innerHTML = `
        <div class="graph-summary-grid">
            ${summaryCards
                .map(
                    ([label, value]) => `
                        <article class="graph-summary-card">
                            <p class="summary-label">${escapeHtml(String(label))}</p>
                            <p class="summary-value">${escapeHtml(String(value))}</p>
                        </article>
                    `
                )
                .join("")}
        </div>
    `;

    const nodeTypeOrder = ["host", "incident", "issue", "strategy", "action", "service", "process", "port"];
    const groupedNodes = nodeTypeOrder
        .map((type) => [type, (graph.nodes || []).filter((node) => node.type === type)])
        .filter(([, group]) => group.length > 0);

    if (!state.selectedGraphNodeId || !graphHasNode(graph, state.selectedGraphNodeId)) {
        state.selectedGraphNodeId = graph.nodes?.[0]?.id || null;
    }

    els["graph-node-groups"].innerHTML = groupedNodes
        .map(([type, group]) => `
            <section class="graph-node-group">
                <h4 class="graph-node-group-title">${escapeHtml(type)} (${group.length})</h4>
                <div class="graph-node-chip-grid">
                    ${group
                        .map((node) => {
                            const activeClass = node.id === state.selectedGraphNodeId ? "graph-node-chip-active" : "";
                            const severityClass = graphNodeSeverityClass(node.severity);
                            return `
                                <button
                                    type="button"
                                    class="graph-node-chip ${activeClass} ${severityClass}"
                                    data-node-id="${escapeHtml(node.id)}"
                                >
                                    ${escapeHtml(node.label)}
                                </button>
                            `;
                        })
                        .join("")}
                </div>
            </section>
        `)
        .join("");

    els["graph-node-groups"].querySelectorAll("button[data-node-id]").forEach((button) => {
        button.addEventListener("click", () => {
            state.selectedGraphNodeId = button.dataset.nodeId;
            renderGraphPanel();
        });
    });

    const selectedNode = (graph.nodes || []).find((node) => node.id === state.selectedGraphNodeId) || null;
    if (!selectedNode) {
        els["graph-node-detail"].innerHTML = emptyState("No graph node selected.");
        els["graph-edge-panel"].innerHTML = emptyState("No dependency edges available.");
        return;
    }

    const selectedAttributes = selectedNode.attributes || {};
    const attributeRows = Object.entries(selectedAttributes)
        .slice(0, 10)
        .map(
            ([key, value]) => `
                <div class="graph-detail-row">
                    <span class="graph-detail-key">${escapeHtml(key.replaceAll("_", " "))}</span>
                    <span class="graph-detail-value">${escapeHtml(String(value))}</span>
                </div>
            `
        )
        .join("");

    els["graph-node-detail"].innerHTML = `
        <article class="graph-detail-card">
            <div class="flex flex-wrap items-center justify-between gap-2">
                <h4 class="text-lg font-semibold text-white">${escapeHtml(selectedNode.label)}</h4>
                <span class="status-badge status-neutral">${escapeHtml(selectedNode.type)}</span>
            </div>
            <p class="mt-2 text-xs text-slate-400">${escapeHtml(selectedNode.id)}</p>
            <div class="graph-detail-attributes">
                ${attributeRows || `<div class="empty-state">No node attributes recorded.</div>`}
            </div>
        </article>
    `;

    const relatedEdges = (graph.edges || []).filter(
        (edge) => edge.source_id === selectedNode.id || edge.target_id === selectedNode.id
    );
    if (!relatedEdges.length) {
        els["graph-edge-panel"].innerHTML = emptyState("No direct dependencies for this node.");
        return;
    }

    els["graph-edge-panel"].innerHTML = relatedEdges
        .slice(0, 50)
        .map((edge) => {
            const source = graph.nodes?.find((node) => node.id === edge.source_id);
            const target = graph.nodes?.find((node) => node.id === edge.target_id);
            return `
                <article class="graph-edge-card">
                    <div class="flex flex-wrap items-center justify-between gap-2">
                        <span class="status-badge status-neutral">${escapeHtml(edge.type)}</span>
                        <span class="text-xs text-slate-400">${escapeHtml(edge.source_id)} → ${escapeHtml(edge.target_id)}</span>
                    </div>
                    <p class="mt-2 text-sm text-slate-300">
                        ${escapeHtml(source?.label || edge.source_id)}
                        <span class="text-slate-500">→</span>
                        ${escapeHtml(target?.label || edge.target_id)}
                    </p>
                    <p class="mt-2 text-xs text-slate-400">${escapeHtml(edge.description || "No edge description.")}</p>
                </article>
            `;
        })
        .join("");
}

function renderHero(snapshot, risk, issues, candidateActions, allowedActions) {
    els["active-view-label"].textContent = capitalize(state.data.view);
    els["status-copy"].textContent = `${issues.length} issues observed, ${allowedActions.length} actions policy-approved.`;
    els["risk-score"].textContent = `${snapshot.risk_score}`;
    els["risk-summary"].textContent = `${risk.label} risk posture. Health score ${snapshot.health_score}/100.`;
    els["hero-platform"].textContent = snapshot.system_info.os_name;
    els["hero-mode"].textContent = `Mode: ${capitalize(state.mode)}`;
    els["live-pill"].textContent = `Mode: ${capitalize(state.mode)}`;
    els["last-refresh"].textContent = formatTime(state.lastRefresh);
    els["health-summary"].textContent = `${allowedActions.length}/${candidateActions.length || 0} actions allowed by policy.`;

    els["status-pill"].textContent = risk.label;
    els["status-pill"].className = `status-pill ${risk.statusClass}`;
}

function renderSummary(snapshot, issues, candidateActions, allowedActions) {
    const issueSummary = snapshot.issue_summary || {
        critical_count: 0,
        high_count: 0,
        medium_count: 0,
        low_count: 0,
        total_count: issues.length,
    };

    els["summary-os"].textContent = snapshot.system_info.os_version;
    els["summary-hostname"].textContent = snapshot.system_info.hostname;
    els["summary-cpu"].textContent = formatPercent(snapshot.resources.cpu_percent);
    els["summary-memory"].textContent = `${formatNumber(snapshot.resources.memory_used_mb)} / ${formatNumber(snapshot.resources.memory_total_mb)} MB`;
    els["summary-disk"].textContent = `${formatPercent(snapshot.resources.disk_usage_percent)} (${snapshot.resources.disk_used_gb.toFixed(1)} GB)`;
    els["summary-issues"].textContent = `${issueSummary.total_count}`;
    els["summary-critical"].textContent = `${issueSummary.critical_count}`;
    els["summary-high"].textContent = `${issueSummary.high_count}`;
    els["summary-medium"].textContent = `${issueSummary.medium_count}`;
    els["summary-low"].textContent = `${issueSummary.low_count}`;
    els["summary-health"].textContent = `${snapshot.health_score}`;
}

function renderIssues(issues) {
    els["issues-meta"].textContent = `${issues.length} issue${issues.length === 1 ? "" : "s"} detected, sorted by priority`;
    if (!issues.length) {
        els["issues-panel"].innerHTML = emptyState("No issues detected. The current snapshot looks clean and within conservative thresholds.");
        return;
    }

    els["issues-panel"].innerHTML = issues
        .map((issue) => {
            const severity = (issue.severity || "low").toLowerCase();
            const severityLabel = severity.toUpperCase();
            const target = issue.target || "unscoped";
            const evidenceHtml = (issue.evidence || [])
                .map((item) => `<li>${escapeHtml(item)}</li>`)
                .join("");
            return `
                <article class="issue-card issue-card-${escapeHtml(severity)}" data-issue-id="${escapeHtml(issue.id || "")}" data-issue-target="${escapeHtml(target)}">
                    <div class="flex flex-wrap items-center justify-between gap-3">
                        <div>
                            <p class="text-xs uppercase tracking-[0.22em] text-slate-400">${escapeHtml(issue.category || "issue")}</p>
                            <h4 class="mt-2 text-lg font-semibold text-white">${escapeHtml(issue.type)}</h4>
                        </div>
                        <span class="severity-badge severity-${escapeHtml(severity)}">${escapeHtml(severityLabel)}</span>
                    </div>
                    <p class="mt-4 text-sm leading-6 text-slate-300">${escapeHtml(issue.description || "No description provided.")}</p>
                    <details class="mt-4 rounded-xl border border-white/10 bg-slate-950/30 px-4 py-3 text-sm text-slate-300">
                        <summary class="font-medium text-white">Issue trace details</summary>
                        <div class="mt-3 space-y-2">
                            ${issue.evidence && issue.evidence.length ? `<div><strong>Evidence:</strong><ul class="list-disc pl-5">${evidenceHtml}</ul></div>` : ""}
                            ${issue.detection_reason ? `<div><strong>Detection:</strong> ${escapeHtml(issue.detection_reason)}</div>` : ""}
                            ${issue.severity_reason ? `<div><strong>Severity:</strong> ${escapeHtml(issue.severity_reason)}</div>` : ""}
                            ${issue.confidence_reason ? `<div><strong>Confidence:</strong> ${escapeHtml(issue.confidence_reason)}</div>` : ""}
                        </div>
                    </details>
                    <div class="mt-4 flex flex-wrap gap-2 text-xs">
                        <span class="status-badge status-neutral">Target: ${escapeHtml(target)}</span>
                        <span class="status-badge status-neutral">Priority: ${escapeHtml(String(issue.priority_score ?? "--"))}</span>
                        <span class="status-badge status-neutral">Confidence: ${escapeHtml(formatConfidence(issue.confidence))}</span>
                        <span class="status-badge status-neutral">ID: ${escapeHtml(issue.id || "n/a")}</span>
                    </div>
                    ${renderIssueAnomalySection(issue)}
                </article>
            `;
        })
        .join("");

    els["issues-panel"].querySelectorAll("article[data-issue-id]").forEach((article) => {
        article.addEventListener("click", () => {
            const issueId = article.dataset.issueId;
            const target = article.dataset.issueTarget;
            selectGraphNodeForIssue(issueId, target);
        });
    });
}

function renderProcesses(processes) {
    els["processes-meta"].textContent = `${processes.length} process${processes.length === 1 ? "" : "es"} displayed`;
    if (!processes.length) {
        els["processes-panel"].innerHTML = emptyState("No process telemetry available for this target.");
        return;
    }

    const rows = processes
        .map(
            (process) => `
                <tr>
                    <td class="font-medium text-white">${escapeHtml(process.name)}</td>
                    <td class="mono text-slate-300">${escapeHtml(String(process.pid ?? "--"))}</td>
                    <td class="mono text-slate-300">${formatPercent(process.cpu_percent)}</td>
                    <td class="mono text-slate-300">${formatNumber(process.memory_mb)} MB</td>
                    <td><span class="status-badge ${process.status === "running" ? "status-running" : "status-neutral"}">${escapeHtml(process.status || "unknown")}</span></td>
                </tr>
            `
        )
        .join("");

    els["processes-panel"].innerHTML = `
        <table class="process-table">
            <thead>
                <tr>
                    <th>Name</th>
                    <th>PID</th>
                    <th>CPU</th>
                    <th>Memory</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>
    `;
}

function renderServices(services) {
    els["services-meta"].textContent = `${services.length} service${services.length === 1 ? "" : "s"} observed`;
    if (!services.length) {
        els["services-panel"].innerHTML = emptyState("Service inspection is currently minimal for this view.");
        return;
    }

    els["services-panel"].innerHTML = services
        .map((service) => {
            const isHealthy = (service.status || "").toLowerCase() === "running";
            return `
                <article class="service-card">
                    <div class="flex items-start justify-between gap-3">
                        <div>
                            <h4 class="text-lg font-semibold text-white">${escapeHtml(service.name)}</h4>
                            <p class="mt-2 text-sm leading-6 text-slate-300">${escapeHtml(service.description || "No description provided.")}</p>
                        </div>
                        <span class="status-badge ${isHealthy ? "status-running" : "status-unhealthy"}">${escapeHtml(service.status || "unknown")}</span>
                    </div>
                    <div class="mt-4 flex flex-wrap gap-2 text-xs">
                        <span class="status-badge status-neutral">Restarts: ${escapeHtml(String(service.restart_count ?? 0))}</span>
                    </div>
                </article>
            `;
        })
        .join("");
}

function renderBaselineSummary(summary) {
    if (!summary || !summary.host_baseline) {
        els["baseline-meta"].textContent = "No baseline data available yet.";
        els["baseline-panel"].innerHTML = emptyState("Baseline modeling requires prior historical snapshots.");
        return;
    }

    const baseline = summary.host_baseline;
    const comparisons = summary.baseline_comparisons || [];
    const signals = summary.deviation_signals || [];
    const anomalyScore = summary.anomaly_score != null ? `${summary.anomaly_score * 100}%` : "0%";

    els["baseline-meta"].textContent = `${signals.length} anomaly signal${signals.length === 1 ? "" : "s"} detected`;
    els["baseline-panel"].innerHTML = `
        <div class="baseline-card">
            <p class="text-xs uppercase tracking-[0.22em] text-slate-400">Baseline host</p>
            <h4 class="mt-2 text-lg font-semibold text-white">${escapeHtml(baseline.hostname || baseline.platform)}</h4>
            <p class="mt-3 text-sm leading-6 text-slate-300">${escapeHtml(baseline.event_count)} recent event${baseline.event_count === 1 ? "" : "s"} used for baseline.</p>
            <div class="mt-4 grid gap-3 sm:grid-cols-2">
                <div class="result-column">
                    <p class="summary-label">Avg CPU</p>
                    <p class="summary-value">${escapeHtml(baseline.avg_cpu_percent.toFixed(1))}%</p>
                </div>
                <div class="result-column">
                    <p class="summary-label">Avg Memory</p>
                    <p class="summary-value">${escapeHtml(baseline.avg_memory_used_mb.toFixed(0))} MB</p>
                </div>
                <div class="result-column">
                    <p class="summary-label">Avg Disk</p>
                    <p class="summary-value">${escapeHtml(baseline.avg_disk_usage_percent.toFixed(1))}%</p>
                </div>
                <div class="result-column">
                    <p class="summary-label">Avg Risk</p>
                    <p class="summary-value">${escapeHtml(baseline.avg_risk_score.toFixed(1))}</p>
                </div>
                <div class="result-column">
                    <p class="summary-label">Avg Health</p>
                    <p class="summary-value">${escapeHtml(baseline.avg_health_score.toFixed(1))}</p>
                </div>
                <div class="result-column">
                    <p class="summary-label">Anomaly Score</p>
                    <p class="summary-value">${escapeHtml(anomalyScore)}</p>
                </div>
            </div>
        </div>
        <div class="baseline-card baseline-card-details">
            <p class="text-xs uppercase tracking-[0.22em] text-slate-400">Deviation overview</p>
            <div class="mt-4 space-y-3">
                ${comparisons
                    .map(
                        (comparison) => `
                            <div class="baseline-compare-row">
                                <span>${escapeHtml(comparison.metric)}</span>
                                <span>${escapeHtml(String(comparison.current_value))} → ${escapeHtml(String(comparison.baseline_value))}</span>
                            </div>
                        `
                    )
                    .join("")}
                ${signals.length
                    ? signals
                          .map(
                              (signal) => `
                                  <div class="baseline-signal-row">
                                      <span class="signal-pill signal-pill-${escapeHtml(signal.severity)}">${escapeHtml(signal.signal_type)}</span>
                                      <span>${escapeHtml(signal.description)}</span>
                                  </div>
                              `
                          )
                          .join("")
                    : `<div class="empty-state">No baseline deviations detected.</div>`}
            </div>
        </div>
        <div class="baseline-card baseline-card-summary">
            <p class="text-xs uppercase tracking-[0.22em] text-slate-400">Host norms</p>
            <p class="mt-3 text-sm leading-6 text-slate-300">${escapeHtml(baseline.common_process_names.slice(0, 5).join(", ") || "No stable process pattern")}</p>
            <p class="mt-4 text-sm leading-6 text-slate-300">Healthy services: ${escapeHtml(baseline.healthy_service_names.slice(0, 5).join(", ") || "No stable healthy services")}</p>
        </div>
    `;
}

function renderIssueAnomalySection(issue) {
    const anomalyReason = issue.anomaly_reason || (issue.anomaly_context?.anomaly_reasons || []).join("; ");
    const deviationScore = issue.deviation_score != null ? issue.deviation_score : issue.anomaly_context?.deviation_score;
    const baselineSummary = issue.baseline_summary || issue.anomaly_context?.baseline_comparisons?.map((c) => c.metric).join(", ");

    if (!anomalyReason && !deviationScore) {
        return "";
    }

    return `
        <div class="issue-anomaly-card">
            ${anomalyReason ? `<p class="issue-anomaly-reason">${escapeHtml(anomalyReason)}</p>` : ""}
            <div class="mt-3 flex flex-wrap gap-2 text-xs">
                ${deviationScore ? `<span class="status-badge status-warning">Deviation: ${escapeHtml(String(deviationScore))}</span>` : ""}
                ${baselineSummary ? `<span class="status-badge status-success">Baseline: ${escapeHtml(baselineSummary)}</span>` : ""}
            </div>
        </div>
    `;
}

function renderPorts(ports) {
    if (!ports.length) {
        els["ports-panel"].innerHTML = emptyState("No open listening ports were reported for this view.");
        return;
    }

    els["ports-panel"].innerHTML = `
        <div class="port-cloud">
            ${ports.map((port) => `<span class="port-pill">${escapeHtml(String(port))}</span>`).join("")}
        </div>
    `;
}

function renderLogs(logs) {
    if (!logs.length) {
        els["logs-panel"].innerHTML = emptyState("No recent logs are available.");
        return;
    }

    els["logs-panel"].innerHTML = logs
        .slice(0, 12)
        .map(
            (line, index) => `
                <div class="log-line">
                    <span class="log-index">${String(index + 1).padStart(2, "0")}</span>
                    <span>${escapeHtml(line)}</span>
                </div>
            `
        )
        .join("");
}

function renderPlan(candidateActions, allowedActions, approvalRequiredActions, blockedActions) {
    els["plan-meta"].textContent = `${capitalize(state.data.view)} view`;
    els["candidate-count"].textContent = `${candidateActions.length}`;
    els["allowed-count"].textContent = `${allowedActions.length}`;
    els["approval-required-count"].textContent = `${approvalRequiredActions.length}`;
    els["blocked-count"].textContent = `${blockedActions.length}`;

    els["candidate-actions-panel"].innerHTML = renderActionList(
        candidateActions,
        "No plan has been generated yet. Load the plan or execute view to inspect policy decisions."
    );
    els["allowed-actions-panel"].innerHTML = renderActionList(
        allowedActions,
        "No actions are currently approved by policy."
    );
    els["approval-required-actions-panel"].innerHTML = renderActionList(
        approvalRequiredActions,
        "No approval-required actions are present."
    );
    els["blocked-actions-panel"].innerHTML = renderActionList(
        blockedActions,
        "No blocked actions for the current dataset."
    );
}

function renderStrategySelectionBoard(strategySelections) {
    const selections = strategySelections || [];
    const selectedCount = selections.length;
    const altCount = selections.reduce((count, selection) => {
        const ranked = selection.ranked_candidates || [];
        return count + Math.max(0, ranked.length - 1);
    }, 0);

    els["strategy-selected-count"].textContent = `${selectedCount}`;
    els["strategy-alt-count"].textContent = `${altCount}`;
    els["strategy-selection-meta"].textContent = selectedCount
        ? `${selectedCount} issue strategy decisions with ranked alternatives`
        : "No strategy competition data for current view";

    if (!selectedCount) {
        els["strategy-selected-panel"].innerHTML = emptyState("Load plan or execute view to inspect strategy competition.");
        els["strategy-alt-panel"].innerHTML = emptyState("No lower-ranked alternatives available.");
        return;
    }

    els["strategy-selected-panel"].innerHTML = selections
        .map((selection) => {
            const winner = selection.ranked_candidates?.find(
                (candidate) => candidate.strategy?.strategy_id === selection.selected_strategy_id
            ) || selection.ranked_candidates?.[0];
            const score = winner?.score?.total_score ?? "--";
            const topTradeoffs = (winner?.tradeoffs || []).slice(0, 4)
                .map((tradeoff) => `
                    <span class="status-badge status-neutral">
                        ${escapeHtml(tradeoff.dimension)} ${tradeoff.impact === "cost" ? "cost" : "gain"}: ${escapeHtml(Number(tradeoff.value || 0).toFixed(1))}
                    </span>
                `)
                .join("");
            return `
                <article class="strategy-selection-card">
                    <div class="flex flex-wrap items-start justify-between gap-3">
                        <div>
                            <p class="text-xs uppercase tracking-[0.2em] text-slate-400">${escapeHtml(selection.evaluation_context?.issue_type || "issue")}</p>
                            <h4 class="mt-2 text-lg font-semibold text-white">${escapeHtml(selection.selected_strategy?.name || selection.selected_strategy_id)}</h4>
                        </div>
                        <span class="status-badge status-success">Score ${escapeHtml(String(score))}</span>
                    </div>
                    <p class="mt-3 text-sm leading-6 text-slate-300">${escapeHtml(selection.winning_reason || "No winning reason provided.")}</p>
                    <div class="mt-3 flex flex-wrap gap-2 text-xs">
                        <span class="status-badge status-neutral">Issue: ${escapeHtml(selection.issue_id || "n/a")}</span>
                        <span class="status-badge status-neutral">Mode: ${escapeHtml(selection.evaluation_context?.mode || state.mode)}</span>
                        <span class="status-badge status-neutral">Severity: ${escapeHtml(selection.evaluation_context?.severity || "unknown")}</span>
                        <span class="status-badge status-neutral">Confidence: ${escapeHtml(formatConfidence(selection.evaluation_context?.confidence || 0))}</span>
                    </div>
                    <div class="mt-3 flex flex-wrap gap-2 text-xs">
                        ${topTradeoffs || `<span class="status-badge status-neutral">No tradeoff data available.</span>`}
                    </div>
                </article>
            `;
        })
        .join("");

    const alternatives = selections.flatMap((selection) => {
        const ranked = selection.ranked_candidates || [];
        return ranked
            .filter((candidate) => candidate.strategy?.strategy_id !== selection.selected_strategy_id)
            .map((candidate) => ({
                issue_type: selection.evaluation_context?.issue_type || "issue",
                issue_id: selection.issue_id,
                rejected_reason: selection.rejected_reasons?.[candidate.strategy?.strategy_id] || candidate.decision_reason,
                ...candidate,
            }));
    });

    if (!alternatives.length) {
        els["strategy-alt-panel"].innerHTML = emptyState("No lower-ranked alternatives were produced.");
        return;
    }

    els["strategy-alt-panel"].innerHTML = alternatives
        .map((candidate) => `
            <article class="strategy-alt-card">
                <div class="flex flex-wrap items-start justify-between gap-3">
                    <div>
                        <p class="text-xs uppercase tracking-[0.2em] text-slate-400">${escapeHtml(candidate.issue_type)}</p>
                        <h4 class="mt-2 text-lg font-semibold text-white">${escapeHtml(candidate.strategy?.name || candidate.strategy?.strategy_id || "alternative")}</h4>
                    </div>
                    <span class="status-badge status-neutral">Rank ${escapeHtml(String(candidate.rank))} · Score ${escapeHtml(String(candidate.score?.total_score ?? "--"))}</span>
                </div>
                <p class="mt-3 text-sm leading-6 text-slate-300">${escapeHtml(candidate.rejected_reason || "No rejection reason provided.")}</p>
                <div class="mt-3 flex flex-wrap gap-2 text-xs">
                    <span class="status-badge status-neutral">Approval cost: ${escapeHtml(String(candidate.score?.approval_cost ?? "--"))}</span>
                    <span class="status-badge status-neutral">Disruption cost: ${escapeHtml(String(candidate.score?.disruption_cost ?? "--"))}</span>
                    <span class="status-badge status-neutral">Observability: ${escapeHtml(String(candidate.score?.observability_gain ?? "--"))}</span>
                </div>
            </article>
        `)
        .join("");
}

function renderExecution(executedActions, verificationResults) {
    els["execute-meta"].textContent = state.mode === "live" ? "Live observation, simulated actions only" : "Simulation only";
    els["executed-count"].textContent = `${executedActions.length}`;
    els["verification-count"].textContent = `${verificationResults.length}`;

    if (!executedActions.length) {
        els["executed-actions-panel"].innerHTML = emptyState("No execution results yet. Load the execute view to simulate allowed actions.");
    } else {
        els["executed-actions-panel"].innerHTML = executedActions
            .map(
                (result) => `
                    <article class="execution-card">
                        <div class="flex items-center justify-between gap-3">
                            <div>
                                <p class="text-xs uppercase tracking-[0.2em] text-slate-400">${escapeHtml(result.issue_id || "simulation")}</p>
                                <h4 class="mt-2 text-lg font-semibold text-white">${escapeHtml(result.action_type)}</h4>
                            </div>
                            <span class="status-badge ${result.success ? "status-success" : "status-unhealthy"}">${result.success ? "success" : "failed"}</span>
                        </div>
                        <p class="mt-4 text-sm leading-6 text-slate-300">${escapeHtml(result.message)}</p>
                        <div class="mt-4 flex flex-wrap gap-2 text-xs">
                            <span class="status-badge status-neutral">Target: ${escapeHtml(result.target || "unscoped")}</span>
                            <span class="status-badge status-neutral">Executed: ${escapeHtml(String(result.executed))}</span>
                        </div>
                    </article>
                `
            )
            .join("");
    }

    if (!verificationResults.length) {
        els["verification-panel"].innerHTML = emptyState("Verification results will appear after simulated execution.");
    } else {
        els["verification-panel"].innerHTML = verificationResults
            .map(
                (verification) => `
                    <article class="verification-card">
                        <div class="flex items-center justify-between gap-3">
                            <div>
                                <p class="text-xs uppercase tracking-[0.2em] text-slate-400">${escapeHtml(verification.issue_id || "verification")}</p>
                                <h4 class="mt-2 text-lg font-semibold text-white">${escapeHtml(verification.action_type)}</h4>
                            </div>
                            <span class="status-badge ${verification.verified ? "status-verified" : "status-unhealthy"}">${verification.verified ? "verified" : "not verified"}</span>
                        </div>
                        <p class="mt-4 text-sm leading-6 text-slate-300">${escapeHtml(verification.reason)}</p>
                    </article>
                `
            )
            .join("");
    }
}

function renderStrategies(strategies, incidentStates) {
    els["strategy-count"].textContent = `${strategies.length}`;
    els["incident-state-count"].textContent = `${incidentStates.length}`;

    if (!strategies.length) {
        els["strategy-panel"].innerHTML = emptyState("No remediation strategy selected for the current view.");
    } else {
        els["strategy-panel"].innerHTML = strategies
            .map((strategy) => {
                const steps = (strategy.playbook?.steps || [])
                    .map((step) => {
                        const statusClass = `step-status-${(step.status || "pending").replace(/_/g, "-")}`;
                        return `
                            <li class="strategy-step ${statusClass}">
                                <div class="flex items-center justify-between gap-3">
                                    <span class="font-semibold text-white">${escapeHtml(step.name || step.step_id)}</span>
                                    <span class="status-badge status-neutral">${escapeHtml(step.status || "pending")}</span>
                                </div>
                                <p class="mt-2 text-sm leading-6 text-slate-300">${escapeHtml(step.description || "")}</p>
                                <div class="mt-2 flex flex-wrap gap-2 text-xs">
                                    ${step.action_type ? `<span class="status-badge status-neutral">Action: ${escapeHtml(step.action_type)}</span>` : ""}
                                    ${step.execution_mode ? `<span class="status-badge status-neutral">Mode: ${escapeHtml(step.execution_mode)}</span>` : ""}
                                    ${step.risk_tier ? `<span class="status-badge status-neutral">Risk: ${escapeHtml(step.risk_tier)}</span>` : ""}
                                    ${step.approval_required ? `<span class="status-badge status-warning">Approval Required</span>` : ""}
                                </div>
                                ${step.policy_reason ? `<p class="mt-2 text-xs text-slate-400">${escapeHtml(step.policy_reason)}</p>` : ""}
                            </li>
                        `;
                    })
                    .join("");
                return `
                    <article class="strategy-card">
                        <div class="flex flex-wrap items-start justify-between gap-3">
                            <div>
                                <p class="text-xs uppercase tracking-[0.2em] text-slate-400">${escapeHtml(strategy.issue_type)}</p>
                                <h4 class="mt-2 text-lg font-semibold text-white">${escapeHtml(strategy.playbook?.name || "Playbook")}</h4>
                            </div>
                            <span class="status-badge status-neutral">Priority: ${escapeHtml(String(strategy.priority_score ?? "--"))}</span>
                        </div>
                        <p class="mt-3 text-sm leading-6 text-slate-300">${escapeHtml(strategy.selection_reason || "Strategy selected deterministically.")}</p>
                        <ol class="mt-4 space-y-3">${steps}</ol>
                    </article>
                `;
            })
            .join("");
    }

    if (!incidentStates.length) {
        els["incident-state-panel"].innerHTML = emptyState("No incident state-machine data available.");
        return;
    }

    els["incident-state-panel"].innerHTML = incidentStates
        .map((incidentState) => {
            const transitions = (incidentState.transitions || [])
                .map(
                    (transition) => `
                        <li class="transition-item">
                            <div class="transition-head">
                                <span>${escapeHtml(transition.from_state)} → ${escapeHtml(transition.to_state)}</span>
                                <span class="text-slate-500">${escapeHtml(transition.step_id)}</span>
                            </div>
                            <p class="text-sm text-slate-300">${escapeHtml(transition.reason)}</p>
                        </li>
                    `
                )
                .join("");

            return `
                <article class="incident-state-card">
                    <div class="flex flex-wrap items-center justify-between gap-3">
                        <h4 class="text-lg font-semibold text-white">${escapeHtml(incidentState.issue_type)} · ${escapeHtml(incidentState.incident_key)}</h4>
                        <span class="status-badge ${getIncidentStateClass(incidentState.current_state)}">${escapeHtml(incidentState.current_state)}</span>
                    </div>
                    <p class="mt-3 text-sm leading-6 text-slate-300">${escapeHtml(incidentState.transition_reason || "No transition reason provided.")}</p>
                    <div class="mt-3 flex flex-wrap gap-2 text-xs">
                        <span class="status-badge status-neutral">Previous: ${escapeHtml(incidentState.previous_state || "none")}</span>
                        <span class="status-badge status-neutral">Next: ${escapeHtml((incidentState.allowed_transitions || []).join(", ") || "none")}</span>
                    </div>
                    <ol class="mt-4 space-y-2 transition-list">${transitions || `<li class="empty-state">No transitions recorded.</li>`}</ol>
                </article>
            `;
        })
        .join("");
}

function renderPlaybookExecutions(playbookExecutions) {
    els["playbook-execution-count"].textContent = `${playbookExecutions.length}`;
    if (!playbookExecutions.length) {
        els["playbook-execution-panel"].innerHTML = emptyState("No playbook execution timeline available. Load execute view to simulate.");
        return;
    }

    els["playbook-execution-panel"].innerHTML = playbookExecutions
        .map((execution) => {
            const checkpoints = (execution.verification_checkpoints || [])
                .map((checkpoint) => {
                    const verifiedClass =
                        checkpoint.verified === true
                            ? "status-verified"
                            : checkpoint.verified === false
                                ? "status-unhealthy"
                                : "status-neutral";
                    const verifiedLabel =
                        checkpoint.verified === true
                            ? "verified"
                            : checkpoint.verified === false
                                ? "failed"
                                : "pending";
                    return `
                        <li class="checkpoint-item">
                            <div class="flex flex-wrap items-center justify-between gap-2">
                                <span class="font-semibold text-white">${escapeHtml(checkpoint.step_id)}</span>
                                <span class="status-badge ${verifiedClass}">${escapeHtml(verifiedLabel)}</span>
                            </div>
                            <p class="mt-2 text-sm text-slate-300">${escapeHtml(checkpoint.reason || checkpoint.success_condition)}</p>
                        </li>
                    `;
                })
                .join("");

            const transitions = (execution.transitions || [])
                .map(
                    (transition) => `
                        <li class="transition-item">
                            <div class="transition-head">
                                <span>${escapeHtml(transition.from_state)} → ${escapeHtml(transition.to_state)}</span>
                                <span class="text-slate-500">${escapeHtml(transition.step_id)}</span>
                            </div>
                            <p class="text-sm text-slate-300">${escapeHtml(transition.reason)}</p>
                        </li>
                    `
                )
                .join("");

            return `
                <article class="playbook-execution-card">
                    <div class="flex flex-wrap items-center justify-between gap-3">
                        <h4 class="text-lg font-semibold text-white">${escapeHtml(execution.playbook_id)}</h4>
                        <span class="status-badge ${getIncidentStateClass(execution.current_state)}">${escapeHtml(execution.current_state)}</span>
                    </div>
                    <p class="mt-3 text-sm leading-6 text-slate-300">${escapeHtml(execution.transition_reason || "No transition reason available.")}</p>
                    <div class="mt-3 flex flex-wrap gap-2 text-xs">
                        <span class="status-badge status-neutral">Current step: ${escapeHtml(execution.current_step_id || "none")}</span>
                        <span class="status-badge status-neutral">Completed: ${escapeHtml(String((execution.completed_step_ids || []).length))}</span>
                        <span class="status-badge status-neutral">Failed: ${escapeHtml(String((execution.failed_step_ids || []).length))}</span>
                        <span class="status-badge status-neutral">Blocked: ${escapeHtml(String((execution.blocked_step_ids || []).length))}</span>
                    </div>
                    <div class="mt-4 grid gap-4 lg:grid-cols-2">
                        <div>
                            <p class="section-kicker">Verification Checkpoints</p>
                            <ul class="mt-3 space-y-2">${checkpoints || `<li class="empty-state">No checkpoints recorded.</li>`}</ul>
                        </div>
                        <div>
                            <p class="section-kicker">Transition Timeline</p>
                            <ol class="mt-3 space-y-2 transition-list">${transitions || `<li class="empty-state">No transitions recorded.</li>`}</ol>
                        </div>
                    </div>
                </article>
            `;
        })
        .join("");
}

function renderActionList(actions, emptyMessage) {
    if (!actions.length) {
        return emptyState(emptyMessage);
    }

    return actions
        .map((action) => {
            const allowed = action.allowed === true;
            const policyClass = allowed ? "policy-allowed" : "policy-denied";
            const policyLabel = allowed ? "allowed" : "blocked";
            const approvalBadge = action.approval_required ? "status-warning" : "status-success";
            const executionBadge = action.execution_mode ? `status-${action.execution_mode.replace(/_/g, "-")}` : "status-neutral";
            return `
                <article class="action-card">
                    <div class="flex flex-wrap items-start justify-between gap-3">
                        <div>
                            <p class="text-xs uppercase tracking-[0.2em] text-slate-400">${escapeHtml(action.issue_id || "policy")}</p>
                            <h4 class="mt-2 text-lg font-semibold text-white">${escapeHtml(action.action_type)}</h4>
                        </div>
                        <span class="policy-badge ${policyClass}">${policyLabel}</span>
                    </div>
                    <p class="mt-4 text-sm leading-6 text-slate-300">${escapeHtml(action.description || "No description provided.")}</p>
                    <details class="mt-4 rounded-xl border border-white/10 bg-slate-950/30 px-4 py-3 text-sm text-slate-300">
                        <summary class="font-medium text-white">Action trace details</summary>
                        <div class="mt-3 space-y-2">
                            ${action.planning_reason ? `<div><strong>Planning:</strong> ${escapeHtml(action.planning_reason)}</div>` : ""}
                            ${action.policy_reason ? `<div><strong>Policy:</strong> ${escapeHtml(action.policy_reason)}</div>` : ""}
                            ${action.dispatch_reason ? `<div><strong>Dispatch:</strong> ${escapeHtml(action.dispatch_reason)}</div>` : ""}
                        </div>
                    </details>
                    <div class="mt-4 flex flex-wrap gap-2 text-xs">
                        <span class="status-badge status-neutral">Risk: ${escapeHtml(action.risk_tier || "unknown")}</span>
                        <span class="status-badge ${approvalBadge}">Approval: ${escapeHtml(String(action.approval_required || false))}</span>
                        <span class="status-badge ${executionBadge}">Mode: ${escapeHtml(action.execution_mode || "unknown")}</span>
                        <span class="status-badge status-neutral">Confidence: ${escapeHtml(formatConfidence(action.action_confidence ?? 0))}</span>
                        <span class="status-badge status-neutral">Target: ${escapeHtml(action.target || "unscoped")}</span>
                    </div>
                </article>
            `;
        })
        .join("");
}

function computeRisk(snapshot) {
    const score = snapshot.risk_score ?? 0;

    if (score >= 70) {
        return { score, label: "Critical", statusClass: "status-critical" };
    }
    if (score >= 35) {
        return { score, label: "Elevated", statusClass: "status-elevated" };
    }
    return { score, label: "Stable", statusClass: "status-stable" };
}

function getIncidentStateClass(state) {
    const normalized = String(state || "").toLowerCase();
    if (normalized === "closed" || normalized === "verified" || normalized === "approved") return "status-success";
    if (normalized === "approval_pending" || normalized === "planned" || normalized === "analyzed") return "status-warning";
    if (normalized === "blocked" || normalized === "failed") return "status-unhealthy";
    return "status-neutral";
}

function setBanner(message, type) {
    els["feedback-banner"].classList.remove("hidden", "feedback-error", "feedback-info");
    els["feedback-banner"].classList.add(type === "error" ? "feedback-error" : "feedback-info");
    els["feedback-banner"].textContent = message;
}

function emptyState(message) {
    return `<div class="empty-state">${escapeHtml(message)}</div>`;
}

function formatPercent(value) {
    if (typeof value !== "number" || Number.isNaN(value)) {
        return "--";
    }
    return `${value.toFixed(1)}%`;
}

function formatNumber(value) {
    if (typeof value !== "number" || Number.isNaN(value)) {
        return "--";
    }
    return new Intl.NumberFormat("en-US", { maximumFractionDigits: value < 100 ? 1 : 0 }).format(value);
}

function formatConfidence(value) {
    if (typeof value !== "number" || Number.isNaN(value)) {
        return "--";
    }
    return `${Math.round(value * 100)}%`;
}

function formatTime(date) {
    if (!(date instanceof Date)) {
        return "--";
    }
    return new Intl.DateTimeFormat([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
    }).format(date);
}

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function capitalize(value) {
    return String(value).charAt(0).toUpperCase() + String(value).slice(1);
}
