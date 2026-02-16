const API_BASE = '/v1'; // Proxied by server.js

// DOM Elements
const promptInput = document.getElementById('promptInput');
const executeBtn = document.getElementById('executeBtn');
const cancelBtn = document.getElementById('cancelBtn');
const simpleChatMode = document.getElementById('simpleChatMode');
const routingLogEl = document.getElementById('routingLog');
const systemStatusEl = document.getElementById('systemStatus');
const thoughtStreamEl = document.getElementById('thoughtStream');
const archiveSubtabsEl = document.getElementById('archiveSubtabs');
const archiveOutputEl = document.getElementById('archiveOutput');
const artifactsOutputEl = document.getElementById('artifactsOutput');
const jsonOutputEl = document.getElementById('jsonOutput');

// STATE tab sub-view elements
const stateSubBtns = document.querySelectorAll('.state-sub-btn');
const stateViews = document.querySelectorAll('.state-view');
const snapshotPrevBtn = document.getElementById('snapshotPrev');
const snapshotNextBtn = document.getElementById('snapshotNext');
const snapshotLabelEl = document.getElementById('snapshotLabel');
const snapshotTimestampEl = document.getElementById('snapshotTimestamp');
const snapshotContentEl = document.getElementById('snapshotContent');

// File Upload Elements
const fileInput = document.getElementById('fileInput');
const uploadBtn = document.getElementById('uploadBtn');
const clearFileBtn = document.getElementById('clearFileBtn');
const fileNameEl = document.getElementById('fileName');

// Zoom Modal Elements
// const zoomBtn = document.getElementById('zoomBtn'); // Removed
const zoomModal = document.getElementById('zoomModal');
const closeModal = document.querySelector('.close-modal');
const modalBody = document.getElementById('modal-body');

// Mission Report Tabs (consolidated)
const tabBtns = document.querySelectorAll('.trace-panel .tab-btn');
const tabContents = document.querySelectorAll('.trace-panel .tab-content');

// State
let currentRunId = null;
let tracePollInterval = null;
let turnCount = 0;
let startTime = 0;
let lastUpdateTime = 0;
let loadedFile = null; // { content: string, type: 'text' | 'image' }
let abortController = null; // Controller for the fetch request
let thoughtStreamEntries = []; // Track thought stream entries
let currentArtifacts = {}; // Track artifacts as they're generated

// STATE tab: snapshot accumulator and intra-run paging
let stateSnapshots = [];       // Accumulates state_snapshot events within current run
let snapshotPageIndex = -1;    // Current snapshot being viewed (-1 = none)

// ADR-UI-001 / #181: Run history for Mission Report paging + context selection
let runHistory = [];        // [{timestamp, conversationId, finalResponse, artifacts}]
let currentPageIndex = -1;  // -1 = no history yet
let checkedItems = {};      // {pageIndex: {key: bool, _finalResponse: bool}}

// Paging DOM refs
const pagePrevBtn = document.getElementById('pagePrev');
const pageNextBtn = document.getElementById('pageNext');
const pageTimestampEl = document.getElementById('pageTimestamp');
const selectAllCheckbox = document.getElementById('selectAllContext');

// ADR-CORE-042: Clarification state and DOM refs
let pendingThreadId = null;
const clarificationModal = document.getElementById('clarificationModal');
const clarificationQuestions = document.getElementById('clarificationQuestions');
const clarificationInput = document.getElementById('clarificationInput');
const clarificationSubmitBtn = document.getElementById('clarificationSubmitBtn');

// Theme Switcher Logic
const themeBtns = document.querySelectorAll('.theme-btn');

// Load saved theme
const savedTheme = localStorage.getItem('theme') || 'light';
setTheme(savedTheme);

themeBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        const theme = btn.dataset.theme;
        setTheme(theme);
    });
});

function setTheme(theme) {
    // Update DOM
    if (theme === 'light') {
        document.documentElement.removeAttribute('data-theme');
    } else {
        document.documentElement.setAttribute('data-theme', theme);
    }

    // Update Buttons
    themeBtns.forEach(btn => {
        if (btn.dataset.theme === theme) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });

    // Save preference
    localStorage.setItem('theme', theme);
}

// Config Refresh Logic
const refreshConfigBtn = document.getElementById('refreshConfigBtn');

