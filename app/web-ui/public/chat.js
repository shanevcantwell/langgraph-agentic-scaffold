// =============================================================================
// V.E.G.A.S. TERMINAL — Chat Input Layer
//
// This file loads LAST (after app.js and observability.js). It defines:
//   - Workflow execution (executeWorkflow)
//   - Abort handling (handleAbort)
//   - Clarification submission (submitClarification)
//   - File upload logic
//   - All chat-related event listeners
//
// All functions reference globals from app.js and call into
// observability functions (handleStreamEvent, logStatus, etc.)
//
// When this file is removed (ADR-UI-003 WS2 Step 5), V.E.G.A.S.
// becomes a pure observability dashboard. No server changes needed.
//
// Load order: app.js → observability.js → chat.js
// =============================================================================


// =============================================================================
// FILE UPLOAD
// =============================================================================

uploadBtn.addEventListener('click', () => fileInput.click());

fileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();

    if (file.type.startsWith('image/')) {
        if (file.type !== 'image/png') {
            logStatus(`⚠ Only PNG images are currently supported. Got: ${file.type}`);
            fileInput.value = '';
            return;
        }
        reader.onload = (e) => {
            loadedFile = {
                content: e.target.result,
                type: 'image'
            };
            updateFileUI(file.name);
        };
        reader.readAsDataURL(file);
    } else {
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


// =============================================================================
// CLARIFICATION (ADR-CORE-042)
// =============================================================================

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
    logStatus('► RESUMING WITH CLARIFICATION...');
    addThoughtStreamEntry('USER', userInput, 'info');

    try {
        const response = await fetch(`${API_BASE}/graph/resume`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                thread_id: pendingThreadId,
                user_input: userInput
            })
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        // Process the resumed SSE stream (same format as initial stream)
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
                        console.error("Error parsing resume SSE:", e, line);
                    }
                }
            }
        }

    } catch (error) {
        logStatus(`❌ RESUME ERROR: ${error.message}`);
        addThoughtStreamEntry('SYSTEM', `Resume failed: ${error.message}`, 'error');
    }
}


// =============================================================================
// WORKFLOW EXECUTION
// =============================================================================

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
    startTime = Date.now();
    lastUpdateTime = startTime;

    // Prepare Payload
    const payload = {
        input_prompt: prompt,
        use_simple_chat: simpleChatMode.checked
    };

    if (loadedFile) {
        if (loadedFile.type === 'image') {
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
                role: 'user',
                content: `[Prior Run Context — ${ts}]\n\n${parts.join('\n\n')}`
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
    const CONNECTION_TIMEOUT_MS = 15000;

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
            buffer = lines.pop();

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
        clearTimeout(timeoutId);

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

        stopTracePolling();
        stopProgressPolling();
        abortController = null;
    }
}


// =============================================================================
// ABORT
// =============================================================================

async function handleAbort() {
    if (abortController) {
        abortController.abort();
    }

    if (currentRunId) {
        cancelBtn.disabled = true;
        cancelBtn.textContent = 'ABORTING...';
        try {
            await fetch(`${API_BASE}/graph/cancel/${currentRunId}`, {
                method: 'POST'
            });
            logStatus('► ABORT SIGNAL SENT');
        } catch (e) {
            console.error("Error sending cancel request:", e);
        }
    }
}


// =============================================================================
// EVENT LISTENERS — Chat input wiring
// =============================================================================

executeBtn.addEventListener('click', executeWorkflow);
cancelBtn.addEventListener('click', handleAbort);
promptInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        executeWorkflow();
    }
});
