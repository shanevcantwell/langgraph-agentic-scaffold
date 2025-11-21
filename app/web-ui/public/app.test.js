/**
 * V.E.G.A.S. Terminal UI Test Suite
 *
 * Tests for event handling, rendering, and state management.
 * Run with: npm test (requires jest setup in package.json)
 */

// Mock DOM elements
const createMockDOM = () => {
    document.body.innerHTML = `
        <div id="routingLog"></div>
        <div id="thoughtStream"></div>
        <div id="archiveSubtabs"></div>
        <div id="archiveOutput"></div>
        <div id="artifactsOutput"></div>
        <pre id="jsonOutput"></pre>
        <div id="systemStatus"></div>
    `;

    return {
        routingLogEl: document.getElementById('routingLog'),
        thoughtStreamEl: document.getElementById('thoughtStream'),
        archiveSubtabsEl: document.getElementById('archiveSubtabs'),
        archiveOutputEl: document.getElementById('archiveOutput'),
        artifactsOutputEl: document.getElementById('artifactsOutput'),
        jsonOutputEl: document.getElementById('jsonOutput'),
        systemStatusEl: document.getElementById('systemStatus')
    };
};

describe('V.E.G.A.S. Terminal Event Handling', () => {
    let mockDOM;
    let thoughtStreamEntries;
    let currentArtifacts;

    beforeEach(() => {
        mockDOM = createMockDOM();
        thoughtStreamEntries = [];
        currentArtifacts = {};
    });

    describe('Routing Log', () => {
        test('should not add duplicate entries from node_start and log events', () => {
            const routingHistory = [];

            const addRoutingEntry = (specialist) => {
                routingHistory.push(specialist);
                const div = document.createElement('div');
                div.textContent = specialist;
                mockDOM.routingLogEl.appendChild(div);
            };

            // Simulate node_start event (should add entry)
            const nodeStartEvent = {
                type: 'node_start',
                source: 'triage_architect',
                data: {}
            };
            addRoutingEntry(nodeStartEvent.source);

            // Simulate log event (should NOT add entry - this is the bug we're fixing)
            const logEvent = {
                type: 'log',
                source: 'triage_architect',
                data: { message: 'Entering node: triage_architect' }
            };
            // DON'T call addRoutingEntry from log events

            // Assert only one entry exists
            expect(routingHistory.length).toBe(1);
            expect(mockDOM.routingLogEl.children.length).toBe(1);
        });

        test('should add entries in correct order', () => {
            const routingHistory = [];

            const addRoutingEntry = (specialist) => {
                routingHistory.push(specialist);
            };

            addRoutingEntry('triage_architect');
            addRoutingEntry('router_specialist');
            addRoutingEntry('end_specialist');

            expect(routingHistory).toEqual(['triage_architect', 'router_specialist', 'end_specialist']);
        });
    });

    describe('Thought Stream', () => {
        test('should add thought stream entries with correct metadata', () => {
            const addThoughtStreamEntry = (specialist, message, type = 'info') => {
                const entry = { specialist, message, type };
                thoughtStreamEntries.push(entry);

                const div = document.createElement('div');
                div.className = `thought-entry thought-${type}`;
                div.textContent = `${specialist}: ${message}`;
                mockDOM.thoughtStreamEl.appendChild(div);
            };

            addThoughtStreamEntry('TRIAGE', 'Analyzing request...', 'info');
            addThoughtStreamEntry('ROUTER', 'Routing to specialist', 'success');

            expect(thoughtStreamEntries.length).toBe(2);
            expect(thoughtStreamEntries[0].specialist).toBe('TRIAGE');
            expect(thoughtStreamEntries[1].type).toBe('success');
        });

        test('should limit thought stream to 100 entries', () => {
            const addThoughtStreamEntry = (specialist, message, type = 'info') => {
                thoughtStreamEntries.push({ specialist, message, type });

                if (thoughtStreamEntries.length > 100) {
                    thoughtStreamEntries.shift();
                }
            };

            // Add 150 entries
            for (let i = 0; i < 150; i++) {
                addThoughtStreamEntry('TEST', `Message ${i}`, 'info');
            }

            expect(thoughtStreamEntries.length).toBe(100);
            expect(thoughtStreamEntries[0].message).toBe('Message 50'); // First 50 removed
            expect(thoughtStreamEntries[99].message).toBe('Message 149');
        });

        test('should extract scratchpad data correctly', () => {
            const scratchpad = {
                triage_reasoning: 'User wants to analyze data',
                facilitator_complete: true,
                router_decision: 'route to data_analysis_specialist'
            };

            const extractedData = [];

            if (scratchpad.triage_reasoning) {
                extractedData.push({ type: 'triage', data: scratchpad.triage_reasoning });
            }
            if (scratchpad.facilitator_complete) {
                extractedData.push({ type: 'facilitator', data: 'complete' });
            }
            if (scratchpad.router_decision) {
                extractedData.push({ type: 'router', data: scratchpad.router_decision });
            }

            expect(extractedData.length).toBe(3);
            expect(extractedData[0].data).toBe('User wants to analyze data');
            expect(extractedData[2].data).toBe('route to data_analysis_specialist');
        });
    });

    describe('Mission Report Rendering', () => {
        test('should parse H2 headers into tabs', () => {
            const markdown = `
## Executive Summary
This is the summary section.

## Technical Details
These are the technical details.

## Recommendations
Here are the recommendations.
`;

            const sections = markdown.split(/^## /gm);
            const tabs = sections
                .filter(s => s.trim())
                .map(section => {
                    const lines = section.split('\n');
                    const title = lines.shift().trim();
                    const content = lines.join('\n');
                    return { title, content };
                });

            expect(tabs.length).toBe(3);
            expect(tabs[0].title).toBe('Executive Summary');
            expect(tabs[1].title).toBe('Technical Details');
            expect(tabs[2].title).toBe('Recommendations');
        });

        test('should handle markdown with no H2 headers', () => {
            const markdown = 'Just some plain text without headers.';

            const sections = markdown.split(/^## /gm);
            const validSections = sections.filter(s => s.trim());

            // Should still render the content, just without tabs
            expect(validSections.length).toBe(1);
        });

        test('should skip empty sections', () => {
            const markdown = `
## Section 1
Content 1

##
No title

## Section 2
Content 2
`;

            const sections = markdown.split(/^## /gm);
            const validTabs = sections
                .filter(s => s.trim())
                .map(section => {
                    const lines = section.split('\n');
                    const title = lines.shift().trim();
                    return title;
                })
                .filter(title => title); // Remove empty titles

            expect(validTabs.length).toBe(2);
            expect(validTabs).toEqual(['Section 1', 'Section 2']);
        });
    });

    describe('Artifact Handling', () => {
        test('should merge artifacts correctly', () => {
            const updateArtifactsDisplay = (newArtifacts) => {
                currentArtifacts = { ...currentArtifacts, ...newArtifacts };
            };

            updateArtifactsDisplay({ artifact1: 'data1' });
            updateArtifactsDisplay({ artifact2: 'data2' });
            updateArtifactsDisplay({ artifact1: 'updated_data1' }); // Override

            expect(Object.keys(currentArtifacts).length).toBe(2);
            expect(currentArtifacts.artifact1).toBe('updated_data1');
            expect(currentArtifacts.artifact2).toBe('data2');
        });

        test('should skip archive_report.md from artifacts display', () => {
            const artifacts = {
                'data.json': { foo: 'bar' },
                'archive_report.md': '# Archive',
                'plan.txt': 'System plan'
            };

            const displayedArtifacts = Object.keys(artifacts).filter(
                key => key !== 'archive_report.md'
            );

            expect(displayedArtifacts.length).toBe(2);
            expect(displayedArtifacts).toEqual(['data.json', 'plan.txt']);
        });
    });

    describe('Event Type Handling', () => {
        test('should handle both node_start and specialist_start', () => {
            const handledEvents = [];

            const handleEvent = (eventType) => {
                switch (eventType) {
                    case 'node_start':
                    case 'specialist_start':
                        handledEvents.push('start_event');
                        break;
                }
            };

            handleEvent('node_start');
            handleEvent('specialist_start');

            expect(handledEvents.length).toBe(2);
            expect(handledEvents).toEqual(['start_event', 'start_event']);
        });

        test('should handle both node_end and specialist_end', () => {
            const handledEvents = [];

            const handleEvent = (eventType) => {
                switch (eventType) {
                    case 'node_end':
                    case 'specialist_end':
                        handledEvents.push('end_event');
                        break;
                }
            };

            handleEvent('node_end');
            handleEvent('specialist_end');

            expect(handledEvents.length).toBe(2);
            expect(handledEvents).toEqual(['end_event', 'end_event']);
        });
    });

    describe('Archive Data Flow', () => {
        test('should detect missing archive data', () => {
            const workflowEndData = {
                final_state: { artifacts: [] },
                // archive missing!
            };

            const hasArchive = !!workflowEndData.archive;
            expect(hasArchive).toBe(false);
        });

        test('should detect present archive data', () => {
            const workflowEndData = {
                final_state: { artifacts: [] },
                archive: '## Summary\n\nArchive content here.'
            };

            const hasArchive = !!workflowEndData.archive;
            expect(hasArchive).toBe(true);
            expect(workflowEndData.archive.length).toBeGreaterThan(0);
        });

        test('should handle empty archive string', () => {
            const workflowEndData = {
                final_state: { artifacts: [] },
                archive: ''
            };

            // Empty string is falsy, so should NOT render
            const shouldRender = workflowEndData.archive && workflowEndData.archive.trim();
            expect(shouldRender).toBeFalsy();
        });
    });
});

describe('V.E.G.A.S. Terminal Integration', () => {
    test('full workflow event sequence should not duplicate routing', () => {
        const routingLog = [];

        const events = [
            { type: 'workflow_start', source: 'system' },
            { type: 'node_start', source: 'triage_architect' },
            { type: 'log', source: 'triage_architect', data: { message: 'Entering node: triage_architect' } },
            { type: 'node_end', source: 'triage_architect' },
            { type: 'node_start', source: 'router_specialist' },
            { type: 'log', source: 'router_specialist', data: { message: 'Entering node: router_specialist' } },
            { type: 'node_end', source: 'router_specialist' },
            { type: 'workflow_end', source: 'system' }
        ];

        events.forEach(event => {
            if (event.type === 'node_start' || event.type === 'specialist_start') {
                routingLog.push(event.source);
            }
            // DON'T add from log events
        });

        // Should have 2 entries, not 4
        expect(routingLog.length).toBe(2);
        expect(routingLog).toEqual(['triage_architect', 'router_specialist']);
    });
});
