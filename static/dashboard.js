const state = {
    platform: "linux",
    mode: "mock",
    lastAction: "snapshot",
    loading: false,
    data: null,
    lastRefresh: null,
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
        "execute-meta",
        "executed-count",
        "verification-count",
        "executed-actions-panel",
        "verification-panel",
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

function normalizeData(action, payload) {
    if (action === "snapshot") {
        return {
            snapshot: payload,
            candidate_actions: [],
            allowed_actions: [],
            dispatch: { executed_actions: [] },
            verification_results: [],
            view: action,
        };
    }

    return {
        ...payload,
        dispatch: payload.dispatch || { executed_actions: [] },
        verification_results: payload.verification_results || [],
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
    const executedActions = state.data.dispatch.executed_actions || [];
    const verificationResults = state.data.verification_results || [];
    const risk = computeRisk(snapshot);

    renderHero(snapshot, risk, issues, candidateActions, allowedActions);
    renderSummary(snapshot, issues, candidateActions, allowedActions);
    renderIssues(issues);
    renderProcesses(snapshot.processes || []);
    renderServices(snapshot.services || []);
    renderPorts(snapshot.open_ports || []);
    renderLogs(snapshot.recent_logs || []);
    renderPlan(candidateActions, allowedActions, approvalRequiredActions, blockedActions);
    renderExecution(executedActions, verificationResults);
}

function renderLoadingState(action) {
    const loadingBlock = `<div class="empty-state">Streaming ${escapeHtml(action)} view...</div>`;
    [
        "issues-panel",
        "processes-panel",
        "services-panel",
        "ports-panel",
        "logs-panel",
        "candidate-actions-panel",
        "allowed-actions-panel",
        "approval-required-actions-panel",
        "blocked-actions-panel",
        "executed-actions-panel",
        "verification-panel",
    ].forEach((id) => {
        els[id].innerHTML = loadingBlock;
    });
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
        "ports-panel",
        "logs-panel",
        "candidate-actions-panel",
        "allowed-actions-panel",
        "approval-required-actions-panel",
        "blocked-actions-panel",
        "executed-actions-panel",
        "verification-panel",
    ].forEach((id) => {
        els[id].innerHTML = errorBlock;
    });
    els["status-pill"].textContent = "Attention";
    els["status-pill"].className = "status-pill status-critical";
    els["status-copy"].textContent = message;
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
                <article class="issue-card issue-card-${escapeHtml(severity)}">
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
                </article>
            `;
        })
        .join("");
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
