// =============================================================================
// V.E.G.A.S. TERMINAL — Inspector & Paging
// Snapshot inspector, mission report paging, context selection.
// =============================================================================

// =============================================================================
// STATE TAB: SNAPSHOT PAGING & RENDERING
// =============================================================================

function updateSnapshotPagingControls() {
    snapshotPrevBtn.disabled = snapshotPageIndex <= 0;
    snapshotNextBtn.disabled = snapshotPageIndex >= stateSnapshots.length - 1;

    if (snapshotPageIndex >= 0 && stateSnapshots[snapshotPageIndex]) {
        const snap = stateSnapshots[snapshotPageIndex];
        const name = snap.specialist
            ? snap.specialist.replace(/_specialist$/, '').replace(/_/g, ' ').toUpperCase()
            : 'UNKNOWN';
        snapshotLabelEl.textContent = `STEP ${snapshotPageIndex + 1} / ${stateSnapshots.length} : ${name}`;
        if (snap.timestamp) {
            const ts = new Date(snap.timestamp);
            snapshotTimestampEl.textContent = ts.toLocaleTimeString();
        }
    } else {
        snapshotLabelEl.textContent = stateSnapshots.length > 0
            ? `${stateSnapshots.length} SNAPSHOTS`
            : 'NO SNAPSHOTS';
        snapshotTimestampEl.textContent = '';
    }
}

// Snapshot paging event listeners
snapshotPrevBtn.addEventListener('click', () => {
    if (snapshotPageIndex > 0) {
        snapshotPageIndex--;
        renderSnapshot(snapshotPageIndex);
    }
});
snapshotNextBtn.addEventListener('click', () => {
    if (snapshotPageIndex < stateSnapshots.length - 1) {
        snapshotPageIndex++;
        renderSnapshot(snapshotPageIndex);
    }
});

