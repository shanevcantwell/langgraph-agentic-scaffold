// =============================================================================
// V.E.G.A.S. TERMINAL — Observability Layer
//
// This file loads SECOND (after app.js). It defines:
//   - Thought Stream rendering (addThoughtStreamEntry)
//   - Routing Log (addRoutingEntry)
//   - Neural Grid (updateSpecialistGrid)
//   - Mermaid Graph Visualization (fetchAndRenderTopology, renderMermaidGraph)
//   - Artifact display (updateArtifactsDisplay)
//   - Snapshot Inspector (renderSnapshot, updateSnapshotPagingControls)
//   - Mission Report (renderMissionReport, renderPage, paging)
//   - SSE event handling (handleStreamEvent)
//   - Status updates (logStatus)
//   - Progress polling (startProgressPolling, stopProgressPolling)
//   - Trace polling (startTracePolling, stopTracePolling) [deprecated]
//   - Headless mode (startHeadlessPolling, attachToHeadlessRun, etc.)
//   - Code block toolbars (addToolbarsToPreBlocks)
//
// All functions reference globals defined in app.js.
// Load order: app.js → observability.js → chat.js
// =============================================================================


// =============================================================================
// STATUS
// =============================================================================

function logStatus(msg) {
    systemStatusEl.textContent = msg;
}


// =============================================================================
// THOUGHT STREAM
// =============================================================================

/**
 * Enhanced thought stream entry with semantic rendering
 * @param {string} specialist - Source specialist name
 * @param {string} message - Message content
 * @param {string} type - Entry type: info, success, error, mcp, routing, reasoning, artifact, lifecycle
 * @param {object} options - Additional options: { collapsible, service, method, params, target }
 */
