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

// State
let currentRunId = null;
let tracePollInterval = null;
let turnCount = 0;
let startTime = 0;
let lastUpdateTime = 0;

// Event Listeners
executeBtn.addEventListener('click', executeWorkflow);
promptInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        executeWorkflow();
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

    try {
        const response = await fetch(`${API_BASE}/graph/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                input_prompt: prompt,
                use_simple_chat: simpleChatMode.checked
            })
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            
            const chunk = decoder.decode(value);
            const lines = chunk.split('\n\n');
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = JSON.parse(line.slice(6));
                    handleStreamEvent(data);
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
    }
}

function handleStreamEvent(data) {
    const now = Date.now();
    const latency = now - lastUpdateTime;
    latencyEl.textContent = String(Math.min(latency, 999)).padStart(3, '0');
    lastUpdateTime = now;

    if (data.run_id) {
        currentRunId = data.run_id;
        logStatus(`► RUN ID: ${currentRunId}`);
        startTracePolling(currentRunId);
    }

    if (data.status) {
        logStatus(`► ${data.status}`);
    }

    if (data.logs) {
        if (data.logs.includes('Entering node:')) {
            const node = data.logs.split('Entering node:')[1].trim();
            addRoutingEntry(node);
        }
    }

    if (data.final_state) {
        jsonOutputEl.textContent = JSON.stringify(data.final_state, null, 2);
        
        if (data.html) {
            const iframe = document.createElement('iframe');
            iframe.srcdoc = data.html;
            document.getElementById('tab-html').innerHTML = '';
            document.getElementById('tab-html').appendChild(iframe);
            // Switch to HTML tab automatically if content exists
            document.querySelector('[data-tab="html"]').click();
        }

        if (data.archive) {
            archiveOutputEl.innerHTML = marked.parse(data.archive);
        }
    }

    if (data.error) {
        logStatus(`❌ ERROR: ${data.error}`);
        if (data.error_report) {
            archiveOutputEl.innerHTML = `<h2>❌ Error Report</h2><pre>${data.error_report}</pre>`;
            document.querySelector('[data-tab="archive"]').click();
        }
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
