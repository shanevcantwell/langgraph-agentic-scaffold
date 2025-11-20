const API_BASE = '/v1'; // Proxied by server.js

// DOM Elements
const promptInput = document.getElementById('promptInput');
const executeBtn = document.getElementById('executeBtn');
const cancelBtn = document.getElementById('cancelBtn');
const simpleChatMode = document.getElementById('simpleChatMode');
// const turnCountEl = document.getElementById('turnCount'); // Removed
// const latencyEl = document.getElementById('latency'); // Removed
const routingLogEl = document.getElementById('routingLog');
const systemStatusEl = document.getElementById('systemStatus');
const traceTabsEl = document.getElementById('traceTabs');
const executionTraceEl = document.getElementById('executionTrace');
const jsonOutputEl = document.getElementById('jsonOutput');

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

// Artifact Tabs
const tabBtns = document.querySelectorAll('.artifacts-panel .tab-btn');
const tabContents = document.querySelectorAll('.artifacts-panel .tab-content');

// State
let currentRunId = null;
let tracePollInterval = null;
let turnCount = 0;
let startTime = 0;
let lastUpdateTime = 0;
let loadedFile = null; // { content: string, type: 'text' | 'image' }
let abortController = null; // Controller for the fetch request

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
    if (e.key === 'Enter' && e.shiftKey) {
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
    
    // Check if image
    if (file.type.startsWith('image/')) {
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
    executionTraceEl.innerHTML = '<div class="placeholder">WAITING FOR MISSION DATA...</div>';
    traceTabsEl.innerHTML = '';
    jsonOutputEl.textContent = '{}';
    document.getElementById('archiveOutput').innerHTML = '';
    
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
            payload.image_to_process = loadedFile.content;
            logStatus(`► INJECTING IMAGE DATA...`);
        } else {
            payload.text_to_process = loadedFile.content;
            logStatus(`► INJECTING TEXT DATA...`);
        }
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
        promptInput.value = '';
        promptInput.focus();
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

    switch (event.type) {
        case 'workflow_start':
            logStatus(`► WORKFLOW STARTED`);
            break;

        case 'status_update':
            if (data.status) {
                logStatus(`► ${data.status}`);
            }
            break;

        case 'log':
            if (data.message) {
                // Check for routing info in logs (legacy support or explicit log)
                if (data.message.includes('Entering node:')) {
                    const node = data.message.split('Entering node:')[1].trim();
                    addRoutingEntry(node);
                }
            }
            break;

        case 'error':
            logStatus(`❌ ERROR: ${data.error}`);
            if (data.error_report) {
                renderMissionReport(`## ❌ Error Report\n\n${data.error_report}`);
            }
            break;

        case 'workflow_end':
            logStatus(`► WORKFLOW COMPLETE`);
            
            if (data.final_state) {
                jsonOutputEl.textContent = JSON.stringify(data.final_state, null, 2);
            }

            // Removed legacy HTML rendering
            // if (data.html) { ... }

            if (data.archive) {
                renderMissionReport(data.archive);
                // Also render to the Artifacts panel if needed, but Mission Report panel is primary now.
                // If we want it in the Artifacts panel too:
                document.getElementById('archiveOutput').innerHTML = marked.parse(data.archive);
            }
            break;
            
        default:
            console.warn("Unknown event type:", event.type, event);
    }
}

function logStatus(msg) {
    systemStatusEl.textContent = msg;
}

function renderMissionReport(markdown) {
    if (!markdown) return;

    // Split by H2 headers (## )
    // We use a regex that matches the start of a line, ##, space, and captures the title
    const sections = markdown.split(/^## /gm);
    
    traceTabsEl.innerHTML = '';
    executionTraceEl.innerHTML = '';

    let firstTabBtn = null;

    sections.forEach((section, index) => {
        if (!section.trim()) return; // Skip empty sections (often the first split if file starts with ##)

        // The split consumes the "## ", so we need to extract the title from the first line
        const lines = section.split('\n');
        const title = lines.shift().trim();
        const content = lines.join('\n');

        if (!title) return;

        const btn = document.createElement('button');
        btn.className = 'tab-btn';
        btn.textContent = title;
        
        btn.onclick = () => {
            // Deactivate all
            document.querySelectorAll('#traceTabs .tab-btn').forEach(b => b.classList.remove('active'));
            // Activate this
            btn.classList.add('active');
            // Render content
            executionTraceEl.innerHTML = marked.parse(content);
        };

        traceTabsEl.appendChild(btn);

        if (!firstTabBtn) {
            firstTabBtn = btn;
        }
    });

    // Activate first tab by default
    if (firstTabBtn) {
        firstTabBtn.click();
    } else {
        // Fallback if no sections found
        executionTraceEl.innerHTML = marked.parse(markdown);
    }
}

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
}

// Add Copy/Fullscreen Toolbars after rendering
const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
        if (mutation.addedNodes.length) {
            addToolbarsToPreBlocks();
        }
    });
});

observer.observe(executionTraceEl, { childList: true, subtree: true });
observer.observe(jsonOutputEl.parentElement, { childList: true, subtree: true }); // Observe tab-json content

function addToolbarsToPreBlocks() {
    document.querySelectorAll('pre').forEach(pre => {
        if (pre.querySelector('.code-toolbar')) return; // Already added

        const toolbar = document.createElement('div');
        toolbar.className = 'code-toolbar';

        const copyBtn = document.createElement('button');
        copyBtn.className = 'toolbar-btn';
        copyBtn.textContent = 'COPY';
        copyBtn.onclick = () => {
            navigator.clipboard.writeText(pre.textContent.replace('COPYFULLSCREEN', '').trim());
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
    
    executionTraceEl.innerHTML = '';
    
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

    rootRuns.forEach(run => {
        executionTraceEl.appendChild(createTraceNode(run));
    });
}