function addThoughtStreamEntry(specialist, message, type = 'info', options = {}) {
    const timestamp = formatTimestamp();
    const entry = { timestamp, specialist, message, type, options };
    thoughtStreamEntries.push(entry);

    const div = document.createElement('div');

    switch (type) {
        case 'routing':
            div.className = 'thought-entry thought-routing';
            div.innerHTML = `
                <span class="thought-time">${timestamp}</span>
                <span class="thought-badge badge-route">ROUTE</span>
                <span class="thought-specialist">${specialist.toUpperCase()}</span>
                <span class="thought-route-arrow">→</span>
                <span class="thought-content">${options.target || message}</span>
            `;
            break;

        case 'mcp':
            div.className = 'thought-entry thought-mcp';
            if (options.service && options.method) {
                div.innerHTML = `
                    <span class="thought-time">${timestamp}</span>
                    <span class="thought-badge badge-mcp">MCP</span>
                    <div class="thought-mcp-call">
                        <span class="thought-mcp-service">${options.service}</span>
                        <span class="thought-mcp-method">.${options.method}()</span>
                        ${options.params ? `<span class="thought-mcp-params">${options.params}</span>` : ''}
                    </div>
                `;
            } else {
                div.innerHTML = `
                    <span class="thought-time">${timestamp}</span>
                    <span class="thought-badge badge-mcp">MCP</span>
                    <span class="thought-content">📡 ${message}</span>
                `;
            }
            break;

        case 'fork':
            div.className = 'thought-entry thought-fork' + (options.hadError ? ' fork-error' : '');
            div.innerHTML = `
                <span class="thought-time">${timestamp}</span>
                <span class="thought-badge badge-fork">FORK</span>
                <span class="thought-specialist">${specialist}</span>
                <span class="thought-content">${escapeHtml(message)}</span>
                ${options.childRoute ? `<div class="fork-route">${escapeHtml(options.childRoute)}</div>` : ''}
                ${options.childRunId ? `<span class="fork-run-id">${options.childRunId.substring(0, 8)}</span>` : ''}
            `;
            break;

        case 'reasoning':
            div.className = 'thought-entry thought-reasoning' + (options.collapsible ? ' collapsed' : '');
            if (options.collapsible) {
                div.innerHTML = `
                    <span class="thought-time">${timestamp}</span>
                    <span class="thought-badge badge-think">THINK</span>
                    <span class="thought-specialist">${specialist.toUpperCase()}</span>
                    <span class="thought-toggle" onclick="this.parentElement.classList.toggle('collapsed')"><span class="toggle-arrow">▶</span> ${message.split('\n')[0].substring(0, 50)}...</span>
                    <div class="thought-content">${message.replace(/\n/g, '<br>')}</div>
                `;
            } else {
                div.innerHTML = `
                    <span class="thought-time">${timestamp}</span>
                    <span class="thought-badge badge-think">THINK</span>
                    <span class="thought-specialist">${specialist.toUpperCase()}:</span>
                    <span class="thought-content">${message}</span>
                `;
            }
            break;

        case 'artifact':
            div.className = 'thought-entry thought-artifact';
            div.innerHTML = `
                <span class="thought-time">${timestamp}</span>
                <span class="thought-badge badge-artifact">ARTIFACT</span>
                <span class="thought-specialist">${specialist.toUpperCase()}</span>
                <span class="thought-content">📦 ${message}</span>
            `;
            break;

        case 'lifecycle':
            div.className = 'thought-entry thought-lifecycle';
            const lifecycleIcon = message.includes('start') ? '▶' : message.includes('complete') || message.includes('end') ? '■' : '●';
            div.innerHTML = `
                <span class="thought-time">${timestamp}</span>
                <span class="thought-badge badge-${message.includes('Error') ? 'error' : message.includes('complete') ? 'end' : 'start'}">${message.includes('complete') ? 'DONE' : 'SYS'}</span>
                <span class="thought-content">${lifecycleIcon} ${message}</span>
            `;
            break;

        case 'error':
            div.className = 'thought-entry thought-error';
            div.innerHTML = `
                <span class="thought-time">${timestamp}</span>
                <span class="thought-badge badge-error">ERROR</span>
                <span class="thought-specialist">${specialist.toUpperCase()}:</span>
                <span class="thought-content">❌ ${message}</span>
            `;
            break;

        case 'success':
            div.className = 'thought-entry thought-success';
            div.innerHTML = `
                <span class="thought-time">${timestamp}</span>
                <span class="thought-badge badge-end">OK</span>
                <span class="thought-specialist">${specialist.toUpperCase()}:</span>
                <span class="thought-content">✓ ${message}</span>
            `;
            break;

        default: // 'info' and others
            div.className = `thought-entry thought-${type}`;
            const typeIcon = type === 'error' ? '❌' : type === 'success' ? '✓' : '💭';
            div.innerHTML = `
                <span class="thought-time">${timestamp}</span>
                <span class="thought-specialist">${specialist.toUpperCase()}:</span>
                <span class="thought-content">${typeIcon} ${message}</span>
            `;
    }

    // Remove placeholder if exists
    if (thoughtStreamEl.querySelector('.placeholder')) {
        thoughtStreamEl.innerHTML = '';
    }

    thoughtStreamEl.appendChild(div);
    thoughtStreamEl.scrollTop = thoughtStreamEl.scrollHeight;

    // Limit to last 100 entries
    if (thoughtStreamEntries.length > 100) {
        thoughtStreamEntries.shift();
        if (thoughtStreamEl.firstChild) {
            thoughtStreamEl.removeChild(thoughtStreamEl.firstChild);
        }
    }
}


// =============================================================================
// ARTIFACTS DISPLAY
// =============================================================================

function updateArtifactsDisplay(artifacts) {
    if (!artifacts || Object.keys(artifacts).length === 0) return;

    currentArtifacts = { ...currentArtifacts, ...artifacts };

    // #198: Build display with textContent to prevent HTML artifact CSS bleed.
    artifactsOutputEl.innerHTML = '';
    for (const [key, value] of Object.entries(currentArtifacts)) {
        const heading = document.createElement('h3');
        heading.textContent = key;
        heading.className = 'artifact-heading';
        artifactsOutputEl.appendChild(heading);

        const pre = document.createElement('pre');
        pre.className = 'artifact-pre';
        if (typeof value === 'object') {
            pre.textContent = JSON.stringify(value, null, 2);
        } else {
            pre.textContent = decodeHtmlEntities(String(value));
        }
        artifactsOutputEl.appendChild(pre);
    }
}


