// =============================================================================
// V.E.G.A.S. TERMINAL — Polling & Headless Mode
// Progress polling (ADR-OBS-002 multi-run), trace polling, headless observation.
// =============================================================================


// =============================================================================
// TRACE POLLING (deprecated — renderTraces is a no-op)
// =============================================================================

function startTracePolling(runId) {
    if (tracePollInterval) clearInterval(tracePollInterval);

    tracePollInterval = setInterval(async () => {
        try {
            const res = await fetch(`${API_BASE}/traces/${runId}`);
            if (res.ok) {
                const data = await res.json();
                renderTraces(data.runs);
            }
        } catch (e) {
            console.error("Trace poll error", e);
        }
    }, 2000);
}

function stopTracePolling() {
    if (tracePollInterval) clearInterval(tracePollInterval);
}

function renderTraces(runs) {
    // DEPRECATED: executionTraceEl no longer exists
    return;
}


// =============================================================================
// INTRA-NODE PROGRESS POLLING (ADR-OBS-002: multi-run tree support)
// =============================================================================

// Track which child run_ids we're actively polling (for delegate tree drilling)
let _activeChildPolls = new Set();

function startProgressPolling(runId, depth = 0) {
    if (progressIntervals.has(runId)) return; // Already polling this run

    const intervalId = setInterval(async () => {
        try {
            const resp = await fetch(`${API_BASE}/progress/${runId}`);
            if (!resp.ok) return;
            const data = await resp.json();
            for (const entry of (data.entries || [])) {
                renderProgressEntry(entry, depth);
            }
        } catch (e) {
            // Silently ignore poll failures (run may have ended)
        }
    }, 2500);

    progressIntervals.set(runId, intervalId);
}

function stopProgressPolling(runId) {
    if (runId) {
        // Stop polling a specific run (e.g. child completed)
        const intervalId = progressIntervals.get(runId);
        if (intervalId) {
            clearInterval(intervalId);
            progressIntervals.delete(runId);
        }
        _activeChildPolls.delete(runId);
    } else {
        // Stop all polling (workflow ended)
        for (const [rid, intervalId] of progressIntervals) {
            clearInterval(intervalId);
        }
        progressIntervals.clear();
        _activeChildPolls.clear();
    }
}

function renderProgressEntry(entry, depth = 0) {
    const specialist = (entry.specialist || 'project_director').replace(/_specialist$/, '').replace(/_/g, ' ').toUpperCase();
    const tool = entry.tool || 'unknown';

    // Depth badge for child run entries
    const depthPrefix = depth > 0 ? `[child-${depth}] ` : '';

    // ADR-OBS-002: delegate_child_started — start polling the child's progress
    if (tool === 'delegate_child_started' && entry.child_run_id) {
        const childId = entry.child_run_id;
        if (!_activeChildPolls.has(childId)) {
            _activeChildPolls.add(childId);
            startProgressPolling(childId, depth + 1);
            addThoughtStreamEntry(specialist,
                `${depthPrefix}Delegating → child ${childId.substring(0, 8)}`,
                'lifecycle');
        }
        return;
    }

    // #250: Delegate start (pre-dispatch, legacy entry without child_run_id)
    if (tool === 'delegate' && !entry.fork_metadata) {
        addThoughtStreamEntry(specialist, `${depthPrefix}${entry.args_summary || 'Delegating to child run...'}`, 'lifecycle');
        return;
    }

    // Fork entries get special rendering (delegate completion with fork_metadata)
    if (entry.fork_metadata) {
        const fm = entry.fork_metadata;
        const route = (fm.child_routing_history || []).join(' \u2192 ');
        // Stop polling the completed child
        if (fm.child_run_id) {
            stopProgressPolling(fm.child_run_id);
        }
        addThoughtStreamEntry(specialist, `${depthPrefix}${entry.args_summary || tool}`, 'fork', {
            childRunId: fm.child_run_id,
            childRoute: route,
            hadError: fm.had_error,
        });
        return;
    }

    // _start entries render as lifecycle
    if (tool === '_start') {
        // For child runs, args_summary contains the conditioning frame preamble.
        // Show a clean label instead of internal prompt text.
        const label = depth > 0
            ? 'Child specialist starting...'
            : (entry.args_summary || 'Starting react loop...');
        addThoughtStreamEntry(specialist, `${depthPrefix}${label}`, 'lifecycle');
        return;
    }

    // Regular tool calls
    if (entry.success) {
        addThoughtStreamEntry(specialist, `${depthPrefix}${tool}()`, 'mcp', {
            service: 'react_step',
            method: tool,
            params: entry.args_summary,
        });
    } else {
        addThoughtStreamEntry(specialist, `${depthPrefix}${tool}() \u2014 ${(entry.observation_preview || 'failed').substring(0, 100)}`, 'error');
    }
}


