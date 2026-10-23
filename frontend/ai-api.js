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

    return {
        status: () => request('/api/ai/status'),
        chat: body => post('/api/ai/chat', body),
        explain: incidentId => post('/api/ai/explain', {incident_id: incidentId}),
        verify: incidentId => post('/api/ai/verify', {incident_id: incidentId}),
    };
})();