// =============================================================================
// ROUTING LOG & NEURAL GRID
// =============================================================================

function addRoutingEntry(node) {
    const div = document.createElement('div');
    div.className = 'ticker-item active';
    div.textContent = `► ${node}`;
    routingLogEl.appendChild(div);
    routingLogEl.scrollTop = routingLogEl.scrollHeight;

    // Deactivate previous
    const prev = routingLogEl.lastElementChild.previousElementSibling;
    if (prev) prev.classList.remove('active');

    // Update Specialist Grid
    updateSpecialistGrid(node);
}

function updateSpecialistGrid(nodeName) {
    // Deactivate all
    document.querySelectorAll('.spec-node').forEach(el => el.classList.remove('active'));

    // Activate current if exists
    const el = document.getElementById(`node-${nodeName}`);
    if (el) {
        el.classList.add('active');
    }

    // Also highlight in Mermaid graph if visible
    highlightMermaidNode(nodeName);
}


// =============================================================================
// MERMAID GRAPH VISUALIZATION
// =============================================================================

let topologyData = null;
let graphViewActive = false;
let mermaidRenderCount = 0;

const toggleGraphViewBtn = document.getElementById('toggleGraphView');
const graphViewContainer = document.getElementById('graphViewContainer');
const gridViewContainer = document.getElementById('gridViewContainer');
const mermaidGraphEl = document.getElementById('mermaidGraph');

// Toggle between grid and graph view
if (toggleGraphViewBtn) {
    toggleGraphViewBtn.addEventListener('click', async () => {
        graphViewActive = !graphViewActive;
        toggleGraphViewBtn.classList.toggle('active', graphViewActive);

        if (graphViewActive) {
            graphViewContainer.style.display = 'block';
            gridViewContainer.style.display = 'none';

            if (!topologyData) {
                await fetchAndRenderTopology();
            }
        } else {
            graphViewContainer.style.display = 'none';
            gridViewContainer.style.display = 'grid';
        }
    });
}

