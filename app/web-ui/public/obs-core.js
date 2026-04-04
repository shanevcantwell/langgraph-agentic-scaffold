// =============================================================================
// V.E.G.A.S. TERMINAL — Core Observability Primitives
// Loads after app.js. Provides logStatus, addThoughtStreamEntry,
// updateArtifactsDisplay, addRoutingEntry, updateSpecialistGrid.
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
