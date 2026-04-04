// =============================================================================
// V.E.G.A.S. TERMINAL — SSE Event Handling
// Central event dispatcher for AG-UI events from the streaming API.
// =============================================================================


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