async function fetchAndRenderTopology() {
    try {
        mermaidGraphEl.innerHTML = '<div class="placeholder">Loading topology...</div>';

        const response = await fetch(`${API_BASE}/graph/topology`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        topologyData = await response.json();
        await renderMermaidGraph(topologyData);

    } catch (error) {
        console.error('Failed to fetch topology:', error);
        mermaidGraphEl.innerHTML = `<div class="placeholder" style="color: var(--alert-color);">Failed to load topology: ${error.message}</div>`;
    }
}

async function renderMermaidGraph(data) {
    if (!data || !data.nodes) return;

    const mermaid = window.mermaid;
    if (!mermaid) {
        mermaidGraphEl.innerHTML = '<div class="placeholder">Mermaid library not loaded</div>';
        return;
    }

    // Group nodes by category for subgraph clustering
    const categories = {};
    data.nodes.forEach(node => {
        const cat = node.category || 'other';
        if (!categories[cat]) categories[cat] = [];
        categories[cat].push(node);
    });

    // Build Mermaid flowchart definition
    let def = 'graph TD\n';

    // Style classes
    def += '  classDef router fill:#FF9F1C,stroke:#1a1a2e,color:#1a1a2e,stroke-width:2px\n';
    def += '  classDef core fill:#2EC4B6,stroke:#1a1a2e,color:#1a1a2e,stroke-width:2px\n';
    def += '  classDef specialist fill:#242442,stroke:#2EC4B6,color:#FFECC2,stroke-width:1px\n';
    def += '  classDef mcp fill:#16213e,stroke:#FF9F1C,color:#FF9F1C,stroke-width:1px,stroke-dasharray:5\n';
    def += '  classDef active fill:#FF9F1C,stroke:#FFECC2,color:#1a1a2e,stroke-width:3px\n';

    // Category display names
    const catNames = {
        orchestration: 'Orchestration',
        planning: 'Planning',
        context: 'Context Engineering',
        research: 'Research',
        chat: 'Chat Pipeline',
        data: 'Data & Analysis',
        files: 'File Operations',
        builders: 'Builders',
        distillation: 'Distillation',
        utilities: 'Utilities',
        core: 'Core Infrastructure',
        mcp_only: 'MCP Services',
        other: 'Other'
    };

    // Render subgraphs by category
    const orderedCats = ['orchestration', 'planning', 'context', 'chat', 'research',
                         'data', 'files', 'builders', 'distillation', 'utilities', 'core', 'mcp_only', 'other'];

    for (const cat of orderedCats) {
        const nodes = categories[cat];
        if (!nodes || nodes.length === 0) continue;

        const displayName = catNames[cat] || cat;
        def += `  subgraph ${cat}["${displayName}"]\n`;

        for (const node of nodes) {
            const id = node.id.replace(/[^a-zA-Z0-9_]/g, '_');
            const label = node.id.replace(/_specialist$/, '').replace(/_/g, ' ').toUpperCase();

            if (node.type === 'router') {
                def += `    ${id}{{${label}}}\n`;
            } else if (node.type === 'core_infrastructure') {
                def += `    ${id}([${label}])\n`;
            } else if (node.type === 'mcp_only') {
                def += `    ${id}[/${label}/]\n`;
            } else {
                def += `    ${id}["${label}"]\n`;
            }
        }

        def += '  end\n';
    }

    // Add edges
    for (const edge of data.edges) {
        const src = edge.source.replace(/[^a-zA-Z0-9_]/g, '_');
        const tgt = edge.target.replace(/[^a-zA-Z0-9_]/g, '_');

        if (edge.type === 'conditional') {
            def += `  ${src} -.->|route| ${tgt}\n`;
        } else if (edge.type === 'completion') {
            def += `  ${src} -->|${edge.label}| ${tgt}\n`;
        } else {
            def += `  ${src} ==>|${edge.label}| ${tgt}\n`;
        }
    }

    // Apply node type styles
    for (const node of data.nodes) {
        const id = node.id.replace(/[^a-zA-Z0-9_]/g, '_');
        if (node.type === 'router') def += `  class ${id} router\n`;
        else if (node.type === 'core_infrastructure') def += `  class ${id} core\n`;
        else if (node.type === 'mcp_only') def += `  class ${id} mcp\n`;
        else def += `  class ${id} specialist\n`;
    }

    // Render
    try {
        mermaidRenderCount++;
        const { svg } = await mermaid.render(`mermaid-graph-${mermaidRenderCount}`, def);
        mermaidGraphEl.innerHTML = svg;
    } catch (err) {
        console.error('Mermaid render error:', err);
        mermaidGraphEl.innerHTML = `<div class="placeholder" style="color: var(--alert-color);">Render error: ${err.message}</div>`;
    }
}

function highlightMermaidNode(nodeName) {
    if (!graphViewActive) return;

    // Remove previous highlights
    document.querySelectorAll('.mermaid-container .node.highlighted').forEach(el => {
        el.classList.remove('highlighted');
    });

    // Find and highlight the matching node
    const nodeId = nodeName.replace(/[^a-zA-Z0-9_]/g, '_');
    // Mermaid uses data-id attribute on node groups
    const svgNode = mermaidGraphEl.querySelector(`[id*="${nodeId}"]`);
    if (svgNode) {
        // Walk up to the .node group
        let group = svgNode.closest('.node') || svgNode;
        group.classList.add('highlighted');

        // Also try to apply the active class style
        const rect = group.querySelector('rect, polygon, circle');
        if (rect) {
            rect.style.stroke = '#FFECC2';
            rect.style.strokeWidth = '3px';
            // Reset after 3s
            setTimeout(() => {
                rect.style.stroke = '';
                rect.style.strokeWidth = '';
            }, 3000);
        }
    }
}


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


// =============================================================================
// MISSION REPORT RENDERING
// =============================================================================

function renderMissionReport(markdown) {
    if (!markdown) return;

    // Parse markdown and render to HTML
    const html = marked.parse(markdown);
    archiveOutputEl.innerHTML = html;

    // Generate sub-tabs from H2 headers
    const sections = archiveOutputEl.querySelectorAll('h2');
    if (sections.length > 1) {
        archiveSubtabsEl.innerHTML = '';
        sections.forEach((section, idx) => {
            const btn = document.createElement('button');
            btn.className = 'archive-subtab' + (idx === 0 ? ' active' : '');
            btn.textContent = section.textContent;
            btn.addEventListener('click', () => {
                document.querySelectorAll('.archive-subtab').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                section.scrollIntoView({ behavior: 'smooth', block: 'start' });
            });
            archiveSubtabsEl.appendChild(btn);
        });

        // Set up intersection observer for auto-highlighting
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const idx = Array.from(sections).indexOf(entry.target.querySelector('h2') || entry.target);
                    if (idx >= 0) {
                        document.querySelectorAll('.archive-subtab').forEach((b, i) => {
                            b.classList.toggle('active', i === idx);
                        });
                    }
                }
            });
        }, { root: archiveOutputEl, threshold: 0.3 });

        // Wrap sections for observing
        const wrapper = document.createElement('div');
        let currentSection = null;
        Array.from(archiveOutputEl.childNodes).forEach(node => {
            if (node.tagName === 'H2') {
                if (currentSection) wrapper.appendChild(currentSection);
                currentSection = document.createElement('div');
                currentSection.className = 'report-section';
            }
            if (currentSection) {
                currentSection.appendChild(node.cloneNode(true));
            }
        });
        if (currentSection) wrapper.appendChild(currentSection);
        archiveOutputEl.innerHTML = '';
        archiveOutputEl.appendChild(wrapper);

        // Observe all sections
        document.querySelectorAll('.report-section').forEach(section => {
            observer.observe(section);
        });
    }

    // Add copy/save toolbars to code blocks
    addToolbarsToPreBlocks();
}