// =============================================================================
// HEADLESS MODE — observe externally-initiated runs (#267)
// =============================================================================

headlessModeCheckbox.addEventListener('change', () => {
    // ADR-UI-003 Step 4: Hide command bar in headless mode, reclaim space for observability
    const commandPanel = document.querySelector('.command-panel');
    if (commandPanel) {
        commandPanel.style.display = headlessModeCheckbox.checked ? 'none' : '';
    }

    if (headlessModeCheckbox.checked) {
        startHeadlessPolling();
        headlessStatusEl.textContent = 'SCANNING';
        headlessStatusEl.style.color = 'var(--secondary-color)';
        logStatus('► HEADLESS MODE: Scanning for external runs...');
    } else {
        stopHeadlessMode();
        headlessStatusEl.textContent = 'OFF';
        headlessStatusEl.style.color = '';
        headlessStatusEl.style.opacity = '0.6';
        logStatus('► HEADLESS MODE: Disabled');
    }
});

function startHeadlessPolling() {
    if (headlessPollInterval) clearInterval(headlessPollInterval);

    headlessPollInterval = setInterval(async () => {
        if (currentRunId || headlessEventSource) return;

        try {
            const res = await fetch(`${API_BASE}/runs/active`);
            if (!res.ok) return;
            const data = await res.json();
            const runs = data.runs || [];

            if (runs.length > 0) {
                const run = runs[0];
                attachToHeadlessRun(run.run_id, run.model);
            }
        } catch (e) {
            // Silently ignore poll failures
        }
    }, 1500);
}

function attachToHeadlessRun(runId, model) {
    if (headlessEventSource) return;

    logStatus(`► HEADLESS: Attaching to run ${runId.substring(0, 8)}... (${model || 'unknown'})`);
    headlessStatusEl.textContent = 'ATTACHED';
    headlessStatusEl.style.color = 'var(--primary-color)';
    headlessStatusEl.style.opacity = '1';

    routingLogEl.innerHTML = '';
    thoughtStreamEl.innerHTML = '<div class="placeholder">OBSERVING EXTERNAL RUN...</div>';
    systemStatusEl.innerHTML = `► HEADLESS: Observing run ${runId.substring(0, 8)}...`;

    thoughtStreamEntries = [];
    currentArtifacts = {};
    stateSnapshots = [];
    snapshotPageIndex = -1;

    startProgressPolling(runId);

    headlessEventSource = new EventSource(`${API_BASE}/runs/${runId}/events`);

    headlessEventSource.onmessage = (msg) => {
        try {
            const event = JSON.parse(msg.data);
            handleStreamEvent(event);
        } catch (e) {
            console.error('Headless SSE parse error:', e);
        }
    };

    headlessEventSource.onerror = () => {
        detachHeadlessRun();
    };
}

function detachHeadlessRun() {
    if (headlessEventSource) {
        headlessEventSource.close();
        headlessEventSource = null;
    }
    stopProgressPolling();
    currentRunId = null;

    if (headlessModeCheckbox.checked) {
        headlessStatusEl.textContent = 'SCANNING';
        headlessStatusEl.style.color = 'var(--secondary-color)';
        logStatus('► HEADLESS: Run complete. Scanning for next run...');
    }
}

function stopHeadlessMode() {
    if (headlessPollInterval) {
        clearInterval(headlessPollInterval);
        headlessPollInterval = null;
    }
    if (headlessEventSource) {
        headlessEventSource.close();
        headlessEventSource = null;
    }
}


// =============================================================================
// INITIALIZATION — deferred calls that depend on restored state
// =============================================================================

// If run history was restored from session storage, render the last page
if (runHistory.length > 0) {
    updatePagingControls();
}
