window.MetroPulseAIAPI = (() => {
    async function request(path, options = {}) {
        const response = await fetch(path, options);
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(payload.detail || `Request failed (${response.status})`);
        }
        return payload;
    }

    function post(path, body) {
        return request(path, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body),
        });
    }

    async function voiceConnect(incidentId, sdp, signal) {
        const response = await fetch(`/api/ai/voice/connect?incident_id=${encodeURIComponent(incidentId || '')}`, {
            method: 'POST',
            headers: {'Content-Type':'application/sdp'},
            body: sdp,
            signal,
        });
        const answer = await response.text();
        if (!response.ok) {
            let message = answer;
            try { message = JSON.parse(answer).detail || message; } catch (_) { /* SDP endpoint can also return plain errors. */ }
            throw new Error(message || `Voice session request failed (${response.status})`);
        }
        return answer;
    }

    return {
        status: () => request('/api/ai/status'),
        chat: body => post('/api/ai/chat', body),
        explain: incidentId => post('/api/ai/explain', {incident_id: incidentId}),
        verify: incidentId => post('/api/ai/verify', {incident_id: incidentId}),
        voiceConnect,
    };
})();