function renderSnapshot(index) {
    if (index < 0 || index >= stateSnapshots.length) return;
    const snap = stateSnapshots[index];
    updateSnapshotPagingControls();

    const specialistName = snap.specialist
        ? snap.specialist.replace(/_specialist$/, '').replace(/_/g, ' ').toUpperCase()
        : 'UNKNOWN';
    const prompts = snap.prompts || {};
    const reactTrace = prompts.react_trace;
    const hasReactTrace = reactTrace && Array.isArray(reactTrace) && reactTrace.length > 0;

    let html = '';

    // --- Header: specialist name, model, latency ---
    html += '<div class="snapshot-header">';
    html += `<span class="snapshot-specialist-name">${escapeHtml(specialistName)}</span>`;
    if (prompts.model_id) {
        html += `<span class="snapshot-model-badge">${escapeHtml(prompts.model_id)}</span>`;
    }
    if (snap.latency_ms != null) {
        html += `<span class="snapshot-latency">${snap.latency_ms}ms</span>`;
    }
    html += '</div>';

    // --- Routing breadcrumb ---
    if (snap.routing_history && snap.routing_history.length > 0) {
        const breadcrumb = snap.routing_history.map(r =>
            r.replace(/_specialist$/, '').replace(/_/g, ' ').toUpperCase()
        ).join(' \u2192 ');
        html += `<div class="snapshot-breadcrumb">${escapeHtml(breadcrumb)}</div>`;
    }

    // --- Prompt Inspector ---
    html += '<div class="prompt-inspector">';
    html += '<h4 class="inspector-section-title">PROMPT INSPECTOR</h4>';

    if (prompts.system_prompt) {
        html += '<div class="prompt-block">';
        html += '<div class="prompt-block-header" onclick="this.parentElement.classList.toggle(\'expanded\')">';
        html += '<span class="prompt-block-label">SYSTEM PROMPT</span>';
        html += `<span class="prompt-block-size">${prompts.system_prompt.length} chars</span>`;
        html += '<span class="toggle-arrow">&#x25B6;</span>';
        html += '</div>';
        html += `<pre class="prompt-block-content">${escapeHtml(prompts.system_prompt)}</pre>`;
        html += '</div>';
    }

    if (prompts.assembled_prompt) {
        html += '<div class="prompt-block expanded">';  // Default open
        html += '<div class="prompt-block-header" onclick="this.parentElement.classList.toggle(\'expanded\')">';
        html += '<span class="prompt-block-label">ASSEMBLED PROMPT</span>';
        html += `<span class="prompt-block-size">${prompts.assembled_prompt.length} chars</span>`;
        html += '<span class="toggle-arrow">&#x25B6;</span>';
        html += '</div>';
        html += `<pre class="prompt-block-content">${escapeHtml(prompts.assembled_prompt)}</pre>`;
        html += '</div>';
    }

    if (!prompts.system_prompt && !prompts.assembled_prompt && !hasReactTrace) {
        // For Facilitator: show the gathered_context it assembled
        const gatheredContext = (snap.artifacts || {}).gathered_context;
        if (gatheredContext) {
            html += '<div class="prompt-block expanded">';
            html += '<div class="prompt-block-header" onclick="this.parentElement.classList.toggle(\'expanded\')">';
            html += '<span class="prompt-block-label">GATHERED CONTEXT</span>';
            html += `<span class="prompt-block-size">${gatheredContext.length} chars</span>`;
            html += '<span class="toggle-arrow">&#x25B6;</span>';
            html += '</div>';
            html += `<pre class="prompt-block-content">${escapeHtml(gatheredContext)}</pre>`;
            html += '</div>';
        } else {
            html += '<div class="prompt-block-empty">No prompt data captured (procedural specialist)</div>';
        }
    }

    html += '</div>'; // end prompt-inspector

    // --- Tool Chain Viewer (for ReAct specialists) ---
    if (hasReactTrace) {
        html += '<div class="tool-chain-viewer">';
        html += '<h4 class="inspector-section-title">TOOL CHAIN</h4>';
        html += '<div class="tool-chain-timeline">';

        reactTrace.forEach((entry) => {
            const tc = entry.tool_call || {};
            const isSuccess = entry.success !== false;
            const statusClass = isSuccess ? 'tool-success' : 'tool-error';
            const statusIcon = isSuccess ? '\u2713' : '\u2717';

            html += `<div class="tool-chain-entry ${statusClass}">`;

            html += '<div class="tool-chain-step">';
            html += `<span class="tool-chain-iteration">iter ${entry.iteration != null ? entry.iteration : '?'}</span>`;
            html += `<span class="tool-chain-status">${statusIcon}</span>`;
            html += '</div>';

            html += '<div class="tool-chain-details">';

            html += '<div class="tool-call-header">';
            html += `<span class="tool-call-name">${escapeHtml(tc.name || 'unknown')}</span>`;
            if (tc.id) {
                html += `<span class="tool-call-id">${escapeHtml(tc.id)}</span>`;
            }
            html += '</div>';

            if (tc.args && Object.keys(tc.args).length > 0) {
                html += '<div class="tool-call-args">';
                html += `<pre>${escapeHtml(JSON.stringify(tc.args, null, 2))}</pre>`;
                html += '</div>';
            }

            if (entry.observation) {
                const obsLength = entry.observation.length;
                const isLong = obsLength > 200;
                html += `<div class="tool-observation ${isLong ? '' : 'expanded'}">`;
                html += '<div class="tool-observation-header" onclick="this.parentElement.classList.toggle(\'expanded\')">';
                html += '<span class="tool-observation-label">OBSERVATION</span>';
                html += `<span class="prompt-block-size">${obsLength} chars</span>`;
                if (isLong) html += '<span class="toggle-arrow">&#x25B6;</span>';
                html += '</div>';
                html += `<pre class="tool-observation-content">${escapeHtml(entry.observation)}</pre>`;
                html += '</div>';
            }

            if (entry.fork_metadata) {
                const fm = entry.fork_metadata;
                html += '<div class="fork-breadcrumb">';
                html += '<div class="fork-breadcrumb-header">';
                html += '<span class="fork-breadcrumb-label">CHILD INVOCATION</span>';
                if (fm.child_run_id) {
                    html += `<span class="fork-run-id">${fm.child_run_id.substring(0, 8)}</span>`;
                }
                html += '</div>';
                if (fm.child_routing_history && fm.child_routing_history.length > 0) {
                    html += '<div class="fork-routing-path">';
                    fm.child_routing_history.forEach((node, i) => {
                        if (i > 0) html += '<span class="fork-path-arrow">\u2192</span>';
                        html += `<span class="fork-path-node">${escapeHtml(node)}</span>`;
                    });
                    html += '</div>';
                }
                if (fm.had_error) html += '<span class="fork-error-flag">ERROR</span>';
                html += '</div>';
            }

            if (entry.thought) {
                html += '<div class="tool-thought">';
                html += '<span class="tool-thought-label">THOUGHT:</span> ';
                html += `<span>${escapeHtml(entry.thought)}</span>`;
                html += '</div>';
            }

            html += '</div>'; // end tool-chain-details
            html += '</div>'; // end tool-chain-entry
        });

        html += '</div>'; // end tool-chain-timeline
        html += '</div>'; // end tool-chain-viewer
    }

    // --- Scratchpad viewer ---
    const scratchpad = snap.scratchpad || {};
    const scratchpadKeys = Object.keys(scratchpad).filter(k => scratchpad[k] != null);
    if (scratchpadKeys.length > 0) {
        html += '<div class="scratchpad-viewer">';
        html += '<h4 class="inspector-section-title">SCRATCHPAD</h4>';
        scratchpadKeys.forEach(key => {
            const val = scratchpad[key];
            const valStr = typeof val === 'object' ? JSON.stringify(val, null, 2) : String(val);
            const isLong = valStr.length > 200;
            html += `<div class="prompt-block ${isLong ? '' : 'expanded'}">`;
            html += `<div class="prompt-block-header" onclick="this.parentElement.classList.toggle('expanded')">`;
            html += `<span class="prompt-block-label">${escapeHtml(key)}</span>`;
            html += `<span class="prompt-block-size">${valStr.length} chars</span>`;
            html += '<span class="toggle-arrow">&#x25B6;</span>';
            html += '</div>';
            html += `<pre class="prompt-block-content">${escapeHtml(valStr)}</pre>`;
            html += '</div>';
        });
        html += '</div>';
    }

    // --- Metadata footer ---
    html += '<div class="snapshot-meta">';
    html += `<span>Turn: ${snap.turn_count || 0}</span>`;
    html += `<span>Messages: ${snap.messages_count || 0}</span>`;
    html += `<span>Artifacts: ${(snap.artifact_keys || []).join(', ') || 'none'}</span>`;
    html += `<span>Complete: ${snap.task_is_complete ? 'YES' : 'NO'}</span>`;
    if (snap.im_decision) {
        html += `<span class="snapshot-im-decision">IM: ${escapeHtml(snap.im_decision)}</span>`;
    }
    html += '</div>';

    snapshotContentEl.innerHTML = html;

    // Re-apply code toolbars for any pre blocks we just created
    addToolbarsToPreBlocks();
}


