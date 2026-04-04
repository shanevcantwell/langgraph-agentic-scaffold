// =============================================================================
// V.E.G.A.S. TERMINAL — Mission Report & Toolbars
// Report rendering with sub-tabs and code block copy/save.
// =============================================================================


// =============================================================================
// MISSION REPORT RENDERING
// =============================================================================

function renderMissionReport(markdown) {
    if (!markdown) return;

    // Parse markdown and render to HTML
    const html = marked.parse(markdown);
    archiveOutputEl.innerHTML = html;

    // Generate sub-tabs from H2 headers
    const sections = archiveOutputEl.querySelectorAll('h2');
    if (sections.length > 1) {
        archiveSubtabsEl.innerHTML = '';
        sections.forEach((section, idx) => {
            const btn = document.createElement('button');
            btn.className = 'archive-subtab' + (idx === 0 ? ' active' : '');
            btn.textContent = section.textContent;
            btn.addEventListener('click', () => {
                document.querySelectorAll('.archive-subtab').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                section.scrollIntoView({ behavior: 'smooth', block: 'start' });
            });
            archiveSubtabsEl.appendChild(btn);
        });

        // Set up intersection observer for auto-highlighting
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const idx = Array.from(sections).indexOf(entry.target.querySelector('h2') || entry.target);
                    if (idx >= 0) {
                        document.querySelectorAll('.archive-subtab').forEach((b, i) => {
                            b.classList.toggle('active', i === idx);
                        });
                    }
                }
            });
        }, { root: archiveOutputEl, threshold: 0.3 });

        // Wrap sections for observing
        const wrapper = document.createElement('div');
        let currentSection = null;
        Array.from(archiveOutputEl.childNodes).forEach(node => {
            if (node.tagName === 'H2') {
                if (currentSection) wrapper.appendChild(currentSection);
                currentSection = document.createElement('div');
                currentSection.className = 'report-section';
            }
            if (currentSection) {
                currentSection.appendChild(node.cloneNode(true));
            }
        });
        if (currentSection) wrapper.appendChild(currentSection);
        archiveOutputEl.innerHTML = '';
        archiveOutputEl.appendChild(wrapper);

        // Observe all sections
        document.querySelectorAll('.report-section').forEach(section => {
            observer.observe(section);
        });
    }

    // Add copy/save toolbars to code blocks
    addToolbarsToPreBlocks();
}


// =============================================================================
// CODE BLOCK TOOLBARS
// =============================================================================

function addToolbarsToPreBlocks() {
    const preBlocks = document.querySelectorAll('#archiveOutput pre:not(.has-toolbar), #snapshotContent pre:not(.has-toolbar)');

    preBlocks.forEach(pre => {
        if (pre.querySelector('.toolbar')) return;
        pre.classList.add('has-toolbar');
        pre.style.position = 'relative';

        const toolbar = document.createElement('div');
        toolbar.className = 'toolbar';
        toolbar.style.cssText = 'position: absolute; top: 4px; right: 4px; display: flex; gap: 4px; z-index: 10;';

        // Copy button
        const copyBtn = document.createElement('button');
        copyBtn.className = 'toolbar-btn';
        copyBtn.textContent = 'COPY';
        copyBtn.onclick = async (e) => {
            e.stopPropagation();
            try {
                await navigator.clipboard.writeText(pre.textContent);
                copyBtn.textContent = 'OK';
                setTimeout(() => { copyBtn.textContent = 'COPY'; }, 1000);
            } catch (err) {
                // Fallback
                const range = document.createRange();
                range.selectNodeContents(pre);
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);
                document.execCommand('copy');
                sel.removeAllRanges();
                copyBtn.textContent = 'OK';
                setTimeout(() => { copyBtn.textContent = 'COPY'; }, 1000);
            }
        };
        toolbar.appendChild(copyBtn);

        // Save button (only for content > 500 chars)
        if (pre.textContent.length > 500) {
            const saveBtn = document.createElement('button');
            saveBtn.className = 'toolbar-btn';
            saveBtn.textContent = 'SAVE';
            saveBtn.onclick = (e) => {
                e.stopPropagation();
                const blob = new Blob([pre.textContent], { type: 'text/plain' });
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = 'output.txt';
                a.click();
                URL.revokeObjectURL(a.href);
            };
            toolbar.appendChild(saveBtn);
        }

        pre.appendChild(toolbar);
    });
}
