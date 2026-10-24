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
        voiceMode: false,
        voice: {status:'disconnected',error:'',pc:null,channel:null,stream:null,audio:null,muted:false,audioBlocked:false,turns:[],partial:{},closing:false,generation:0,connectAbort:null},
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

    function voiceSessionActive() {
        return Boolean(chat.voice.pc) && !['disconnected', 'error'].includes(chat.voice.status);
    }

    function renderVoicePanel() {
        const voice = chat.voice;
        const labels = {connecting:'Connecting',listening:'Listening',processing:'Processing',speaking:'Speaking',muted:'Muted',disconnected:'Disconnected',error:'Connection error'};
        const turns = voice.turns.length
            ? voice.turns.map(turn => `<article class="voice-turn ${turn.role}"><b>${turn.role === 'user' ? 'YOU' : 'METROPULSE AI'}</b><p>${escapeHtml(turn.text)}</p></article>`).join('')
            : '<div class="voice-empty">Your live conversation transcript will appear here.</div>';
        const active = voiceSessionActive();
        const severity = getIncidents().find(item => item.incident_id === chat.incidentId)?.severity || 'network';
        return `<section class="voice-agent" aria-label="MetroPulse AI voice agent">
            <div class="voice-agent-title"><div><span class="voice-kicker">VOICE INVESTIGATION</span><h3>MetroPulse AI Voice Agent</h3><p>${escapeHtml(chat.incidentId || 'All current network data')} · ${escapeHtml(severity)}</p></div><span class="voice-status ${voice.status}" role="status"><i></i>${labels[voice.status] || 'Disconnected'}</span></div>
            <div class="voice-orb-stage"><div class="voice-orb ${voice.status}" aria-hidden="true"><span></span><span></span><span></span><span></span><span></span></div><div class="voice-status-caption">${voice.status === 'error' ? 'Check your microphone and connection' : active ? (voice.muted ? 'Microphone muted' : 'Speak naturally; the agent is listening') : 'Start the conversation when ready'}</div></div>
            ${voice.error ? `<div class="voice-error" role="alert">${escapeHtml(voice.error)}</div>` : ''}
            ${voice.audioBlocked ? '<button class="voice-enable-audio" id="voice-enable-audio">Tap to enable agent audio</button>' : ''}
            <div class="voice-transcript" id="voice-transcript" aria-live="polite">${turns}</div>
            <div class="voice-controls">${active ? `<button class="voice-control ${voice.muted ? 'selected' : ''}" id="voice-mute">${voice.muted ? 'Unmute mic' : 'Mute mic'}</button><button class="voice-control end" id="voice-end">End conversation</button>` : `<button class="voice-control primary" id="voice-start">${voice.status === 'error' ? 'Retry connection' : 'Start voice conversation'}</button>`}<button class="voice-control back" id="voice-back">Back to Chat</button></div>
            <p class="voice-disclosure">AI-generated voice · Hindi by default, switches to English when spoken or requested · Advisory only</p>
        </section>`;
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
                    <section class="ai-chat-panel ${chat.voiceMode ? 'voice-mode' : ''}" role="dialog" aria-modal="false" aria-labelledby="ai-chat-title">
                        <header class="ai-chat-header">
                            <div class="ai-header-brand"><span class="ai-pulse-icon" aria-hidden="true"><i></i><i></i><i></i></span><div><h2 id="ai-chat-title">MetroPulse AI</h2><p>Metro Infrastructure Investigation Assistant</p></div></div>
                            <div class="ai-header-actions"><button class="ai-header-action" id="ai-clear" title="Start a new conversation" aria-label="Start a new conversation">↻</button><button class="ai-header-action" id="ai-close" title="Close assistant" aria-label="Close assistant">×</button></div>
                            <div class="ai-status ${status.className}"><i></i>${status.label}</div>
                        </header>
                        <div class="ai-context-bar"><label for="ai-incident-select">INCIDENT CONTEXT</label><select id="ai-incident-select" aria-label="Select incident context" ${voiceSessionActive() ? 'disabled' : ''}><option value="">All current network data</option>${options}</select></div>
                        ${chat.voiceMode ? renderVoicePanel() : ''}
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

    function updateVoiceTurn(role, id, text) {
        const value = String(text || '').trim();
        if (!value) return;
        const key = id || `${role}-${Date.now()}`;
        const turn = chat.voice.turns.find(item => item.id === key);
        if (turn) turn.text = value;
        else chat.voice.turns.push({id:key,role,text:value});
        const existing = chat.messages.find(item => item.voiceId === key);
        if (existing) existing.content = value;
        else if (role === 'user' && chat.messages.at(-1)?.role === 'user' && chat.messages.at(-1)?.content === value) {
            chat.messages.at(-1).voiceId = key;
        } else {
            chat.messages.push({role,content:value,voiceId:key,source:'voice'});
        }
        if (chat.voiceMode) {
            render();
            const list = document.querySelector('#voice-transcript');
            if (list) list.scrollTop = list.scrollHeight;
        }
    }

    function voiceStatus(status, error = '') {
        chat.voice.status = status;
        chat.voice.error = error;
        if (chat.voiceMode) render();
    }

    function friendlyVoiceError(error) {
        if (error?.name === 'NotAllowedError' || error?.name === 'PermissionDeniedError') return 'Microphone permission was denied. Allow microphone access in your browser settings, then retry.';
        if (error?.name === 'NotFoundError' || error?.name === 'DevicesNotFoundError') return 'No microphone was found. Connect a microphone and retry.';
        if (!window.isSecureContext) return 'Microphone access requires localhost or a secure HTTPS connection.';
        return error?.message || 'The voice session could not connect. Check your network and OpenAI Realtime access, then retry.';
    }

    function releaseVoiceResources() {
        const voice = chat.voice;
        voice.connectAbort?.abort();
        voice.connectAbort = null;
        if (voice.channel) { voice.channel.onopen = voice.channel.onclose = voice.channel.onmessage = voice.channel.onerror = null; try { voice.channel.close(); } catch (_) {} }
        if (voice.stream) voice.stream.getTracks().forEach(track => { track.enabled = false; track.stop(); });
        if (voice.pc) { voice.pc.onconnectionstatechange = voice.pc.ontrack = null; try { voice.pc.close(); } catch (_) {} }
        if (voice.audio) { voice.audio.pause(); voice.audio.srcObject = null; voice.audio = null; }
        voice.channel = voice.stream = voice.pc = null;
        voice.muted = false;
    }

    async function stopVoiceSession({returnToChat = false, notifyServer = true} = {}) {
        const voice = chat.voice;
        if (voice.closing) return;
        voice.closing = true;
        voice.generation += 1;
        voice.connectAbort?.abort();
        voice.connectAbort = null;
        if (voice.stream) voice.stream.getAudioTracks().forEach(track => { track.enabled = false; });
        if (notifyServer && voice.channel?.readyState === 'open') {
            try {
                const closed = new Promise(resolve => { voice.closedResolve = resolve; setTimeout(resolve, 1800); });
                voice.channel.send(JSON.stringify({type:'session.close'}));
                await closed;
            } catch (_) { /* The local media tracks are still released below. */ }
        }
        releaseVoiceResources();
        voice.partial = {};
        voice.audioBlocked = false;
        voice.closedResolve = null;
        voice.closing = false;
        voice.status = 'disconnected';
        if (returnToChat) chat.voiceMode = false;
        if (chat.open) render();
    }

    function sendVoiceEvent(event) {
        const channel = chat.voice.channel;
        if (channel?.readyState === 'open') channel.send(JSON.stringify(event));
    }

    async function executeVoiceTool(event) {
        const voice = chat.voice;
        if (event.name !== 'ask_metropulse_evidence') return;
        let question = '';
        try { question = String(JSON.parse(event.arguments || '{}').question || '').trim().slice(0,1200); } catch (_) {}
        if (!question) question = 'Answer the operator using the selected incident evidence. If the question is unclear, ask for clarification.';
        const userKey = `voice-question-${event.call_id || Date.now()}`;
        if (!chat.messages.some(item => item.role === 'user' && item.content === question)) updateVoiceTurn('user', userKey, question);
        voiceStatus('processing');
        const conversation = chat.messages.filter(item => item.role === 'user' || item.role === 'assistant').slice(-9, -1).map(item => ({role:item.role,content:item.content}));
        let output;
        try {
            const result = await window.MetroPulseAIAPI.chat({message:question,incident_id:chat.incidentId || null,conversation_context:conversation});
            output = JSON.stringify({answer:result.answer,incident_id:result.incident_id || chat.incidentId,source:'existing MetroPulse investigation chat'});
        } catch (error) {
            output = JSON.stringify({error:`Evidence lookup failed: ${error.message}. Do not guess; tell the operator the evidence service is unavailable.`});
        }
        sendVoiceEvent({type:'conversation.item.create',item:{type:'function_call_output',call_id:event.call_id,output}});
        sendVoiceEvent({type:'response.create'});
    }

    function handleVoiceEvent(event) {
        if (!event || typeof event !== 'object') return;
        if (event.type === 'response.event' && event.event) event = event.event;
        const voice = chat.voice;
        switch (event.type) {
            case 'session.started':
            case 'session.created':
            case 'session.updated':
                voiceStatus(voice.muted ? 'muted' : 'listening');
                break;
            case 'input_audio_buffer.speech_started':
                voiceStatus(voice.muted ? 'muted' : 'listening');
                break;
            case 'input_audio_buffer.speech_stopped':
                voiceStatus('processing');
                break;
            case 'conversation.item.input_audio_transcription.completed':
            case 'input_audio_transcription.completed':
                updateVoiceTurn('user',event.item_id || `heard-${Date.now()}`,event.transcript);
                voiceStatus('processing');
                break;
            case 'response.created':
                voiceStatus('processing');
                break;
            case 'response.output_audio.delta':
            case 'response.audio.delta':
                if (voice.status !== 'speaking') voiceStatus('speaking');
                break;
            case 'response.output_audio_transcript.delta': {
                const id=event.item_id || 'assistant-current';
                voice.partial[id]=(voice.partial[id] || '') + (event.delta || '');
                updateVoiceTurn('assistant',id,voice.partial[id]);
                voiceStatus('speaking');
                break;
            }
            case 'response.output_audio_transcript.done':
                updateVoiceTurn('assistant',event.item_id || `answer-${Date.now()}`,event.transcript);
                delete voice.partial[event.item_id];
                voiceStatus(voice.muted ? 'muted' : 'listening');
                break;
            case 'response.output_text.done':
                if (event.text) updateVoiceTurn('assistant',event.item_id || `answer-${Date.now()}`,event.text);
                break;
            case 'response.done':
                if (!voice.muted && voice.status !== 'error') voiceStatus('listening');
                break;
            case 'response.function_call_arguments.done':
                executeVoiceTool(event);
                break;
            case 'session.closed':
                voice.closedResolve?.();
                if (!voice.closing) { releaseVoiceResources(); voiceStatus('disconnected','The Realtime session ended. Start a new session to continue.'); }
                break;
            case 'error':
                releaseVoiceResources();
                voiceStatus('error',event.error?.message || 'The Realtime session reported an error. End and reconnect the session.');
                break;
            default:
                break;
        }
    }

    function waitForIceGathering(pc) {
        if (pc.iceGatheringState === 'complete') return Promise.resolve();
        return new Promise((resolve,reject) => {
            const timeout=setTimeout(() => {pc.removeEventListener('icegatheringstatechange',changed);reject(new Error('Timed out preparing the secure audio connection.'))},10000);
            function changed(){if(pc.iceGatheringState!=='complete')return;clearTimeout(timeout);pc.removeEventListener('icegatheringstatechange',changed);resolve();}
            pc.addEventListener('icegatheringstatechange',changed);
        });
    }

    async function startVoiceSession() {
        const voice=chat.voice;
        if (voiceSessionActive() || voice.status==='connecting') return;
        if (chat.status && !chat.status.available) {voiceStatus('error',chat.status.message || 'OpenAI is not online. Check Settings and retry.');return;}
        if (!navigator.mediaDevices?.getUserMedia || !window.RTCPeerConnection) {voiceStatus('error','This browser does not support WebRTC microphone access.');return;}
        const generation=++voice.generation;
        voice.error='';voice.status='connecting';voice.muted=false;render();
        try {
            const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
            if (generation !== voice.generation || !chat.open || !chat.voiceMode) {stream.getTracks().forEach(track=>track.stop());return;}
            voice.stream=stream;
            const pc=new RTCPeerConnection();voice.pc=pc;
            pc.ontrack=event=>{
                const audio=new Audio();audio.autoplay=true;audio.srcObject=event.streams?.[0] || new MediaStream([event.track]);voice.audio=audio;
                audio.play().then(()=>{voice.audioBlocked=false}).catch(()=>{voice.audioBlocked=true;if(chat.voiceMode)render()});
            };
            pc.onconnectionstatechange=()=>{
                if (pc.connectionState==='failed') {releaseVoiceResources();voiceStatus('error','WebRTC connection failed. Check network access and retry.');}
                else if (pc.connectionState==='disconnected' && voice.status!=='disconnected') {voiceStatus('disconnected','The voice connection was interrupted. Reconnect to continue.');releaseVoiceResources();}
            };
            stream.getAudioTracks().forEach(track=>pc.addTrack(track,stream));
            const channel=pc.createDataChannel('oai-events');voice.channel=channel;
            channel.onopen=()=>voiceStatus('listening');
            channel.onmessage=event=>{try{handleVoiceEvent(JSON.parse(event.data))}catch(_){voiceStatus('error','The voice session returned an unreadable event.')}};
            channel.onerror=()=>{releaseVoiceResources();voiceStatus('error','The Realtime event channel failed. End and retry the session.');};
            channel.onclose=()=>{if(voice.pc && !voice.closing){releaseVoiceResources();voiceStatus('disconnected','The Realtime session disconnected. Reconnect to continue.')}};
            const offer=await pc.createOffer();await pc.setLocalDescription(offer);await waitForIceGathering(pc);
            if (generation !== voice.generation) return;
            const sdp=pc.localDescription?.sdp;if(!sdp)throw new Error('The browser did not create a WebRTC offer.');
            voice.connectAbort=new AbortController();
            const response=await window.MetroPulseAIAPI.voiceConnect(chat.incidentId,sdp,voice.connectAbort.signal);
            if (generation !== voice.generation) return;
            await pc.setRemoteDescription({type:'answer',sdp:response});
        } catch(error) {
            if (generation !== voice.generation) return;
            releaseVoiceResources();
            voice.status='error';voice.error=friendlyVoiceError(error);render();
        }
    }

    function toggleVoiceMute() {
        const voice=chat.voice;if(!voice.stream)return;
        voice.muted=!voice.muted;
        voice.stream.getAudioTracks().forEach(track=>{track.enabled=!voice.muted});
        voiceStatus(voice.muted?'muted':'listening');
    }

    function bindEvents(root) {
        root.querySelector('.ai-send')?.insertAdjacentHTML('beforebegin', '<button class="ai-voice-launch" id="ai-voice-launch" type="button" aria-label="Open voice agent" title="Talk to MetroPulse AI"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Z"/><path d="M19 11a7 7 0 0 1-14 0M12 18v4m-4 0h8"/></svg></button>');
        root.querySelector('.ai-launcher')?.addEventListener('click', () => {
            chat.open = !chat.open;
            if (!chat.open) stopVoiceSession({notifyServer:true});
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
            stopVoiceSession({notifyServer:true});
            chat.open = false;
            render();
            document.querySelector('.ai-launcher')?.focus();
        });
        root.querySelector('#ai-clear')?.addEventListener('click', () => {
            stopVoiceSession({notifyServer:true});
            chat.messages = [];
            chat.voice.turns = [];
            chat.voiceMode = false;
            render();
            document.querySelector('#ai-input')?.focus();
        });
        root.querySelector('#ai-incident-select')?.addEventListener('change', event => {
            chat.incidentId = event.target.value;
        });
        root.querySelector('#ai-voice-launch')?.addEventListener('click', () => {
            chat.voiceMode = true;
            render();
            startVoiceSession();
        });
        root.querySelector('#voice-start')?.addEventListener('click', startVoiceSession);
        root.querySelector('#voice-end')?.addEventListener('click', () => stopVoiceSession());
        root.querySelector('#voice-back')?.addEventListener('click', () => stopVoiceSession({returnToChat:true}));
        root.querySelector('#voice-mute')?.addEventListener('click', toggleVoiceMute);
        root.querySelector('#voice-enable-audio')?.addEventListener('click', async () => {
            try { await chat.voice.audio?.play(); chat.voice.audioBlocked=false; render(); }
            catch (_) { voiceStatus('error','Browser audio is still blocked. Allow audio playback and retry.'); }
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
            stopVoiceSession({notifyServer:true});
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