// =============================================================================
// #181: MISSION REPORT PAGING & CONTEXT SELECTION
// =============================================================================

function updatePagingControls() {
    pagePrevBtn.disabled = currentPageIndex <= 0;
    pageNextBtn.disabled = currentPageIndex >= runHistory.length - 1;

    if (currentPageIndex >= 0 && runHistory[currentPageIndex]) {
        const ts = new Date(runHistory[currentPageIndex].timestamp);
        pageTimestampEl.textContent = ts.toLocaleTimeString();
        selectAllCheckbox.style.display = '';
    } else {
        pageTimestampEl.textContent = '';
        selectAllCheckbox.style.display = 'none';
    }

    syncSelectAllState();
}

function syncSelectAllState() {
    if (currentPageIndex < 0) return;
    const checks = checkedItems[currentPageIndex];
    if (!checks) {
        selectAllCheckbox.checked = false;
        return;
    }
    const values = Object.values(checks);
    selectAllCheckbox.checked = values.length > 0 && values.every(v => v);
}

function renderPage(index) {
    if (index < 0 || index >= runHistory.length) return;
    const page = runHistory[index];

    updatePagingControls();

    renderArtifactsWithCheckboxes(page.artifacts, index);
    renderFinalResponseWithCheckbox(page.finalResponse, index);
}

