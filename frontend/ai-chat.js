(() => {
    const suggestions = [
        {label: 'Explain active incidents', message: 'Summarize the active incidents with the highest priority.', all: true},
        {label: 'Why was this incident prioritized?', message: 'Why was this incident prioritized?'},
        {label: 'Analyze the latest anomaly', message: 'Analyze the latest anomaly and explain what evidence is available.', all: true},
        {label: 'Suggest diagnostic checks', message: 'Suggest diagnostic checks for this incident.'},
    ];
    const chat = {
        open: false,
        status: null,
        checkingStatus: false,
        messages: [],
        sending: false,
        incidentId: '',
    };

    const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
    })[character]);

    function markdownText(value) {
        return escapeHtml(value).split('\n').map(line => {
            let safeLine = line
                .replace(/`([^`]+)`/g, '<code>$1</code>')
                .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
                .replace(/(^|[^*])\*([^*]+)\*/g, '$1<em>$2</em>');
            if (/^###?\s/.test(safeLine)) {
                return `<strong class="ai-message-heading">${safeLine.replace(/^###?\s/, '')}</strong>`;
            }
            if (/^[-*]\s/.test(safeLine)) {
                return `<span class="ai-message-bullet">${safeLine.replace(/^[-*]\s/, '')}</span>`;
            }
            if (/^\d+\.\s/.test(safeLine)) {
                return `<span class="ai-message-bullet">${safeLine.replace(/^\d+\.\s/, '')}</span>`;
            }
            return safeLine ? `<span>${safeLine}</span>` : '<span class="ai-message-spacer"></span>';
        }).join('');
    }

    function getIncidents() {
        const state = window.MetroPulseState;
        return state?.allIncidents || state?.data?.incidents || [];
    }

    function activeIncidentId() {
        const state = window.MetroPulseState;
        return state?.selectedIncidentId || chat.incidentId || getIncidents()[0]?.incident_id || '';
    }

    function statusPresentation() {
        if (chat.status?.available) return {label: 'AI ONLINE', className: 'online'};
        if (chat.checkingStatus) return {label: 'CHECKING', className: 'checking'};
        if (chat.status?.configured) return {label: 'AI UNAVAILABLE', className: 'offline'};
        if (chat.status) return {label: 'AI NOT CONFIGURED', className: 'offline'};
        return {label: 'STATUS UNKNOWN', className: 'offline'};
    }

    function introLabelVisible() {
        try {
            return !sessionStorage.getItem('metropulse-ai-intro-seen');
        } catch (_) {
            return true;
        }
    }

    function ensureStatus() {
        if (chat.checkingStatus || chat.status) return;
        chat.checkingStatus = true;
        window.MetroPulseAIAPI.status()
            .then(result => { chat.status = result; })
            .catch(() => {
                chat.status = {configured: false, available: false, status: 'unavailable', message: 'AI status could not be loaded. Check the MetroPulse backend.'};
            })
            .finally(() => {
                chat.checkingStatus = false;
                render();
            });
    }

    function renderMessages() {
        if (!chat.messages.length) {
            const chips = suggestions.map((item, index) => `<button class="ai-suggestion" data-suggestion="${index}">${escapeHtml(item.label)}<span aria-hidden="true">↗</span></button>`).join('');
            return `<div class="ai-welcome"><div class="ai-welcome-icon" aria-hidden="true">✳</div><h3>Hello, Investigator.</h3><p>I'm MetroPulse AI. I can help you understand incidents, interpret anomalies, examine evidence, and explore probable root causes.</p><div class="ai-suggestions">${chips}</div></div>`;
        }
        return chat.messages.map((message, index) => {
            if (message.role === 'error') {
                return `<article class="ai-message ai-error"><div class="ai-message-label">REQUEST ERROR</div><div>${escapeHtml(message.content)}</div><button class="ai-retry" data-retry="${index}">Retry request</button></article>`;
            }
            const author = message.role === 'user' ? 'YOU' : 'METROPULSE AI';
            return `<article class="ai-message ${message.role === 'user' ? 'from-user' : 'from-ai'}"><div class="ai-message-label">${author}</div><div class="ai-message-body">${message.role === 'assistant' ? markdownText(message.content) : escapeHtml(message.content)}</div></article>`;
        }).join('');
    }

    function render() {
        const root = document.querySelector('#ai-assistant-root');
        if (!root || !document.querySelector('.shell')) {
            if (root) root.innerHTML = '';
            return;
        }
        const incidents = getIncidents();
        if (!chat.incidentId) chat.incidentId = activeIncidentId();
        const status = statusPresentation();
        const options = incidents.slice(0, 50).map(incident => `<option value="${escapeHtml(incident.incident_id)}" ${incident.incident_id === chat.incidentId ? 'selected' : ''}>${escapeHtml(incident.incident_id)} · ${escapeHtml(incident.station_id)} · ${escapeHtml(incident.priority)}</option>`).join('');
        root.innerHTML = `
            <div class="ai-chat-root">
                ${chat.open ? `
                    <section class="ai-chat-panel" role="dialog" aria-modal="false" aria-labelledby="ai-chat-title">
                        <header class="ai-chat-header">
                            <div class="ai-header-brand"><span class="ai-pulse-icon" aria-hidden="true"><i></i><i></i><i></i></span><div><h2 id="ai-chat-title">MetroPulse AI</h2><p>Metro Infrastructure Investigation Assistant</p></div></div>
                            <div class="ai-header-actions"><button class="ai-header-action" id="ai-clear" title="Start a new conversation" aria-label="Start a new conversation">↻</button><button class="ai-header-action" id="ai-close" title="Close assistant" aria-label="Close assistant">×</button></div>
                            <div class="ai-status ${status.className}"><i></i>${status.label}</div>
                        </header>
                        <div class="ai-context-bar"><label for="ai-incident-select">INCIDENT CONTEXT</label><select id="ai-incident-select" aria-label="Select incident context"><option value="">All current network data</option>${options}</select></div>
                        <div class="ai-message-list" id="ai-message-list" aria-live="polite" aria-relevant="additions text">${renderMessages()}${chat.sending ? '<div class="ai-typing" aria-label="MetroPulse AI is preparing a response"><i></i><i></i><i></i><span>Reviewing supplied evidence</span></div>' : ''}</div>
                        <form class="ai-composer" id="ai-composer"><textarea id="ai-input" rows="1" maxlength="1200" aria-label="Ask MetroPulse AI" placeholder="Ask about an incident, anomaly, or root cause..." ${chat.sending ? 'disabled' : ''}></textarea><button class="ai-send" type="submit" aria-label="Send message" ${chat.sending ? 'disabled' : ''}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12 20 4l-4 16-4-7-8-1Zm8 1 8-9"/></svg></button><div class="ai-composer-hint">Enter to send <span>·</span> Shift+Enter for a new line</div></form>
                    </section>` : ''}
                <div class="ai-launcher-wrap">
                    ${introLabelVisible() ? '<span class="ai-intro-label">Investigate with AI</span>' : ''}
                    <button class="ai-launcher" type="button" aria-label="Ask MetroPulse AI" title="Ask MetroPulse AI" aria-expanded="${chat.open}"><span class="ai-launcher-orbit"></span><svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 5.5a10.5 10.5 0 0 0-9.1 15.74L5.5 27l6.05-1.4A10.5 10.5 0 1 0 16 5.5Z"/><path d="M12 15.7h.01M16 15.7h.01M20 15.7h.01"/><path d="M20.5 7.5a3.5 3.5 0 0 1 3.9 4.3"/></svg><i class="ai-launcher-status ${status.className}"></i></button>
                </div>
            </div>`;
        bindEvents(root);
        if (chat.open) scrollMessagesToBottom();
    }

    function scrollMessagesToBottom() {
        const list = document.querySelector('#ai-message-list');
        if (list) list.scrollTop = list.scrollHeight;
    }

    async function sendMessage(message, incidentOverride) {
        const value = String(message || '').trim();
        if (!value || chat.sending) return;
        const incidentId = incidentOverride === undefined ? chat.incidentId : incidentOverride;
        const priorMessages = chat.messages.filter(item => item.role === 'user' || item.role === 'assistant').slice(-8).map(item => ({role: item.role, content: item.content}));
        chat.messages.push({role: 'user', content: value});
        chat.sending = true;
        render();
        try {
            const response = await window.MetroPulseAIAPI.chat({
                message: value,
                incident_id: incidentId || null,
                conversation_context: priorMessages,
            });
            chat.messages.push({role: 'assistant', content: response.answer});
        } catch (error) {
            chat.messages.push({role: 'error', content: error.message, retryText: value, incidentId});
        } finally {
            chat.sending = false;
            render();
            document.querySelector('#ai-input')?.focus();
        }
    }

    function bindEvents(root) {
        root.querySelector('.ai-launcher')?.addEventListener('click', () => {
            chat.open = !chat.open;
            try { sessionStorage.setItem('metropulse-ai-intro-seen', '1'); } catch (_) { /* Storage may be disabled. */ }
            render();
            if (chat.open) {
                ensureStatus();
                document.querySelector('#ai-input')?.focus();
            } else {
                document.querySelector('.ai-launcher')?.focus();
            }
        });
        root.querySelector('#ai-close')?.addEventListener('click', () => {
            chat.open = false;
            render();
            document.querySelector('.ai-launcher')?.focus();
        });
        root.querySelector('#ai-clear')?.addEventListener('click', () => {
            chat.messages = [];
            render();
            document.querySelector('#ai-input')?.focus();
        });
        root.querySelector('#ai-incident-select')?.addEventListener('change', event => {
            chat.incidentId = event.target.value;
        });
        root.querySelectorAll('[data-suggestion]').forEach(button => button.addEventListener('click', () => {
            const suggestion = suggestions[Number(button.dataset.suggestion)];
            sendMessage(suggestion.message, suggestion.all ? null : chat.incidentId || null);
        }));
        root.querySelectorAll('[data-retry]').forEach(button => button.addEventListener('click', () => {
            const message = chat.messages[Number(button.dataset.retry)];
            if (message) sendMessage(message.retryText, message.incidentId);
        }));
        root.querySelector('#ai-composer')?.addEventListener('submit', event => {
            event.preventDefault();
            const input = root.querySelector('#ai-input');
            sendMessage(input.value);
        });
        root.querySelector('#ai-input')?.addEventListener('keydown', event => {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                root.querySelector('#ai-composer').requestSubmit();
            }
        });
        root.querySelector('#ai-input')?.addEventListener('input', event => {
            event.target.style.height = 'auto';
            event.target.style.height = `${Math.min(event.target.scrollHeight, 105)}px`;
        });
    }

    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && chat.open) {
            chat.open = false;
            render();
            document.querySelector('.ai-launcher')?.focus();
        }
    });

    window.mountMetroPulseAI = () => {
        if (document.querySelector('#ai-assistant-root .ai-chat-root')) return;
        render();
        if (!chat.status && !chat.checkingStatus) ensureStatus();
    };
})();