// =============================================================================
// SSE EVENT HANDLING
// =============================================================================

function handleStreamEvent(event) {
    const now = Date.now();
    lastUpdateTime = now;

    if (event.run_id && !currentRunId) {
        currentRunId = event.run_id;
        logStatus(`► RUN ID: ${currentRunId}`);
        startProgressPolling(currentRunId);
    }

    const data = event.data || {};
    const source = event.source || 'system';

    // ADR-CORE-042: Handle raw interrupt events from _stream_formatter
    if (event.interrupt || data.interrupt) {
        const interruptData = event.interrupt || data.interrupt;
        pendingThreadId = event.thread_id || data.thread_id;

        let questionsHtml = '';
        const questions = interruptData.questions || [];
        if (questions.length > 0) {
            questionsHtml = '<ul style="list-style: none; padding: 0;">';
            questions.forEach(q => {
                if (typeof q === 'object') {
                    questionsHtml += `<li style="margin: 10px 0;">• ${q.question || q.reason || String(q)}`;
                    if (q.reason) questionsHtml += `<br><span style="opacity: 0.7; font-size: 0.9em;">  (${q.reason})</span>`;
                    questionsHtml += '</li>';
                } else {
                    questionsHtml += `<li style="margin: 10px 0;">• ${q}</li>`;
                }
            });
            questionsHtml += '</ul>';
        } else if (interruptData.question) {
            questionsHtml = `<p style="margin: 10px 0; color: var(--primary-color);">${interruptData.question}</p>`;
            if (interruptData.reason && interruptData.reason !== interruptData.question) {
                questionsHtml += `<p style="opacity: 0.7; font-size: 0.9em;">${interruptData.reason}</p>`;
            }
        }

        clarificationQuestions.innerHTML = questionsHtml;
        clarificationInput.value = '';
        clarificationModal.style.display = 'block';
        clarificationInput.focus();

        addThoughtStreamEntry('SYSTEM', 'Clarification requested - awaiting user input', 'lifecycle');
        logStatus('► AWAITING CLARIFICATION...');
        return;
    }

    switch (event.type) {
        case 'workflow_start':
            logStatus(`► WORKFLOW STARTED`);
            addThoughtStreamEntry('SYSTEM', 'Workflow initiated', 'lifecycle');
            break;

        case 'status_update':
            if (data.status) {
                logStatus(`► ${data.status}`);
                if (data.status.includes('→') || data.status.toLowerCase().includes('routing to')) {
                    const targetMatch = data.status.match(/(?:→|routing to)\s*(\w+)/i);
                    if (targetMatch) {
                        addThoughtStreamEntry('ROUTER', data.status, 'routing', { target: targetMatch[1] });
                    }
                }
            }
            break;

        case 'node_start':
        case 'specialist_start':
            if (source) {
                addRoutingEntry(source);
                const displayName = source.replace(/_specialist$/, '').replace(/_/g, ' ');
                addThoughtStreamEntry(source, `${displayName} starting...`, 'lifecycle');
            }
            break;

        case 'node_end':
        case 'specialist_end':
            if (source) {
                const displayName = source.replace(/_specialist$/, '').replace(/_/g, ' ');
                addThoughtStreamEntry(source, `${displayName} complete`, 'success');

                if (data.scratchpad) {
                    if (data.scratchpad.recommended_specialists && Array.isArray(data.scratchpad.recommended_specialists)) {
                        const recs = data.scratchpad.recommended_specialists;
                        const message = `Recommending: ${recs.join(', ')}`;
                        addThoughtStreamEntry('TRIAGE', message, 'reasoning', { collapsible: recs.length > 2 });
                    }

                    if (data.scratchpad.router_decision) {
                        const decision = data.scratchpad.router_decision;
                        const isLong = decision.length > 80;
                        if (isLong) {
                            addThoughtStreamEntry('ROUTER', decision, 'reasoning', { collapsible: true });
                        } else {
                            addThoughtStreamEntry('ROUTER', decision, 'routing', { target: decision });
                        }
                    }

                    Object.keys(data.scratchpad).forEach(key => {
                        if (key.endsWith('_reasoning')) {
                            const specialist = key.replace(/_reasoning$/, '').toUpperCase().replace(/_/g, ' ');
                            const value = String(data.scratchpad[key]);
                            const isLong = value.length > 100 || value.includes('\n');
                            if (isLong) {
                                addThoughtStreamEntry(specialist, value, 'reasoning', { collapsible: true });
                            } else {
                                addThoughtStreamEntry(specialist, value, 'reasoning');
                            }
                        } else if (key.endsWith('_decision') && key !== 'router_decision') {
                            const specialist = key.replace(/_decision$/, '').toUpperCase().replace(/_/g, ' ');
                            addThoughtStreamEntry(specialist, data.scratchpad[key], 'info');
                        }
                    });

                    if (data.scratchpad.facilitator_complete) {
                        addThoughtStreamEntry('FACILITATOR', 'Context gathering complete', 'success');
                    }
                }

                if (data.artifacts) {
                    updateArtifactsDisplay(data.artifacts);

                    Object.keys(data.artifacts).forEach(key => {
                        if (key !== 'archive_report.md') {
                            addThoughtStreamEntry(source, key, 'artifact');
                        }
                    });
                }
            }
            break;

        case 'log':
            if (data.message) {
                if (data.message.includes('MCP') || data.message.includes('Facilitator: Executing action')) {
                    const mcpMatch = data.message.match(/(\w+_specialist)\.(\w+)\((.*?)\)/);
                    if (mcpMatch) {
                        const [_, service, method, params] = mcpMatch;
                        addThoughtStreamEntry('MCP', `${service}.${method}`, 'mcp', {
                            service: service.replace(/_specialist$/, ''),
                            method: method,
                            params: params || null
                        });
                    } else if (data.message.includes('Executing action')) {
                        addThoughtStreamEntry('FACILITATOR', data.message.split('Facilitator: ')[1] || data.message, 'info');
                    }
                }
            }
            break;

        case 'error':
            logStatus(`❌ ERROR: ${data.error}`);
            addThoughtStreamEntry('SYSTEM', data.error, 'error');
            if (data.error_report) {
                archiveOutputEl.innerHTML = marked.parse(`## ❌ Error Report\n\n${data.error_report}`);
            }
            break;

        case 'workflow_end':
            stopProgressPolling();
            logStatus(`► WORKFLOW COMPLETE`);
            addThoughtStreamEntry('SYSTEM', 'Workflow completed successfully', 'lifecycle');

            if (data.final_state) {
                jsonOutputEl.textContent = JSON.stringify(data.final_state, null, 2);
            }

            // #181: Snapshot completed run into history
            runHistory.push({
                timestamp: new Date().toISOString(),
                conversationId: data.conversation_id || null,
                finalResponse: data.archive || '',
                artifacts: { ...currentArtifacts }
            });
            currentPageIndex = runHistory.length - 1;
            try {
                sessionStorage.setItem('runHistory', JSON.stringify(runHistory));
            } catch (e) {
                console.warn('Failed to save run history (storage full?):', e);
            }
            updatePagingControls();
            renderPage(currentPageIndex);
            break;

        case 'clarification_required':
            pendingThreadId = event.thread_id || data.thread_id;
            const crQuestions = data.questions || [];

            let crQuestionsHtml = '';
            if (crQuestions.length > 0) {
                crQuestionsHtml = '<ul style="list-style: none; padding: 0;">';
                crQuestions.forEach(q => {
                    if (typeof q === 'object') {
                        crQuestionsHtml += `<li style="margin: 10px 0;">• ${q.question || q.reason || String(q)}`;
                        if (q.reason) crQuestionsHtml += `<br><span style="opacity: 0.7; font-size: 0.9em;">  (${q.reason})</span>`;
                        crQuestionsHtml += '</li>';
                    } else {
                        crQuestionsHtml += `<li style="margin: 10px 0;">• ${q}</li>`;
                    }
                });
                crQuestionsHtml += '</ul>';
            } else if (data.question) {
                crQuestionsHtml = `<p style="margin: 10px 0; color: var(--primary-color);">${data.question}</p>`;
                if (data.reason && data.reason !== data.question) {
                    crQuestionsHtml += `<p style="opacity: 0.7; font-size: 0.9em;">${data.reason}</p>`;
                }
            }

            clarificationQuestions.innerHTML = crQuestionsHtml;
            clarificationInput.value = '';
            clarificationModal.style.display = 'block';
            clarificationInput.focus();

            addThoughtStreamEntry('SYSTEM', 'Clarification requested - awaiting user input', 'lifecycle');
            logStatus('► AWAITING CLARIFICATION...');
            break;

        case 'state_snapshot':
            stateSnapshots.push(data);
            snapshotPageIndex = stateSnapshots.length - 1;
            renderSnapshot(snapshotPageIndex);
            updateSnapshotPagingControls();
            break;

        default:
            console.warn("Unknown event type:", event.type, event);
    }
}


