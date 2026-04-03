// =============================================================================
// V.E.G.A.S. TERMINAL — Shared State, DOM Refs, Utilities
//
// This file loads FIRST. It defines:
//   - API base URL
//   - All DOM element references (shared by observability.js and chat.js)
//   - Global state variables
//   - Utility functions (formatTimestamp, escapeHtml, decodeHtmlEntities, formatBytes)
//   - Theme switching
//   - Config refresh
//   - Tab/modal UI wiring
//   - Session storage restoration
//
// Load order: app.js → observability.js → chat.js
// =============================================================================

const API_BASE = '/v1'; // Proxied by server.js

// --- DOM Elements ---
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
const zoomModal = document.getElementById('zoomModal');
const closeModal = document.querySelector('.close-modal');
const modalBody = document.getElementById('modal-body');

// Mission Report Tabs (consolidated)
const tabBtns = document.querySelectorAll('.trace-panel .tab-btn');
const tabContents = document.querySelectorAll('.trace-panel .tab-content');

// --- Global State ---
let currentRunId = null;
let tracePollInterval = null;
let turnCount = 0;
let startTime = 0;
let lastUpdateTime = 0;
let loadedFile = null; // { content: string, type: 'text' | 'image' }
let abortController = null; // Controller for the fetch request
let thoughtStreamEntries = []; // Track thought stream entries
let currentArtifacts = {}; // Track artifacts as they're generated
let progressIntervals = new Map(); // run_id → intervalId for multi-run progress polling

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

// #267: Headless mode state
const headlessModeCheckbox = document.getElementById('headlessMode');
const headlessStatusEl = document.getElementById('headlessStatus');
let headlessPollInterval = null;
let headlessEventSource = null;  // Tracks the active headless SSE connection

// ADR-CORE-042: Clarification state and DOM refs
let pendingThreadId = null;
const clarificationModal = document.getElementById('clarificationModal');
const clarificationQuestions = document.getElementById('clarificationQuestions');
const clarificationInput = document.getElementById('clarificationInput');
const clarificationSubmitBtn = document.getElementById('clarificationSubmitBtn');


// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================

function formatTimestamp() {
    const now = new Date();
    return `[${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}]`;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
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

function formatBytes(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}


// =============================================================================
// THEME SWITCHING
// =============================================================================

const themeBtns = document.querySelectorAll('.theme-btn[data-theme]');

const savedTheme = localStorage.getItem('theme') || 'light';
setTheme(savedTheme);

themeBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        const theme = btn.dataset.theme;
        setTheme(theme);
    });
});

function setTheme(theme) {
    if (theme === 'light') {
        document.documentElement.removeAttribute('data-theme');
    } else {
        document.documentElement.setAttribute('data-theme', theme);
    }

    themeBtns.forEach(btn => {
        if (btn.dataset.theme === theme) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });

    localStorage.setItem('theme', theme);
}


// =============================================================================
// CONFIG REFRESH
// =============================================================================

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


// =============================================================================
// TAB / MODAL UI WIRING
// =============================================================================

// Zoom modal close
closeModal.addEventListener('click', () => {
    zoomModal.style.display = 'none';
});

window.addEventListener('click', (e) => {
    if (e.target == zoomModal) {
        zoomModal.style.display = 'none';
    }
});

// Mission Report tabs
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


// =============================================================================
// SESSION STORAGE RESTORATION
// =============================================================================

// Restore run history from sessionStorage on page load
try {
    const saved = sessionStorage.getItem('runHistory');
    if (saved) {
        runHistory = JSON.parse(saved);
        if (runHistory.length > 0) {
            currentPageIndex = runHistory.length - 1;
            // updatePagingControls() called after observability.js loads
        }
    }
} catch (e) {
    console.warn('Failed to restore run history:', e);
}