refreshConfigBtn.addEventListener('click', async () => {
    logStatus('► RELOADING CONFIGURATION...');
    refreshConfigBtn.disabled = true;
    const originalContent = refreshConfigBtn.innerHTML;
    refreshConfigBtn.textContent = 'Wait...';

    try {
        const res = await fetch(`${API_BASE}/system/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}) // Empty body triggers reload from disk
        });

        if (!res.ok) throw new Error('Failed to reload config');
        const data = await res.json();
        logStatus('► CONFIGURATION RELOADED');
        
        refreshConfigBtn.textContent = 'Done!';
        setTimeout(() => {
            refreshConfigBtn.innerHTML = originalContent;
            refreshConfigBtn.disabled = false;
        }, 1500);

    } catch (e) {
        console.error("Error reloading config:", e);
        logStatus('❌ ERROR RELOADING CONFIG');
        refreshConfigBtn.textContent = 'Error';
        setTimeout(() => {
            refreshConfigBtn.innerHTML = originalContent;
            refreshConfigBtn.disabled = false;
        }, 2000);
    }
});

// Event Listeners
executeBtn.addEventListener('click', executeWorkflow);
cancelBtn.addEventListener('click', handleAbort); // Changed to handleAbort
promptInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        executeWorkflow();
    }
});

// File Upload Logic
uploadBtn.addEventListener('click', () => fileInput.click());

fileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    
    // Check if image - currently only PNG is supported (see Issue #16 for mimetype handling)
    if (file.type.startsWith('image/')) {
        if (file.type !== 'image/png') {
            logStatus(`⚠ Only PNG images are currently supported. Got: ${file.type}`);
            fileInput.value = '';
            return;
        }
        reader.onload = (e) => {
            loadedFile = {
                content: e.target.result, // base64 data url
                type: 'image'
            };
            updateFileUI(file.name);
        };
        reader.readAsDataURL(file);
    } else {
        // Assume text for everything else
        reader.onload = (e) => {
            loadedFile = {
                content: e.target.result,
                type: 'text'
            };
            updateFileUI(file.name);
        };
        reader.readAsText(file);
    }
});

clearFileBtn.addEventListener('click', () => {
    fileInput.value = '';
    loadedFile = null;
    fileNameEl.textContent = 'NO DATA LOADED';
    fileNameEl.style.opacity = '0.7';
    clearFileBtn.style.display = 'none';
});

function updateFileUI(name) {
    fileNameEl.textContent = `[LOADED: ${name}]`;
    fileNameEl.style.opacity = '1';
    clearFileBtn.style.display = 'inline-block';
}

// Zoom Modal Logic
/*
zoomBtn.addEventListener('click', () => {
    modalBody.innerHTML = archiveOutputEl.innerHTML;
    zoomModal.style.display = 'block';
});
*/

closeModal.addEventListener('click', () => {
    zoomModal.style.display = 'none';
});

window.addEventListener('click', (e) => {
    if (e.target == zoomModal) {
        zoomModal.style.display = 'none';
    }
});

tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        tabBtns.forEach(b => b.classList.remove('active'));
        tabContents.forEach(c => c.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active');
    });
});

// STATE tab sub-view switching (Inspector vs Raw)
stateSubBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        stateSubBtns.forEach(b => b.classList.remove('active'));
        stateViews.forEach(v => v.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById(`state-${btn.dataset.view}`).classList.add('active');
    });
});

// STATE tab snapshot paging
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

// #181: Mission Report paging handlers
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
    // Toggle all checkboxes on current page
    document.querySelectorAll('.artifact-row .context-checkbox, .context-select-row .context-checkbox')
        .forEach(cb => {
            cb.checked = checked;
            cb.dispatchEvent(new Event('change', { bubbles: false }));
        });
});

// Restore run history from sessionStorage on page load
try {
    const saved = sessionStorage.getItem('runHistory');
    if (saved) {
        runHistory = JSON.parse(saved);
        if (runHistory.length > 0) {
            currentPageIndex = runHistory.length - 1;
            updatePagingControls();
        }
    }
} catch (e) {
    console.warn('Failed to restore run history:', e);
}

// ADR-CORE-042: Clarification submission handlers
if (clarificationSubmitBtn) {
    clarificationSubmitBtn.addEventListener('click', submitClarification);
}
if (clarificationInput) {
    clarificationInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            submitClarification();
        }
    });
}
// Close clarification modal on outside click
window.addEventListener('click', (e) => {
    if (e.target == clarificationModal) {
        clarificationModal.style.display = 'none';
    }
});

async function submitClarification() {
    const userInput = clarificationInput.value.trim();
    if (!userInput || !pendingThreadId) {
        logStatus('► ERROR: No clarification provided');
        return;
    }

    clarificationModal.style.display = 'none';
    logStatus('► RESUMING WORKFLOW...');
    addThoughtStreamEntry('SYSTEM', `User clarification: "${userInput.substring(0, 80)}${userInput.length > 80 ? '...' : ''}"`, 'lifecycle');

    try {
        // Resume endpoint now streams SSE events (same format as initial run)
        const response = await fetch(`${API_BASE}/graph/resume`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                thread_id: pendingThreadId,
                user_input: userInput
            })
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        // Don't clear pendingThreadId yet — a second interrupt may set it
        // during the stream. Only clear after stream completes without interrupt.

        // Consume SSE stream — same pattern as executeWorkflow
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        handleStreamEvent(data);
                    } catch (e) {
                        console.error("Error parsing resume SSE data:", e, line);
                    }
                }
            }
        }

        // If a new interrupt was set during the stream, don't overwrite status
        if (pendingThreadId) {
            logStatus('► AWAITING CLARIFICATION...');
        } else {
            logStatus('► WORKFLOW RESUMED SUCCESSFULLY');
        }

    } catch (error) {
        logStatus(`❌ RESUME ERROR: ${error.message}`);
        addThoughtStreamEntry('SYSTEM', `Resume failed: ${error.message}`, 'error');
    }
}

async function executeWorkflow() {
    const prompt = promptInput.value.trim();
    if (!prompt) return;

    // Reset UI
    promptInput.disabled = true;
    executeBtn.disabled = true;
    executeBtn.style.display = 'none';
    cancelBtn.style.display = 'inline-block';
    cancelBtn.disabled = false;
    cancelBtn.textContent = '⏹️ ABORT';
    
    systemStatusEl.innerHTML = '► INITIALIZING...';
    routingLogEl.innerHTML = '';
    thoughtStreamEl.innerHTML = '<div class="placeholder">WAITING FOR COGNITIVE ACTIVITY...</div>';
    archiveSubtabsEl.innerHTML = '';
    archiveOutputEl.innerHTML = '<div class="placeholder">WAITING FOR MISSION DATA...</div>';
    artifactsOutputEl.innerHTML = '<div class="placeholder">NO ARTIFACTS YET...</div>';
    jsonOutputEl.textContent = '{}';

    // Reset state trackers
    thoughtStreamEntries = [];
    currentArtifacts = {};

    // Reset state snapshots for new run
    stateSnapshots = [];
    snapshotPageIndex = -1;
    snapshotContentEl.innerHTML = '<div class="placeholder">WAITING FOR STATE SNAPSHOTS...</div>';
    snapshotLabelEl.textContent = 'NO SNAPSHOTS';
    snapshotTimestampEl.textContent = '';
    updateSnapshotPagingControls();

    // Reset Specialist Grid
    document.querySelectorAll('.spec-node').forEach(el => el.classList.remove('active'));
    
    currentRunId = null;
    turnCount++;
    // turnCountEl.textContent = String(turnCount).padStart(3, '0'); // Removed
    startTime = Date.now();
    lastUpdateTime = startTime;

    // Prepare Payload
    const payload = {
        input_prompt: prompt,
        use_simple_chat: simpleChatMode.checked
    };

    if (loadedFile) {
        if (loadedFile.type === 'image') {
            // Extract raw base64 from data URL (adapter expects base64 only, not full data URL)
            // Handle both data URLs and raw base64
            const content = loadedFile.content;
            payload.image_to_process = content.startsWith('data:') ? content.split(',')[1] : content;
            logStatus(`► INJECTING IMAGE DATA...`);
        } else {
            payload.text_to_process = loadedFile.content;
            logStatus(`► INJECTING TEXT DATA...`);
        }
    }

    // #181: Collect checked context from prior runs
    const priorMessages = [];
    let latestConversationId = null;

    for (let i = 0; i < runHistory.length; i++) {
        const page = runHistory[i];
        const checks = checkedItems[i];
        if (!checks) continue;

        if (page.conversationId) latestConversationId = page.conversationId;

        const parts = [];
        for (const [key, isChecked] of Object.entries(checks)) {
            if (!isChecked) continue;
            if (key === '_finalResponse') {
                if (page.finalResponse) parts.push(`final_response:\n${page.finalResponse}`);
            } else if (page.artifacts[key] !== undefined) {
                const val = typeof page.artifacts[key] === 'object'
                    ? JSON.stringify(page.artifacts[key], null, 2)
                    : String(page.artifacts[key]);
                parts.push(`${key}:\n${val}`);
            }
        }

        if (parts.length > 0) {
            const ts = new Date(page.timestamp).toLocaleTimeString();
            priorMessages.push({
                role: 'assistant',
                content: `[Prior Run ${ts}]\n\n${parts.join('\n\n')}`
            });
        }
    }

    if (priorMessages.length > 0) {
        payload.prior_messages = priorMessages;
        logStatus(`► ATTACHING CONTEXT FROM ${priorMessages.length} PRIOR RUN(S)...`);
    }
    if (latestConversationId) {
        payload.conversation_id = latestConversationId;
    }

    // Create new AbortController for this request
    abortController = new AbortController();
    let isTimeout = false;
    const CONNECTION_TIMEOUT_MS = 15000; // 15 seconds to establish connection

    // Start connection timeout
    const timeoutId = setTimeout(() => {
        isTimeout = true;
        if (abortController) abortController.abort();
    }, CONNECTION_TIMEOUT_MS);

    try {
        const response = await fetch(`${API_BASE}/graph/stream/events`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
            signal: abortController.signal
        });

        // Connection established, clear timeout
        clearTimeout(timeoutId);

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n\n');
            buffer = lines.pop(); // Keep the last incomplete chunk
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        handleStreamEvent(data);
                    } catch (e) {
                        console.error("Error parsing SSE data:", e, line);
                    }
                }
            }
        }

    } catch (error) {
        clearTimeout(timeoutId); // Ensure timeout is cleared on error
        
        if (error.name === 'AbortError') {
            if (isTimeout) {
                logStatus('❌ CONNECTION TIMED OUT');
                renderMissionReport('## ❌ Connection Timed Out\n\nThe server failed to respond within 15 seconds.\n\n**Possible Causes:**\n1. The backend is hanging while trying to contact an LLM.\n2. The Proxy is blocking an outgoing connection.\n3. The local LLM (LM Studio) is not running or is unresponsive.');
            } else {
                logStatus('► MISSION ABORTED BY USER');
                renderMissionReport('## Mission Aborted\n\nThe user manually cancelled this mission.');
            }
        } else {
            logStatus(`❌ ERROR: ${error.message}`);
        }
    } finally {
        promptInput.disabled = false;
        executeBtn.disabled = false;
        executeBtn.style.display = 'inline-block';
        cancelBtn.style.display = 'none';

        // Prompt remains visible for copy/paste or re-execution
        // User can manually select all + delete to clear, or just type over it

        stopTracePolling();
        abortController = null;

        // Clear file after send? Maybe keep it? Let's keep it for now, user can clear manually.
    }
}

async function handleAbort() {
    // 1. Abort the client-side fetch immediately to free up the browser connection
    if (abortController) {
        abortController.abort();
    }

    // 2. Attempt to notify the backend to stop processing (best effort)
    if (currentRunId) {
        cancelBtn.disabled = true;
        cancelBtn.textContent = 'ABORTING...';
        logStatus('► SENDING ABORT SIGNAL...');
        
        try {
            // Use a short timeout for the cancel request so it doesn't hang if the server is busy
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 2000);
            
            const res = await fetch(`${API_BASE}/graph/cancel/${currentRunId}`, {
                method: 'POST',
                signal: controller.signal
            });
            clearTimeout(timeoutId);
            
            if (res.ok) {
                console.log('Backend cancellation confirmed');
            }
        } catch (e) {
            console.warn("Backend cancellation request failed (likely due to connection limit or timeout):", e);
        }
    }
}

// Removed old cancelWorkflow function
// async function cancelWorkflow() { ... }

// ============================================================================
// THOUGHT STREAM & MCP TRACE HELPERS
// ============================================================================

function formatTimestamp() {
    const now = new Date();
    return `[${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}]`;
}

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

    // Build entry based on semantic type
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

        case 'reasoning':
            div.className = 'thought-entry thought-reasoning' + (options.collapsible ? ' collapsed' : '');
            const toggleId = `reasoning-${Date.now()}`;
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

/**
 * Decode HTML entities to their actual characters.
 * Handles common entities like &#x27; -> ' and &amp; -> &
 */
function decodeHtmlEntities(text) {
    const textarea = document.createElement('textarea');
    textarea.innerHTML = text;
    return textarea.value;
}

function updateArtifactsDisplay(artifacts) {
    if (!artifacts || Object.keys(artifacts).length === 0) return;

    currentArtifacts = { ...currentArtifacts, ...artifacts };

    // #198: Build display with textContent to prevent HTML artifact CSS bleed.
    // Previously used marked.parse() with code blocks, but artifact content
    // containing triple backticks or <style> tags could escape into parent CSS.
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

// ============================================================================
// STATE TAB: SNAPSHOT PAGING & RENDERING
// ============================================================================

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

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

            // Step header
            html += '<div class="tool-chain-step">';
            html += `<span class="tool-chain-iteration">iter ${entry.iteration != null ? entry.iteration : '?'}</span>`;
            html += `<span class="tool-chain-status">${statusIcon}</span>`;
            html += '</div>';

            html += '<div class="tool-chain-details">';

            // Tool call header
            html += '<div class="tool-call-header">';
            html += `<span class="tool-call-name">${escapeHtml(tc.name || 'unknown')}</span>`;
            if (tc.id) {
                html += `<span class="tool-call-id">${escapeHtml(tc.id)}</span>`;
            }
            html += '</div>';

            // Tool arguments
            if (tc.args && Object.keys(tc.args).length > 0) {
                html += '<div class="tool-call-args">';
                html += `<pre>${escapeHtml(JSON.stringify(tc.args, null, 2))}</pre>`;
                html += '</div>';
            }

            // Observation (collapsible for long content)
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

            // Thought (future: when react_step persists thought field)
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

// ============================================================================
// #181: MISSION REPORT PAGING & CONTEXT SELECTION
// ============================================================================

function formatBytes(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

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

    // Sync select-all state with current page's checkboxes
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

    // Render artifacts with checkboxes
    renderArtifactsWithCheckboxes(page.artifacts, index);

    // Render final response with checkbox
    renderFinalResponseWithCheckbox(page.finalResponse, index);
}

function renderArtifactsWithCheckboxes(artifacts, pageIndex) {
    artifactsOutputEl.innerHTML = '';

    if (!artifacts || Object.keys(artifacts).length === 0) {
        artifactsOutputEl.innerHTML = '<div class="placeholder">NO ARTIFACTS</div>';
        return;
    }

    for (const [key, value] of Object.entries(artifacts)) {
        // Skip internal/display-only artifacts
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

        // Add RENDER + SAVE buttons for HTML artifacts
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
        // #198: Use textContent to prevent HTML artifact CSS from bleeding into parent UI.
        // HTML artifacts have RENDER/SAVE buttons for viewing; display shows safe source text.
        const pre = document.createElement('pre');
        if (typeof value === 'object') {
            pre.textContent = JSON.stringify(value, null, 2);
        } else {
            pre.textContent = decodeHtmlEntities(String(value));
        }
        content.appendChild(pre);

        // Click label to toggle content visibility
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
    // Render the archive markdown normally first
    renderMissionReport(archive);

    // Prepend a checkbox row for context selection
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

function renderMissionReport(markdown) {
    if (!markdown) return;

    // Split by H2 headers (## )
    const sections = markdown.split(/^## /gm);

    // Clear existing content
    archiveSubtabsEl.innerHTML = '';
    archiveOutputEl.innerHTML = '';

    // Build all sections content with anchor IDs
    let allSectionsHtml = '';
    const navItems = [];

    sections.forEach((section, index) => {
        if (!section.trim()) return; // Skip empty sections

        // Extract title from first line
        const lines = section.split('\n');
        const title = lines.shift().trim();
        const content = lines.join('\n');

        if (!title) return;

        // Create a slug for the section anchor
        const sectionId = `section-${index}-${title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/-+$/, '')}`;

        // Build section HTML with anchor
        allSectionsHtml += `<div class="report-section" id="${sectionId}">`;
        allSectionsHtml += `<h2 class="section-header">${title}</h2>`;
        allSectionsHtml += marked.parse(content);
        allSectionsHtml += `</div>`;

        // Track nav item
        navItems.push({ title, sectionId });
    });

    // Render all sections in content area
    if (allSectionsHtml) {
        archiveOutputEl.innerHTML = allSectionsHtml;
    } else {
        // Fallback if no sections found - render the whole thing
        archiveOutputEl.innerHTML = marked.parse(markdown);
        return;
    }

    // Build vertical nav strip
    navItems.forEach((item, idx) => {
        const navBtn = document.createElement('button');
        navBtn.className = 'section-nav-btn';
        navBtn.textContent = item.title;
        navBtn.title = item.title; // Tooltip for truncated titles

        // First item starts active
        if (idx === 0) {
            navBtn.classList.add('active');
        }

        navBtn.onclick = () => {
            // Scroll to section
            const sectionEl = document.getElementById(item.sectionId);
            if (sectionEl) {
                sectionEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }

            // Update active state
            document.querySelectorAll('.section-nav-btn').forEach(b => b.classList.remove('active'));
            navBtn.classList.add('active');
        };

        archiveSubtabsEl.appendChild(navBtn);
    });

    // Update active nav on scroll (intersection observer)
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const sectionId = entry.target.id;
                const navItem = navItems.find(n => n.sectionId === sectionId);
                if (navItem) {
                    document.querySelectorAll('.section-nav-btn').forEach(b => b.classList.remove('active'));
                    const activeBtn = [...archiveSubtabsEl.children].find(btn => btn.textContent === navItem.title);
                    if (activeBtn) activeBtn.classList.add('active');
                }
            }
        });
    }, { root: archiveOutputEl, threshold: 0.3 });

    // Observe all sections
    document.querySelectorAll('.report-section').forEach(section => {
        observer.observe(section);
    });
}

function handleStreamEvent(event) {
    const now = Date.now();
    const latency = now - lastUpdateTime;
    // latencyEl.textContent = String(Math.min(latency, 999)).padStart(3, '0'); // Removed
    lastUpdateTime = now;

    // Handle AgUiEvent structure
    // event = { type, run_id, timestamp, source, data }

    if (event.run_id && !currentRunId) {
        currentRunId = event.run_id;
        logStatus(`► RUN ID: ${currentRunId}`);
        // startTracePolling(currentRunId); // Disabled in favor of Mission Report
    }

    const data = event.data || {};
    const source = event.source || 'system';

    // ADR-CORE-042: Handle raw interrupt events from _stream_formatter
    // These come as {interrupt: {...}, thread_id: "xxx"} without a type wrapper
    if (event.interrupt || data.interrupt) {
        const interruptData = event.interrupt || data.interrupt;
        pendingThreadId = event.thread_id || data.thread_id;

        // Build question display — handle both formats:
        //   Facilitator sends: {question: "...", reason: "...", action_type: "ask_user"}
        //   Future/DialogueSpecialist may send: {questions: [{question, reason}, ...]}
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
            // Single question from Facilitator ASK_USER action
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
        return; // Don't process further - wait for user input
    }

    switch (event.type) {
        case 'workflow_start':
            logStatus(`► WORKFLOW STARTED`);
            addThoughtStreamEntry('SYSTEM', 'Workflow initiated', 'lifecycle');
            break;

        case 'status_update':
            if (data.status) {
                logStatus(`► ${data.status}`);
                // Detect routing decisions in status updates
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
            // Specialist/Node is starting execution
            if (source) {
                addRoutingEntry(source);
                const displayName = source.replace(/_specialist$/, '').replace(/_/g, ' ');
                addThoughtStreamEntry(source, `${displayName} starting...`, 'lifecycle');
            }
            break;

        case 'node_end':
        case 'specialist_end':
            // Specialist/Node completed execution
            if (source) {
                const displayName = source.replace(/_specialist$/, '').replace(/_/g, ' ');
                addThoughtStreamEntry(source, `${displayName} complete`, 'success');

                // Extract thought process from scratchpad (generic pattern)
                if (data.scratchpad) {
                    // Check for triage recommendations
                    if (data.scratchpad.recommended_specialists && Array.isArray(data.scratchpad.recommended_specialists)) {
                        const recs = data.scratchpad.recommended_specialists;
                        const message = `Recommending: ${recs.join(', ')}`;
                        addThoughtStreamEntry('TRIAGE', message, 'reasoning', { collapsible: recs.length > 2 });
                    }

                    // Check for router_decision (routing event)
                    if (data.scratchpad.router_decision) {
                        const decision = data.scratchpad.router_decision;
                        // Use reasoning type with collapsible for long decisions
                        const isLong = decision.length > 80;
                        if (isLong) {
                            addThoughtStreamEntry('ROUTER', decision, 'reasoning', { collapsible: true });
                        } else {
                            addThoughtStreamEntry('ROUTER', decision, 'routing', { target: decision });
                        }
                    }

                    // Generic: display any key ending in _reasoning or _decision
                    Object.keys(data.scratchpad).forEach(key => {
                        if (key.endsWith('_reasoning')) {
                            const specialist = key.replace(/_reasoning$/, '').toUpperCase().replace(/_/g, ' ');
                            const value = String(data.scratchpad[key]);
                            // Use collapsible for long reasoning (> 100 chars or multiline)
                            const isLong = value.length > 100 || value.includes('\n');
                            if (isLong) {
                                addThoughtStreamEntry(specialist, value, 'reasoning', { collapsible: true });
                            } else {
                                addThoughtStreamEntry(specialist, value, 'reasoning');
                            }
                        } else if (key.endsWith('_decision') && key !== 'router_decision') {
                            // Non-router decisions as info
                            const specialist = key.replace(/_decision$/, '').toUpperCase().replace(/_/g, ' ');
                            addThoughtStreamEntry(specialist, data.scratchpad[key], 'info');
                        }
                    });

                    // Special case: facilitator_complete (boolean flag, not reasoning)
                    if (data.scratchpad.facilitator_complete) {
                        addThoughtStreamEntry('FACILITATOR', 'Context gathering complete', 'success');
                    }
                }

                // Update artifacts if present
                if (data.artifacts) {
                    updateArtifactsDisplay(data.artifacts);

                    // Add thought stream entry for each artifact
                    Object.keys(data.artifacts).forEach(key => {
                        // Skip archive_report.md from artifacts display (goes to Final Response)
                        if (key !== 'archive_report.md') {
                            addThoughtStreamEntry(source, key, 'artifact');
                        }
                    });
                }
            }
            break;

        case 'log':
            if (data.message) {
                // NOTE: Routing entries are added via node_start events, not logs
                // (to avoid duplicates since both events fire for each node)

                // Detect MCP calls in logs - add to thought stream with structured display
                if (data.message.includes('MCP') || data.message.includes('Facilitator: Executing action')) {
                    // Try to extract MCP call info - pattern: service.method(params)
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
            // Re-render with checkboxes now that the run is complete
            renderPage(currentPageIndex);
            break;

        case 'clarification_required':
            // ADR-CORE-042: Handle wrapped interrupt event (AgUiEvent type)
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
            // Accumulate snapshot in memory for intra-run paging
            stateSnapshots.push(data);
            // Auto-advance to latest snapshot during live run
            snapshotPageIndex = stateSnapshots.length - 1;
            renderSnapshot(snapshotPageIndex);
            updateSnapshotPagingControls();
            break;

        default:
            console.warn("Unknown event type:", event.type, event);
    }
}

function logStatus(msg) {
    systemStatusEl.textContent = msg;
}

// NOTE: renderMissionReport is defined earlier in the file (around line 410)
// This duplicate has been removed to fix ReferenceError with old variable names

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

// ============================================================================
// MERMAID GRAPH VISUALIZATION
// ============================================================================

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

            // Fetch and render topology if not already loaded
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
        mermaidGraphEl.innerHTML = `<div class="placeholder">Failed to load topology: ${error.message}</div>`;
    }
}

async function renderMermaidGraph(data) {
    if (!window.mermaid) {
        console.warn('Mermaid not loaded yet');
        mermaidGraphEl.innerHTML = '<div class="placeholder">Mermaid loading...</div>';
        return;
    }

    // Build Mermaid flowchart definition with LEFT-to-RIGHT for hub-spoke clarity
    let graphDef = 'flowchart LR\n';

    // Style classes - using CSS variables where possible
    graphDef += '    classDef router fill:#FF9F1C,stroke:#fff,stroke-width:3px,color:#1a1a2e,font-weight:bold\n';
    graphDef += '    classDef core fill:#2EC4B6,stroke:#fff,stroke-width:2px,color:#1a1a2e\n';
    graphDef += '    classDef specialist fill:#242442,stroke:#2EC4B6,stroke-width:1px,color:#FFECC2\n';
    graphDef += '    classDef terminal fill:#E74C3C,stroke:#fff,stroke-width:2px,color:#fff\n';

    // Group nodes by category for subgraph clustering
    const categoryNodes = {};
    const nodeIdMap = {};

    // Category display names and order (for cleaner subgraph labels)
    const CATEGORY_LABELS = {
        'orchestration': '🎯 ORCHESTRATION',
        'context': '📋 CONTEXT',
        'research': '🔍 RESEARCH',
        'chat': '💬 CHAT',
        'data': '📊 DATA',
        'files': '📁 FILES',
        'browser': '🌐 BROWSER',
        'builders': '🏗️ BUILDERS',
        'utilities': '🔧 UTILITIES',
        'core': '⚙️ CORE',
        'distillation': '🧪 DISTILLATION',
        'planning': '📐 PLANNING',
        'other': '📦 OTHER'
    };

    // Only include routable specialists + router + core infrastructure
    data.nodes.forEach(node => {
        // Skip MCP-only and non-routable specialists (except router and core)
        if (!node.is_graph_node) return;
        if (!node.is_routable && node.type !== 'router' && node.type !== 'core_infrastructure') return;

        const shortId = 'n_' + node.id.replace(/_specialist$/, '').replace(/_/g, '_');
        const displayName = node.id.replace(/_specialist$/, '').replace(/_/g, ' ').toUpperCase();
        nodeIdMap[node.id] = shortId;

        // Group by category
        const category = node.category || 'other';
        if (!categoryNodes[category]) {
            categoryNodes[category] = [];
        }
        categoryNodes[category].push({ shortId, displayName, node });
    });

    // Build subgraphs by category
    // Router goes in its own prominent position (not in a subgraph)
    const routerNode = categoryNodes['orchestration']?.find(n => n.node.type === 'router');
    if (routerNode) {
        graphDef += `    ${routerNode.shortId}[["🎯 ${routerNode.displayName}"]]:::router\n`;
        // Remove router from orchestration group
        categoryNodes['orchestration'] = categoryNodes['orchestration'].filter(n => n.node.type !== 'router');
    }

    // Define preferred category order for visual layout
    const categoryOrder = ['orchestration', 'context', 'research', 'chat', 'data', 'files', 'browser', 'builders', 'planning', 'utilities', 'distillation', 'core', 'other'];

    // Add subgraphs for each non-empty category
    categoryOrder.forEach(category => {
        const nodes = categoryNodes[category];
        if (!nodes || nodes.length === 0) return;

        const label = CATEGORY_LABELS[category] || category.toUpperCase();
        graphDef += `    subgraph ${category}["${label}"]\n`;

        nodes.forEach(({ shortId, displayName, node }) => {
            let nodeClass = 'specialist';
            if (node.type === 'core_infrastructure') nodeClass = 'core';

            // Use different shapes for visual distinction
            if (node.type === 'core_infrastructure') {
                graphDef += `        ${shortId}([${displayName}]):::${nodeClass}\n`;
            } else {
                graphDef += `        ${shortId}["${displayName}"]:::${nodeClass}\n`;
            }
        });

        graphDef += '    end\n';
    });

    // Add terminal END node (the final graph termination point)
    graphDef += '    n_end_terminal((END)):::terminal\n';
    nodeIdMap['__end__'] = 'n_end_terminal';

    // Add edges: Router -> specialists (conditional routing)
    const routerEdges = data.edges.filter(e => e.type === 'conditional');
    routerEdges.forEach(edge => {
        const sourceId = nodeIdMap[edge.source];
        const targetId = nodeIdMap[edge.target];
        if (sourceId && targetId) {
            graphDef += `    ${sourceId} --> ${targetId}\n`;
        }
    });

    // Simplified: Show end_specialist -> END terminal edge
    // (Skip the cluttered completion edges back to router for cleaner visualization)
    // Note: end_specialist maps to 'n_end' (from the ID sanitization)
    graphDef += '    n_end -.-> n_end_terminal\n';

    // Render the graph
    try {
        mermaidRenderCount++;
        const { svg } = await window.mermaid.render(`mermaid-graph-${mermaidRenderCount}`, graphDef);
        mermaidGraphEl.innerHTML = svg;
    } catch (error) {
        console.error('Mermaid render error:', error);
        console.error('Graph definition:', graphDef);
        mermaidGraphEl.innerHTML = `<div class="placeholder">Graph render error: ${error.message}</div>`;
    }
}

function highlightMermaidNode(nodeName) {
    // Try to find and highlight the active node in the Mermaid SVG
    // Must match the 'n_' prefix used in renderMermaidGraph
    const shortId = 'n_' + nodeName.replace(/_specialist$/, '').replace(/_/g, '_');

    // Remove previous highlights
    mermaidGraphEl.querySelectorAll('.node').forEach(node => {
        node.classList.remove('active');
    });

    // Find and highlight the matching node
    // Mermaid generates nodes with id like "flowchart-shortId-0"
    const nodeEl = mermaidGraphEl.querySelector(`[id*="${shortId}"]`);
    if (nodeEl) {
        const nodeGroup = nodeEl.closest('.node') || nodeEl;
        nodeGroup.classList.add('active');
    }
}

// Add Copy/Fullscreen Toolbars after rendering
const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
        if (mutation.addedNodes.length) {
            addToolbarsToPreBlocks();
        }
    });
});

// Observe both archive output (Final Response tab) and JSON output for code block toolbars
observer.observe(archiveOutputEl, { childList: true, subtree: true });
observer.observe(jsonOutputEl.parentElement, { childList: true, subtree: true }); // Observe tab-json content

function addToolbarsToPreBlocks() {
    document.querySelectorAll('pre').forEach(pre => {
        if (pre.querySelector('.code-toolbar')) return; // Already added

        const toolbar = document.createElement('div');
        toolbar.className = 'code-toolbar';

        // Get the raw content (without toolbar button text)
        const getCleanContent = () => {
            const clone = pre.cloneNode(true);
            const toolbarClone = clone.querySelector('.code-toolbar');
            if (toolbarClone) toolbarClone.remove();
            return clone.textContent.trim();
        };

        const copyBtn = document.createElement('button');
        copyBtn.className = 'toolbar-btn';
        copyBtn.textContent = 'COPY';
        copyBtn.onclick = () => {
            navigator.clipboard.writeText(getCleanContent());
            copyBtn.textContent = 'COPIED!';
            setTimeout(() => copyBtn.textContent = 'COPY', 2000);
        };

        const fullBtn = document.createElement('button');
        fullBtn.className = 'toolbar-btn';
        fullBtn.textContent = 'FULLSCREEN';
        fullBtn.onclick = () => {
            modalBody.innerHTML = `<pre>${pre.innerHTML}</pre>`;
            // Re-add toolbars to the modal content
            setTimeout(addToolbarsToPreBlocks, 100);
            zoomModal.style.display = 'block';
        };

        toolbar.appendChild(copyBtn);
        toolbar.appendChild(fullBtn);

        // Check if this is HTML content - add RENDER button
        // Look for .html in preceding h3, or detect HTML content
        let isHtml = false;
        const prevH3 = pre.previousElementSibling;
        if (prevH3 && prevH3.tagName === 'H3' && prevH3.textContent.includes('.html')) {
            isHtml = true;
        }
        // Also detect by content (escaped or unescaped)
        const content = pre.textContent.trim();
        if (content.startsWith('<!DOCTYPE') || content.startsWith('<html') ||
            content.startsWith('&lt;!DOCTYPE') || content.startsWith('&lt;html')) {
            isHtml = true;
        }

        if (isHtml) {
            const renderBtn = document.createElement('button');
            renderBtn.className = 'toolbar-btn';
            renderBtn.textContent = 'RENDER';
            renderBtn.onclick = () => {
                // Unescape HTML entities (content is escaped for safe display)
                let htmlContent = getCleanContent();
                const textarea = document.createElement('textarea');
                textarea.innerHTML = htmlContent;
                htmlContent = textarea.value;

                const blob = new Blob([htmlContent], { type: 'text/html' });
                const url = URL.createObjectURL(blob);
                window.open(url, '_blank');
            };
            toolbar.appendChild(renderBtn);

            const saveBtn = document.createElement('button');
            saveBtn.className = 'toolbar-btn';
            saveBtn.textContent = 'SAVE';
            saveBtn.onclick = () => {
                let htmlContent = getCleanContent();
                const ta = document.createElement('textarea');
                ta.innerHTML = htmlContent;
                htmlContent = ta.value;

                const blob = new Blob([htmlContent], { type: 'text/html' });
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = 'artifact.html';
                a.click();
                URL.revokeObjectURL(a.href);
            };
            toolbar.appendChild(saveBtn);
        }

        pre.appendChild(toolbar);
    });
}

function startTracePolling(runId) {
    if (tracePollInterval) clearInterval(tracePollInterval);
    
    // Poll every 2 seconds
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
    // Simple tree rendering
    // Sort by start_time
    runs.sort((a, b) => new Date(a.start_time) - new Date(b.start_time));
    
    // DEPRECATED: executionTraceEl no longer exists - this function is disabled
    // executionTraceEl.innerHTML = '';
    return; // Exit early since this function is deprecated
    
    // Build a map for hierarchy
    const runMap = {};
    const rootRuns = [];
    
    runs.forEach(run => {
        run.children = [];
        runMap[run.id] = run;
    });
    
    runs.forEach(run => {
        if (run.parent_run_id && runMap[run.parent_run_id]) {
            runMap[run.parent_run_id].children.push(run);
        } else {
            rootRuns.push(run);
        }
    });

    function createTraceNode(run) {
        const div = document.createElement('div');
        div.className = 'trace-node';
        
        const header = document.createElement('div');
        header.className = 'trace-header';
        const duration = run.end_time ? ((new Date(run.end_time) - new Date(run.start_time)) / 1000).toFixed(2) + 's' : 'running...';
        header.innerHTML = `<span class="trace-type">[${run.run_type}]</span> ${run.name} (${duration})`;
        
        const details = document.createElement('div');
        details.className = 'trace-details';
        // Show inputs/outputs if available
        const inputs = JSON.stringify(run.inputs).slice(0, 100);
        const outputs = run.outputs ? JSON.stringify(run.outputs).slice(0, 100) : '...';
        details.innerHTML = `<div>IN: ${inputs}...</div><div>OUT: ${outputs}...</div>`;
        
        header.onclick = () => div.classList.toggle('expanded');
        
        div.appendChild(header);
        div.appendChild(details);
        
        if (run.children.length > 0) {
            run.children.forEach(child => {
                div.appendChild(createTraceNode(child));
            });
        }
        
        return div;
    }

    // DEPRECATED: This code is unreachable due to early return above
    rootRuns.forEach(run => {
        // executionTraceEl.appendChild(createTraceNode(run));
    });
}