// =============================================================================
// CODE BLOCK TOOLBARS
// =============================================================================

function addToolbarsToPreBlocks() {
    const preBlocks = document.querySelectorAll('#archiveOutput pre:not(.has-toolbar), #snapshotContent pre:not(.has-toolbar)');

    preBlocks.forEach(pre => {
        if (pre.querySelector('.toolbar')) return;
        pre.classList.add('has-toolbar');
        pre.style.position = 'relative';

        const toolbar = document.createElement('div');
        toolbar.className = 'toolbar';
        toolbar.style.cssText = 'position: absolute; top: 4px; right: 4px; display: flex; gap: 4px; z-index: 10;';

        // Copy button
        const copyBtn = document.createElement('button');
        copyBtn.className = 'toolbar-btn';
        copyBtn.textContent = 'COPY';
        copyBtn.onclick = async (e) => {
            e.stopPropagation();
            try {
                await navigator.clipboard.writeText(pre.textContent);
                copyBtn.textContent = 'OK';
                setTimeout(() => { copyBtn.textContent = 'COPY'; }, 1000);
            } catch (err) {
                // Fallback
                const range = document.createRange();
                range.selectNodeContents(pre);
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);
                document.execCommand('copy');
                sel.removeAllRanges();
                copyBtn.textContent = 'OK';
                setTimeout(() => { copyBtn.textContent = 'COPY'; }, 1000);
            }
        };
        toolbar.appendChild(copyBtn);

        // Save button (only for content > 500 chars)
        if (pre.textContent.length > 500) {
            const saveBtn = document.createElement('button');
            saveBtn.className = 'toolbar-btn';
            saveBtn.textContent = 'SAVE';
            saveBtn.onclick = (e) => {
                e.stopPropagation();
                const blob = new Blob([pre.textContent], { type: 'text/plain' });
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = 'output.txt';
                a.click();
                URL.revokeObjectURL(a.href);
            };
            toolbar.appendChild(saveBtn);
        }

        pre.appendChild(toolbar);
    });
}


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
// INTRA-NODE PROGRESS POLLING
// =============================================================================