function renderArtifactsWithCheckboxes(artifacts, pageIndex) {
    artifactsOutputEl.innerHTML = '';

    if (!artifacts || Object.keys(artifacts).length === 0) {
        artifactsOutputEl.innerHTML = '<div class="placeholder">NO ARTIFACTS</div>';
        return;
    }

    for (const [key, value] of Object.entries(artifacts)) {
        if (key === 'archive_report.md' || key === 'conversation_id') continue;

        const row = document.createElement('div');
        row.className = 'artifact-row';

        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.className = 'context-checkbox';
        cb.checked = checkedItems[pageIndex]?.[key] || false;
        cb.addEventListener('change', () => {
            if (!checkedItems[pageIndex]) checkedItems[pageIndex] = {};
            checkedItems[pageIndex][key] = cb.checked;
            syncSelectAllState();
        });

        const contentWrapper = document.createElement('div');
        contentWrapper.className = 'artifact-row-content';

        const label = document.createElement('div');
        label.className = 'artifact-label';
        const size = JSON.stringify(value).length;
        label.innerHTML = `${key} <span class="artifact-size">(${formatBytes(size)})</span>`;

        const strVal = typeof value === 'string' ? value : '';
        if (key.endsWith('.html') || strVal.startsWith('<!DOCTYPE') || strVal.startsWith('<html')) {
            const renderBtn = document.createElement('button');
            renderBtn.className = 'toolbar-btn';
            renderBtn.textContent = 'RENDER';
            renderBtn.style.marginLeft = '8px';
            renderBtn.onclick = (e) => {
                e.stopPropagation();
                const blob = new Blob([strVal], { type: 'text/html' });
                window.open(URL.createObjectURL(blob), '_blank');
            };
            label.appendChild(renderBtn);

            const saveBtn = document.createElement('button');
            saveBtn.className = 'toolbar-btn';
            saveBtn.textContent = 'SAVE';
            saveBtn.onclick = (e) => {
                e.stopPropagation();
                const blob = new Blob([strVal], { type: 'text/html' });
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = key;
                a.click();
                URL.revokeObjectURL(a.href);
            };
            label.appendChild(saveBtn);
        }

        const content = document.createElement('div');
        content.className = 'artifact-content';
        const pre = document.createElement('pre');
        if (typeof value === 'object') {
            pre.textContent = JSON.stringify(value, null, 2);
        } else if (key.endsWith('.html') || strVal.startsWith('<!DOCTYPE') || strVal.startsWith('<html')) {
            pre.textContent = `HTML document (${formatBytes(size)}) — click RENDER to view.`;
            pre.style.opacity = '0.6';
            pre.style.fontStyle = 'italic';
        } else {
            pre.textContent = decodeHtmlEntities(String(value));
        }
        content.appendChild(pre);

        label.addEventListener('click', () => {
            content.classList.toggle('expanded');
        });

        contentWrapper.appendChild(label);
        contentWrapper.appendChild(content);
        row.appendChild(cb);
        row.appendChild(contentWrapper);
        artifactsOutputEl.appendChild(row);
    }
}

function renderFinalResponseWithCheckbox(archive, pageIndex) {
    renderMissionReport(archive);

    const header = document.createElement('div');
    header.className = 'context-select-row';

    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.className = 'context-checkbox';
    cb.checked = checkedItems[pageIndex]?.['_finalResponse'] || false;
    cb.addEventListener('change', () => {
        if (!checkedItems[pageIndex]) checkedItems[pageIndex] = {};
        checkedItems[pageIndex]['_finalResponse'] = cb.checked;
        syncSelectAllState();
    });

    header.appendChild(cb);
    header.appendChild(document.createTextNode(' Include Final Response in next run'));
    archiveOutputEl.prepend(header);
}

// Mission report paging event listeners
pagePrevBtn.addEventListener('click', () => {
    if (currentPageIndex > 0) {
        currentPageIndex--;
        renderPage(currentPageIndex);
    }
});
pageNextBtn.addEventListener('click', () => {
    if (currentPageIndex < runHistory.length - 1) {
        currentPageIndex++;
        renderPage(currentPageIndex);
    }
});
selectAllCheckbox.addEventListener('change', (e) => {
    const checked = e.target.checked;
    if (currentPageIndex < 0) return;
    if (!checkedItems[currentPageIndex]) checkedItems[currentPageIndex] = {};
    document.querySelectorAll('.artifact-row .context-checkbox, .context-select-row .context-checkbox')
        .forEach(cb => {
            cb.checked = checked;
            cb.dispatchEvent(new Event('change', { bubbles: false }));
        });
});
