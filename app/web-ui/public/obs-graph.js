// =============================================================================
// V.E.G.A.S. TERMINAL — Mermaid Graph Visualization
// Neural Grid graph/grid toggle and topology rendering.
// =============================================================================

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