function startProgressPolling(runId) {
    if (progressInterval) clearInterval(progressInterval);
    progressInterval = setInterval(async () => {
        try {
            const resp = await fetch(`${API_BASE}/progress/${runId}`);
            if (!resp.ok) return;
            const data = await resp.json();
            for (const entry of (data.entries || [])) {
                renderProgressEntry(entry);
            }
        } catch (e) {
            // Silently ignore poll failures (run may have ended)
        }
    }, 2500);
}

function stopProgressPolling() {
    if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
    }
}

function renderProgressEntry(entry) {
    const specialist = (entry.specialist || 'project_director').replace(/_specialist$/, '').replace(/_/g, ' ').toUpperCase();
    const tool = entry.tool || 'unknown';

    // #250: Delegate start (pre-dispatch, no fork_metadata yet)
    if (tool === 'delegate' && !entry.fork_metadata) {
        addThoughtStreamEntry(specialist, entry.args_summary || 'Delegating to child run...', 'lifecycle');
        return;
    }

    // Fork entries get special rendering (delegate completion with fork_metadata)
    if (entry.fork_metadata) {
        const fm = entry.fork_metadata;
        const route = (fm.child_routing_history || []).join(' \u2192 ');
        addThoughtStreamEntry(specialist, entry.args_summary || tool, 'fork', {
            childRunId: fm.child_run_id,
            childRoute: route,
            hadError: fm.had_error,
        });
        return;
    }

    // _start entries render as lifecycle
    if (tool === '_start') {
        addThoughtStreamEntry(specialist, entry.args_summary || 'Starting react loop...', 'lifecycle');
        return;
    }

    // Regular tool calls
    if (entry.success) {
        addThoughtStreamEntry(specialist, `${tool}()`, 'mcp', {
            service: 'react_step',
            method: tool,
            params: entry.args_summary,
        });
    } else {
        addThoughtStreamEntry(specialist, `${tool}() \u2014 ${(entry.observation_preview || 'failed').substring(0, 100)}`, 'error');
    }
}


// =============================================================================
// HEADLESS MODE — observe externally-initiated runs (#267)
// =============================================================================

headlessModeCheckbox.addEventListener('change', () => {
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
