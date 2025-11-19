const API_BASE = '/v1'; // Proxied by server.js

// DOM Elements
const promptInput = document.getElementById('promptInput');
const executeBtn = document.getElementById('executeBtn');
const simpleChatMode = document.getElementById('simpleChatMode');
const turnCountEl = document.getElementById('turnCount');
const latencyEl = document.getElementById('latency');
const routingLogEl = document.getElementById('routingLog');
const systemStatusEl = document.getElementById('systemStatus');
const executionTraceEl = document.getElementById('executionTrace');
const jsonOutputEl = document.getElementById('jsonOutput');
const archiveOutputEl = document.getElementById('archiveOutput');
const tabBtns = document.querySelectorAll('.tab-btn');
const tabContents = document.querySelectorAll('.tab-content');

// File Upload Elements
const fileInput = document.getElementById('fileInput');
const uploadBtn = document.getElementById('uploadBtn');
const clearFileBtn = document.getElementById('clearFileBtn');
const fileNameEl = document.getElementById('fileName');

// Zoom Modal Elements
const zoomBtn = document.getElementById('zoomBtn');
const zoomModal = document.getElementById('zoomModal');
const closeModal = document.querySelector('.close-modal');
const modalBody = document.getElementById('modal-body');

// State
let currentRunId = null;
let tracePollInterval = null;
let turnCount = 0;
let startTime = 0;
let lastUpdateTime = 0;
let loadedFile = null; // { content: string, type: 'text' | 'image' }

// Event Listeners
executeBtn.addEventListener('click', executeWorkflow);
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
zoomBtn.addEventListener('click', () => {
    modalBody.innerHTML = archiveOutputEl.innerHTML;
    zoomModal.style.display = 'block';
});

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
    systemStatusEl.innerHTML = '<div class="status-line">► INITIALIZING...</div>';
    routingLogEl.innerHTML = '';
    executionTraceEl.innerHTML = '';
    jsonOutputEl.textContent = '{}';
    archiveOutputEl.innerHTML = '';
    document.getElementById('tab-html').innerHTML = '<div class="placeholder">PROCESSING...</div>';
    
    turnCount++;
    turnCountEl.textContent = String(turnCount).padStart(3, '0');
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

    try {
        const response = await fetch(`${API_BASE}/graph/stream/events`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

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
        logStatus(`❌ ERROR: ${error.message}`);
    } finally {
        promptInput.disabled = false;
        executeBtn.disabled = false;
        promptInput.value = '';
        promptInput.focus();
        stopTracePolling();
        
        // Clear file after send? Maybe keep it? Let's keep it for now, user can clear manually.
    }
}

function handleStreamEvent(event) {
    const now = Date.now();
    const latency = now - lastUpdateTime;
    latencyEl.textContent = String(Math.min(latency, 999)).padStart(3, '0');
    lastUpdateTime = now;

    // Handle AgUiEvent structure
    // event = { type, run_id, timestamp, source, data }

    if (event.run_id && !currentRunId) {
        currentRunId = event.run_id;
        logStatus(`► RUN ID: ${currentRunId}`);
        startTracePolling(currentRunId);
    }

    const data = event.data || {};

    switch (event.type) {
        case 'workflow_start':
            logStatus(`► WORKFLOW STARTED`);
            break;

        case 'status':
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
                archiveOutputEl.innerHTML = `<h2>❌ Error Report</h2><pre>${data.error_report}</pre>`;
                document.querySelector('[data-tab="archive"]').click();
            }
            break;

        case 'workflow_end':
            logStatus(`► WORKFLOW COMPLETE`);
            
            if (data.final_state) {
                jsonOutputEl.textContent = JSON.stringify(data.final_state, null, 2);
            }

            if (data.html) {
                const iframe = document.createElement('iframe');
                iframe.srcdoc = data.html;
                document.getElementById('tab-html').innerHTML = '';
                document.getElementById('tab-html').appendChild(iframe);
            }

            if (data.archive) {
                archiveOutputEl.innerHTML = marked.parse(data.archive);
            }
            break;
            
        default:
            console.warn("Unknown event type:", event.type, event);
    }
}

function logStatus(msg) {
    const div = document.createElement('div');
    div.className = 'status-line';
    div.textContent = msg;
    systemStatusEl.appendChild(div);
    systemStatusEl.scrollTop = systemStatusEl.scrollHeight;
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
