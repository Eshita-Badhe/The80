const scenarioCatalog = {
    communications: {
        label: 'Communication failure',
        description: 'Simulates a backbone communication timeout with high latency.',
    },
    power: {
        label: 'Power anomaly',
        description: 'Simulates a traction supply voltage fluctuation.',
    },
    escalator: {
        label: 'Equipment degradation',
        description: 'Simulates an escalator motor temperature threshold event.',
    },
    sensor: {
        label: 'Sensor anomaly',
        description: 'Simulates a lift vibration sensor reading outside its baseline.',
    },
    signaling: {
        label: 'Signal anomaly',
        description: 'Simulates a signal aspect feedback mismatch.',
    },
    hvac: {
        label: 'HVAC temperature anomaly',
        description: 'Simulates an HVAC temperature event. Train dwell telemetry is not available.',
    },
    cascade: {
        label: 'Multiple simultaneous faults',
        description: 'Simulates correlated power, signaling, and communication events.',
    },
};

function scenarioSelect(id) {
    const options = Object.entries(scenarioCatalog)
        .map(([value, scenario]) => `<option value="${value}">${scenario.label}</option>`)
        .join('');

    return `<select class="select" id="${id}" aria-label="Simulated incident scenario">${options}</select>`;
}

async function chooseScenario() {
    const select = $('#scenario-choice') || $('#scenario-choice-ingest') || $('#live-scenario');
    await generateScenario(select?.value || 'communications');
}

async function generateScenario(scenario) {
    try {
        const result = await api('/api/simulation/generate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({scenario}),
        });
        state.scenario = scenario;
        state.lastScenarioEvents = result.records_added;
        state.data = result.dashboard;
        state.selectedIncidentId = result.incident_id || null;
        state.investigation = null;
        state.allIncidents = null;
        state.allAnomalies = null;
        render();
        toast(`${scenarioCatalog[scenario]?.label || scenario} generated · ${result.records_added} event(s)`);
    } catch (error) {
        toast(error.message);
    }
}

function overview() {
    const data = state.data;
    const stats = data.statistics;
    const currentIncidents = data.incidents || [];
    const highPriority = stats.high_priority_incidents || 0;
    const equipmentAffected = stats.equipment_affected || 0;
    const health = stats.open_incidents > 0 ? 'Attention' : 'Nominal';
    const recentIncidents = [...currentIncidents].sort((a,b) => new Date(b.timestamp)-new Date(a.timestamp));

    $('#view').innerHTML = `
        <div class="welcome">
            <div>
                <div class="eyebrow">Operations overview · simulated network</div>
                <h2>Infrastructure at a glance</h2>
                <p>Fictional Pune network · Synthetic telemetry · Updated ${new Date(data.timestamp).toLocaleTimeString('en-IN', {timeZone: 'Asia/Kolkata'})} IST</p>
            </div>
            <div class="actions">
                <span class="health-pill ${health === 'Nominal' ? 'healthy' : 'attention'}" title="Derived from the count of open incidents; this is not a live operational health feed."><i></i>NETWORK ${health.toUpperCase()}</span>
                <button class="btn" id="play">${data.playing ? 'Ⅱ Pause simulation' : '▶ Resume simulation'}</button>
                <button class="btn primary" id="scenario">Generate scenario</button>
            </div>
        </div>
        <div class="metrics">
            ${metric('Telemetry events', stats.processed_records, 'Normalized records', '⌁')}
            ${metric('Open incidents', stats.open_incidents, 'Require investigation', '◉', 'warn')}
            ${metric('Critical priority', stats.critical_incidents, 'Priority score ≥ 80', '▲', 'alert')}
            ${metric('High priority', highPriority, 'Priority score 62–79', '⬈', 'warn')}
            ${metric('Anomalies detected', stats.anomalies, 'Rule-based findings', '⌁', 'warn')}
            ${metric('Stations affected', stats.stations_affected, `Of ${data.stations.length} fictional stations`, '◎')}
            ${metric('Equipment affected', equipmentAffected, 'In grouped incidents', '▤')}
        </div>
        <div class="grid-main">
            <div class="panel">
                <div class="panel-head">
                    <div><div class="panel-title">Fictional metro network</div><div class="panel-sub">Select a station to filter incident results</div></div>
                    <span class="tag">${data.stations.length} STATIONS · SIMULATED</span>
                </div>
                <div class="network">${networkSvg(data)}</div>
                <div class="legend"><span><i></i>Nominal</span><span><i class="legend-violet"></i>Attention</span><span><i class="legend-red"></i>Multiple open</span></div>
            </div>
            <div class="panel">
                <div class="panel-head">
                    <div><div class="panel-title">Telemetry events over time</div><div class="panel-sub">Current dataset · events per hour</div></div>
                    <span class="tag">${data.events_by_hour.length} BINS</span>
                </div>
                ${bars(data.events_by_hour)}
            </div>
        </div>
        <div class="charts-grid">
            <div class="panel">
                <div class="panel-head"><div><div class="panel-title">Incident severity</div><div class="panel-sub">Distribution across processed incidents</div></div><span class="tag">${Object.values(data.severity_distribution).reduce((sum, count) => sum + count, 0)} INCIDENTS</span></div>
                ${severityChart(data.severity_distribution)}
            </div>
            <div class="panel">
                <div class="panel-head"><div><div class="panel-title">Equipment categories</div><div class="panel-sub">Grouped incidents by equipment class</div></div><span class="tag">RULE BASED</span></div>
                ${categoryBars(data.category_distribution)}
            </div>
        </div>
        <div class="lower-grid overview-lower">
            <div class="panel table-panel">
                <div class="panel-head">
                    <div><div class="panel-title">Recent incidents</div><div class="panel-sub">Open a row to inspect evidence and priority</div></div>
                    <button class="btn" onclick="navigate('Incident Explorer')">View all incidents</button>
                </div>
                ${incidentTable(recentIncidents.slice(0, 8))}
            </div>
            <div class="panel">
                <div class="panel-head"><div><div class="panel-title">Recent telemetry feed</div><div class="panel-sub">Latest observed simulated events</div></div><span class="tag">SIMULATED</span></div>
                <div class="feed">${data.recent_events.slice(0, 7).map(event => `<div class="feed-item ${esc(event.severity)}"><span class="feed-time">${new Date(event.timestamp).toLocaleTimeString('en-IN', {hour:'2-digit', minute:'2-digit', timeZone:'Asia/Kolkata', hour12:false})}</span><span class="feed-line"></span><div class="feed-text">${esc(event.description)}<small>${esc(event.station_id)} · ${esc(event.equipment_id)} · ${esc(event.severity)}</small></div></div>`).join('')}</div>
                <button class="btn evidence-link" onclick="navigate('Anomaly & Evidence')">Review anomaly evidence</button>
            </div>
        </div>`;

    $$('#view [data-incident]').forEach(row => {
        row.onclick = () => openIncident(row.dataset.incident);
    });
    $$('.station-node').forEach(node => {
        node.onclick = () => {
            state.station = node.dataset.station;
            state.page = 'Incident Explorer';
            render();
        };
    });
    $('#scenario').onclick = () => {
        state.page = 'Simulation & Ingestion';
        render();
    };
    $('#play').onclick = async () => {
        const action = state.data.playing ? 'pause' : 'start';
        try {
            await api(`/api/simulation/control?action=${action}`, {method: 'POST'});
            state.data = await api('/api/dashboard');
            invalidateDatasetCaches();
            render();
        } catch (error) {
            toast(error.message);
        }
    };
}

function liveMonitor() {
    const data = state.data;
    const lastEvent = data.recent_events[0];
    const incidents = data.incidents || [];

    $('#view').innerHTML = `
        <div class="welcome">
            <div><div class="eyebrow">Live monitor · simulated telemetry</div><h2>Network activity</h2><p>Playback appends nominal sample events. Failure events are generated only when selected.</p></div>
            <div class="actions"><button class="btn primary" id="live-toggle">${data.playing ? 'Ⅱ Pause playback' : '▶ Start playback'}</button><button class="btn" id="live-reset">Reset demo</button></div>
        </div>
        <div class="metrics live-metrics">
            ${metric('Playback status', data.playing ? 'RUNNING' : 'PAUSED', data.playing ? 'Simulated records advancing' : 'Waiting for operator action', '●')}
            ${metric('Active incidents', data.statistics.open_incidents, 'Backend grouped incidents', '◉', 'warn')}
            ${metric('Detected anomalies', data.statistics.anomalies, 'Rule-based findings', '⌁', 'warn')}
            ${metric('Events processed', data.statistics.processed_records, 'Current dataset', '▤')}
        </div>
        <div class="live-grid">
            <div class="panel">
                <div class="panel-head"><div><div class="panel-title">Station network status</div><div class="panel-sub">Click a station to inspect its incidents</div></div><span class="tag">SIMULATED</span></div>
                <div class="network live-network">${networkSvg(data)}</div>
                <div class="legend"><span><i></i>Nominal</span><span><i class="legend-violet"></i>Attention</span><span><i class="legend-red"></i>Multiple open</span></div>
            </div>
            <div class="panel">
                <div class="panel-head"><div><div class="panel-title">Simulation controls</div><div class="panel-sub">Only controls backed by the current API are enabled</div></div><span class="tag">${esc(state.scenario.toUpperCase())}</span></div>
                <label class="field-label" for="live-scenario">Generate a supported scenario</label>
                ${scenarioSelect('live-scenario')}
                <div class="scenario-description" id="live-scenario-description">${scenarioCatalog[state.scenario]?.description || 'Choose a supported synthetic scenario.'}</div>
                <button class="btn primary" id="live-generate">Generate selected event</button>
                <div class="telemetry-limit"><b>Telemetry available in this prototype</b><span>Timestamp, station, equipment, category, event, severity, metric, and value.</span><span>Train speed, dwell time, headway, and passenger load are not present in the backend data.</span></div>
            </div>
        </div>
        <div class="panel live-feed-panel">
            <div class="panel-head"><div><div class="panel-title">Telemetry and detection stream</div><div class="panel-sub">Latest backend records and processed findings</div></div><span class="tag">${lastEvent ? `LAST EVENT ${new Date(lastEvent.timestamp).toLocaleTimeString('en-IN', {timeZone:'Asia/Kolkata'})}` : 'NO EVENTS'}</span></div>
            <div class="table-wrap"><table><thead><tr><th>Timestamp</th><th>Station</th><th>Equipment</th><th>Event</th><th>Severity</th><th>Value</th><th>Source</th></tr></thead><tbody>${data.recent_events.map(event => `<tr><td class="mono">${new Date(event.timestamp).toLocaleTimeString('en-IN', {hour:'2-digit',minute:'2-digit',second:'2-digit',timeZone:'Asia/Kolkata'})}</td><td>${esc(event.station_id)}</td><td>${esc(event.equipment_id)}</td><td>${esc(event.event_type || event.description)}</td><td><span class="sev ${esc(event.severity)}">${esc(event.severity)}</span></td><td>${esc(event.metric || '—')} ${esc(event.value ?? '')} ${esc(event.unit || '')}</td><td>${esc(event.source || 'simulated')}</td></tr>`).join('')}</tbody></table></div>
            <div class="monitor-footnote">Simulation time: ${new Date(data.timestamp).toLocaleString('en-IN', {timeZone:'Asia/Kolkata'})} IST · Current incidents: ${incidents.length} in the dashboard response.</div>
        </div>`;

    const detectionEvents = [...data.anomalies]
        .sort((a,b) => new Date(b.timestamp)-new Date(a.timestamp))
        .slice(0, 6);
    if (detectionEvents.length) {
        $('.live-feed-panel').insertAdjacentHTML('afterend', `
            <section class="panel detection-stream">
                <div class="panel-head"><div><div class="panel-title">Detection events</div><div class="panel-sub">Rule findings from the current processed response</div></div><button class="btn" id="live-view-evidence">Open anomaly evidence</button></div>
                <div class="detection-list">${detectionEvents.map(anomaly => `<button class="detection-item" data-anomaly-id="${esc(anomaly.anomaly_id)}"><span class="sev ${esc(anomaly.severity)}">${esc(anomaly.severity)}</span><b>${esc(anomaly.type || anomaly.metric || 'Rule finding')}</b><span>${esc(anomaly.station_id)} · ${new Date(anomaly.timestamp).toLocaleTimeString('en-IN',{timeZone:'Asia/Kolkata'})}</span></button>`).join('')}</div>
            </section>`);
        $('#live-view-evidence').onclick = () => navigate('Anomaly & Evidence');
        $$('.detection-item').forEach(item => item.onclick = () => navigate('Anomaly & Evidence'));
    }

    $('#live-toggle').onclick = async () => {
        const action = state.data.playing ? 'pause' : 'start';
        try {
            await api(`/api/simulation/control?action=${action}`, {method: 'POST'});
            state.data = await api('/api/dashboard');
            invalidateDatasetCaches();
            render();
        } catch (error) {
            toast(error.message);
        }
    };
    $('#live-scenario').value = state.scenario in scenarioCatalog ? state.scenario : 'communications';
    $('#live-reset').onclick = resetDemo;
    $('#live-generate').onclick = () => generateScenario($('#live-scenario').value);
    if (state.selectedIncidentId) {
        $('#live-generate').insertAdjacentHTML('afterend', '<button class="btn generated-incident-link" id="live-view-generated">View generated incident</button>');
        $('#live-view-generated').onclick = () => {
            state.q = state.selectedIncidentId;
            state.station = '';
            state.page = 'Incident Explorer';
            render();
        };
    }
    $('#live-scenario').onchange = event => {
        state.scenario = event.target.value;
        $('#live-scenario-description').textContent = scenarioCatalog[event.target.value].description;
    };
    $$('.station-node').forEach(node => {
        node.onclick = () => {
            state.station = node.dataset.station;
            state.page = 'Incident Explorer';
            render();
        };
    });
}

function ingestion() {
    const data = state.data;
    $('#view').innerHTML = `
        <div class="welcome"><div><div class="eyebrow">Simulation · input · processing</div><h2>Simulation &amp; Ingestion</h2><p>Generate a supported scenario or import sample telemetry into the same processing pipeline.</p></div><span class="health-pill"><i></i>SIMULATION MODE</span></div>
        <div class="pipeline-strip" aria-label="Processing lifecycle"><span>Raw input</span><b>→</b><span>Validation</span><b>→</b><span>Normalization</span><b>→</b><span>Processing</span><b>→</b><span>Detection</span></div>
        <div class="simulation-ingestion-grid">
            <section class="panel simulation-panel">
                <div class="panel-head"><div><div class="panel-title">A · Simulation controls</div><div class="panel-sub">Scenarios currently supported by the backend</div></div><span class="tag">${data.playing ? 'PLAYING' : 'READY'}</span></div>
                <label class="field-label" for="scenario-choice-ingest">Select a fictional scenario</label>
                ${scenarioSelect('scenario-choice-ingest')}
                <p class="scenario-description" id="ingest-scenario-description">${scenarioCatalog[state.scenario]?.description || 'Choose a supported synthetic scenario.'}</p>
                <div class="actions"><button class="btn primary" id="scenario-ingest">Generate scenario</button><button class="btn" id="simulation-toggle">${data.playing ? 'Pause playback' : 'Start playback'}</button><button class="btn" id="reset">Reset demo dataset</button></div>
                <div class="simulation-summary"><div><small>EXECUTION STATUS</small><b>${data.playing ? 'Playback running' : 'Idle'}</b></div><div><small>EVENTS GENERATED LAST RUN</small><b>${state.lastScenarioEvents ? fmt(state.lastScenarioEvents) : '—'}</b></div><div><small>LAST SCENARIO</small><b>${scenarioCatalog[state.scenario]?.label || 'Baseline data'}</b></div></div>
                ${state.selectedIncidentId ? `<button class="btn generated-incident-link" id="view-generated-incident">View generated incident · ${esc(state.selectedIncidentId)}</button>` : ''}
                <p class="capability-note">The API does not currently support simulation duration, event-count controls, playback speed, train delay, or dwell telemetry. Those controls are intentionally not shown.</p>
            </section>
            <section class="panel ingestion-panel">
                <div class="panel-head"><div><div class="panel-title">B · Data ingestion</div><div class="panel-sub">Validated CSV, JSON, or TXT input · maximum 5 MB</div></div><span class="tag">BACKEND VALIDATION</span></div>
                <div id="drop" class="dropzone"><label for="file" style="cursor:pointer"><div class="ingest-icon">⇧</div><b>Drop a file here or browse</b><div class="panel-sub">CSV rows · JSON array/object · TXT JSONL or key=value logs</div></label><input type="file" id="file" accept=".csv,.json,.txt"></div>
                <div id="selected"></div>
                <div class="actions ingestion-actions"><button class="btn primary" id="upload" disabled>Upload and validate</button><button class="btn" id="process">Run processing engine</button><button class="btn" id="download-csv">Export telemetry CSV</button><button class="btn" id="download-json">Export telemetry JSON</button></div>
                <div id="result"></div>
            </section>
        </div>
        <div class="panel ingestion-history">
            <div class="panel-head"><div><div class="panel-title">Ingestion history</div><div class="panel-sub">Source, validation counts, processing state, and receipt time</div></div><button class="btn" id="refresh-history">Refresh history</button></div>
            <div id="history"><div class="empty">Loading ingestion history…</div></div>
        </div>`;

    wireIngestion();
    $('#scenario-choice-ingest').value = state.scenario in scenarioCatalog ? state.scenario : 'communications';
    $('#scenario-choice-ingest').onchange = event => {
        state.scenario = event.target.value;
        $('#ingest-scenario-description').textContent = scenarioCatalog[event.target.value].description;
    };
    $('#simulation-toggle').onclick = async () => {
        const action = state.data.playing ? 'pause' : 'start';
        try {
            await api(`/api/simulation/control?action=${action}`, {method: 'POST'});
            state.data = await api('/api/dashboard');
            invalidateDatasetCaches();
            render();
        } catch (error) {
            toast(error.message);
        }
    };
    $('#view-generated-incident')?.addEventListener('click', () => {
        state.q = state.selectedIncidentId;
        state.station = '';
        state.page = 'Incident Explorer';
        render();
    });
}

async function explorer() {
    $('#view').innerHTML = `<div class="welcome"><div><div class="eyebrow">Investigation workspace</div><h2>Incident Explorer</h2><p>Search the current processed dataset and inspect linked evidence.</p></div><span class="tag">SIMULATED RECORDS</span></div><div class="empty">Loading incidents…</div>`;
    try {
        const response = await api('/api/incidents?limit=500');
        state.allIncidents = response.incidents;
        renderIncidentExplorer();
    } catch (error) {
        $('#view').innerHTML = `<div class="panel empty"><strong>Could not load incidents</strong><p>${esc(error.message)}</p><button class="btn" onclick="navigate('Incident Explorer')">Retry</button></div>`;
    }
}

function renderIncidentExplorer() {
    const incidents = state.allIncidents || [];
    const openCount = incidents.filter(incident => incident.status === 'open').length;
    const criticalCount = incidents.filter(incident => incident.priority === 'critical').length;
    const highCount = incidents.filter(incident => incident.priority === 'high').length;
    const stations = state.data.stations;
    const categories = [...new Set(incidents.map(incident => incident.equipment_category))].sort();

    $('#view').innerHTML = `
        <div class="welcome"><div><div class="eyebrow">Search · filter · investigate</div><h2>Incident Explorer</h2><p>Each row links to its source records and rule-based findings. Suspected causes remain unconfirmed.</p></div><span class="tag">${incidents.length} INCIDENTS</span></div>
        <div class="metrics incident-summary">
            ${metric('Total incidents', incidents.length, 'Current backend results', '▤')}
            ${metric('Open', openCount, 'Needs investigation', '◉', 'warn')}
            ${metric('Critical', criticalCount, 'Highest priority tier', '▲', 'alert')}
            ${metric('High', highCount, 'Priority tier', '⬈', 'warn')}
        </div>
        <div class="panel table-panel incident-explorer-panel">
            <div class="panel-head"><div><div class="panel-title">Processed incidents</div><div class="panel-sub">Search ID, station, equipment, or event description. Scenario IDs are not persisted; equipment category is the available scenario proxy.</div></div></div>
            <div class="incident-filters">
                <input class="input" id="incident-search" placeholder="Search incidents…" value="${esc(state.q)}">
                <select class="select" id="incident-severity"><option value="">All severity</option>${['critical','high','medium','low','normal'].map(value => `<option value="${value}">${value}</option>`).join('')}</select>
                <select class="select" id="incident-status"><option value="">All status</option><option value="open">Open</option><option value="monitoring">Monitoring</option></select>
                <select class="select" id="incident-station"><option value="">All stations</option>${stations.map(station => `<option value="${station.station_id}">${esc(station.name)} · ${station.station_id}</option>`).join('')}</select>
                <select class="select" id="incident-category"><option value="">All event categories / scenario proxy</option>${categories.map(category => `<option value="${esc(category)}">${esc(category)}</option>`).join('')}</select>
                <select class="select" id="incident-period"><option value="all">All time</option><option value="24">Last 24 hours</option><option value="168">Last 7 days</option></select>
                <select class="select" id="incident-sort"><option value="priority">Sort: priority</option><option value="timestamp">Sort: newest</option><option value="severity">Sort: severity</option></select>
            </div>
            <div id="incident-results"></div>
        </div>`;

    const controls = ['#incident-search','#incident-severity','#incident-status','#incident-station','#incident-category','#incident-period','#incident-sort'];
    const update = () => {
        const query = $('#incident-search').value.trim().toLowerCase();
        const severity = $('#incident-severity').value;
        const status = $('#incident-status').value;
        const station = $('#incident-station').value;
        state.station = station;
        const category = $('#incident-category').value;
        const hours = Number($('#incident-period').value || 0);
        const cutoff = hours ? Date.now() - hours * 60 * 60 * 1000 : 0;
        const sort = $('#incident-sort').value;
        const result = incidents.filter(incident => {
            const textMatch = !query || `${incident.incident_id} ${incident.station_id} ${incident.type} ${incident.equipment_id} ${incident.equipment_category}`.toLowerCase().includes(query);
            const timeMatch = !cutoff || new Date(incident.timestamp).getTime() >= cutoff;
            return textMatch && (!severity || incident.severity === severity || incident.priority === severity) && (!status || incident.status === status) && (!station || incident.station_id === station) && (!category || incident.equipment_category === category) && timeMatch;
        });
        if (sort === 'timestamp') result.sort((a,b) => new Date(b.timestamp)-new Date(a.timestamp));
        else if (sort === 'severity') result.sort((a,b) => severityRank(b.severity)-severityRank(a.severity));
        else result.sort((a,b) => b.priority_score-a.priority_score);
        $('#incident-results').innerHTML = incidentTable(result);
        $$('#incident-results [data-incident]').forEach(row => row.onclick = () => openIncident(row.dataset.incident));
    };
    controls.forEach(selector => $(selector).addEventListener(selector === '#incident-search' ? 'input' : 'change', update));
    $('#incident-station').value = state.station;
    update();
}

function severityRank(severity) {
    return ({critical: 5, high: 4, warning: 3, medium: 2, low: 1, normal: 0})[severity] || 0;
}

async function anomalyEvidence() {
    $('#view').innerHTML = `<div class="welcome"><div><div class="eyebrow">Rule findings · source telemetry · verification status</div><h2>Anomaly &amp; Evidence</h2><p>An anomaly is a detected observation, not proof of a root cause or independent verification.</p></div><span class="tag">SIMULATED DATA</span></div><div class="empty">Loading anomaly findings…</div>`;
    try {
        const [anomalyResponse, incidentResponse] = await Promise.all([
            api('/api/anomalies'),
            api('/api/incidents?limit=500'),
        ]);
        state.allIncidents = incidentResponse.incidents;
        state.allAnomalies = anomalyResponse.anomalies;
        renderAnomalyEvidence();
    } catch (error) {
        $('#view').innerHTML = `<div class="panel empty"><strong>Could not load anomaly evidence</strong><p>${esc(error.message)}</p></div>`;
    }
}

function renderAnomalyEvidence() {
    const anomalies = state.allAnomalies || [];
    const categoryCounts = anomalies.reduce((counts, anomaly) => {
        const category = anomaly.metric || anomaly.type || 'Explicit event';
        counts[category] = (counts[category] || 0) + 1;
        return counts;
    }, {});
    const entries = Object.entries(categoryCounts).sort((a,b) => b[1]-a[1]);

    $('#view').innerHTML = `
        <div class="welcome"><div><div class="eyebrow">Rule findings · source telemetry · verification status</div><h2>Anomaly &amp; Evidence</h2><p>Threshold violations and explicit event findings returned by the backend detection rules.</p></div><span class="tag">${anomalies.length} FINDINGS</span></div>
        <div class="metrics incident-summary">
            ${metric('Detected anomalies', anomalies.length, 'Rule-based observations', '⌁', 'warn')}
            ${metric('Critical findings', anomalies.filter(item => item.severity === 'critical').length, 'By source event severity', '▲', 'alert')}
            ${metric('Rule categories', entries.length, 'Observed metric or event type', '▤')}
            ${metric('Verification', 'Unavailable', 'No verification engine configured', '○')}
        </div>
        <div class="evidence-overview-grid">
            <section class="panel">
                <div class="panel-head"><div><div class="panel-title">Finding categories</div><div class="panel-sub">Counts from the current processed dataset</div></div><span class="tag">RULE BASED</span></div>
                ${entries.length ? `<div class="category-list">${entries.map(([name,count]) => `<div class="category-item"><span>${esc(name)}</span><b>${count}</b><i style="--bar-width:${Math.max(8,count/Math.max(...entries.map(item=>item[1]))*100)}%"></i></div>`).join('')}</div>` : '<div class="empty">No anomaly findings in the current dataset.</div>'}
            </section>
            <section class="panel verification-note">
                <div class="panel-head"><div><div class="panel-title">Evidence verification</div><div class="panel-sub">No independent verification engine is implemented</div></div><span class="badge">PENDING</span></div>
                <p>Rule crossings and explicit non-normal events are reported as observations. The backend does not compare independent sensors or conflicting signals, so these findings are not marked verified.</p>
                <div class="evidence-state"><b>Supported observation</b><span>A matching source event or configured threshold finding exists.</span></div>
                <div class="evidence-state unavailable"><b>Conclusion status</b><span>Insufficient to confirm a physical cause or service impact.</span></div>
            </section>
        </div>
        <section class="panel table-panel anomaly-table-panel">
            <div class="panel-head"><div><div class="panel-title">Detected anomalies and source evidence</div><div class="panel-sub">Select a related incident to inspect its returned evidence records</div></div><input class="input" id="anomaly-search" placeholder="Search station, metric, event…"></div>
            <div id="anomaly-results"></div>
        </section>`;

    const update = () => {
        const query = $('#anomaly-search').value.trim().toLowerCase();
        const rows = anomalies.filter(anomaly => `${anomaly.anomaly_id} ${anomaly.station_id} ${anomaly.equipment_id} ${anomaly.metric} ${anomaly.type} ${anomaly.explanation}`.toLowerCase().includes(query));
        $('#anomaly-results').innerHTML = rows.length ? `<div class="table-wrap"><table><thead><tr><th>Finding</th><th>Timestamp</th><th>Station / equipment</th><th>Observation</th><th>Rule threshold</th><th>Source</th><th>Severity</th><th>Verification</th><th>Related incident</th></tr></thead><tbody>${rows.map(anomaly => {
            const incident = (state.allIncidents || []).find(item => item.anomaly_ids.includes(anomaly.anomaly_id));
            const expected = anomaly.threshold == null ? 'No numeric threshold' : Array.isArray(anomaly.threshold) ? `${anomaly.threshold[0]}&ndash;${anomaly.threshold[1]}` : anomaly.threshold;
            const observed = Number(anomaly.observed_value);
            let delta = '';
            if (Number.isFinite(observed) && Array.isArray(anomaly.threshold)) {
                delta = observed < anomaly.threshold[0]
                    ? ` &middot; Delta ${(observed-anomaly.threshold[0]).toFixed(2)} below range`
                    : ` &middot; Delta +${(observed-anomaly.threshold[1]).toFixed(2)} above range`;
            } else if (Number.isFinite(observed) && typeof anomaly.threshold === 'number') {
                delta = ` &middot; Delta ${observed > anomaly.threshold ? '+' : ''}${(observed-anomaly.threshold).toFixed(2)}`;
            }
            return `<tr class="${incident ? 'linked-row' : ''}" ${incident ? `data-incident="${esc(incident.incident_id)}"` : ''}><td class="mono">${esc(anomaly.anomaly_id)}</td><td class="mono">${new Date(anomaly.timestamp).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'})}</td><td>${esc(anomaly.station_id)}<div class="mono">${esc(anomaly.equipment_id)}</div></td><td>${esc(anomaly.metric || anomaly.type)} = ${esc(anomaly.observed_value ?? 'event')}${delta}<div class="panel-sub">${esc(anomaly.explanation)}</div>${anomaly.raw_log ? `<div class="mono anomaly-source-log">${esc(anomaly.raw_log)}</div>` : ''}</td><td>${esc(expected)}</td><td>${esc(anomaly.source || 'unknown')}<div class="mono">${esc(anomaly.record_id)}</div></td><td><span class="sev ${esc(anomaly.severity)}">${esc(anomaly.severity)}</span></td><td><span class="badge">PENDING</span></td><td>${incident ? `<span class="mono">${esc(incident.incident_id)}</span>` : 'No grouped incident'}</td></tr>`;
        }).join('')}</tbody></table></div>` : '<div class="empty">No findings match this search.</div>';
        $$('#anomaly-results [data-incident]').forEach(row => row.onclick = () => {
            state.selectedIncidentId = row.dataset.incident;
            state.investigation = null;
            state.page = 'Root Cause Analysis';
            render();
        });
    };
    $('#anomaly-search').oninput = update;
    update();
}

function rootCause() {
    if (!state.allIncidents) {
        $('#view').innerHTML = `<div class="welcome"><div><div class="eyebrow">Evidence-led investigation</div><h2>Root Cause Analysis</h2><p>Loading current incident list…</p></div></div><div class="empty">Loading incidents…</div>`;
        api('/api/incidents?limit=500')
            .then(response => {
                state.allIncidents = response.incidents;
                rootCause();
            })
            .catch(error => {
                $('#view').innerHTML = `<div class="panel empty"><strong>Could not load incidents</strong><p>${esc(error.message)}</p></div>`;
            });
        return;
    }
    const incidents = state.allIncidents || state.data.incidents || [];
    if (!state.selectedIncidentId && incidents.length) state.selectedIncidentId = incidents[0].incident_id;
    if (!state.selectedIncidentId) {
        $('#view').innerHTML = `<div class="welcome"><div><div class="eyebrow">Evidence-led investigation</div><h2>Root Cause Analysis</h2><p>Generate a scenario or upload records to create an incident for review.</p></div></div><div class="panel empty">No incidents are available in the current dataset.</div>`;
        return;
    }
    const incidentId = state.selectedIncidentId;
    if (state.investigation?.incident?.incident_id === incidentId) {
        renderRootCause(state.investigation);
        return;
    }
    $('#view').innerHTML = `<div class="welcome"><div><div class="eyebrow">Evidence aggregation · deterministic priority · cause assessment</div><h2>Root Cause Analysis</h2><p>Loading source incident and linked evidence…</p></div></div><div class="empty">Loading investigation ${esc(incidentId)}…</div>`;
    api(`/api/incidents/${encodeURIComponent(incidentId)}`)
        .then(detail => {
            if (state.page !== 'Root Cause Analysis' || state.selectedIncidentId !== incidentId) return;
            state.investigation = detail;
            renderRootCause(detail);
        })
        .catch(error => {
            $('#view').innerHTML = `<div class="panel empty"><strong>Could not load investigation</strong><p>${esc(error.message)}</p></div>`;
        });
}

function renderRootCause(detail) {
    const incident = detail.incident;
    const incidents = state.allIncidents || state.data.incidents || [];
    const options = incidents.map(item => `<option value="${esc(item.incident_id)}" ${item.incident_id === incident.incident_id ? 'selected' : ''}>${esc(item.incident_id)} · ${esc(item.station_id)} · ${esc(item.type)}</option>`).join('');
    const pipeline = [
        ['Input received', true, null],
        ['Processed and grouped', true, null],
        ['Rule anomaly detection', true, null, detail.anomalies.length ? `${detail.anomalies.length} linked finding(s)` : 'Completed · no linked anomaly finding'],
        ['Supporting evidence returned', true, null, `${detail.evidence.length} source record(s)`],
        ['AI evidence review', null, null, 'Advisory only; available when Groq is online'],
        ['Priority assessed', true, null],
        ['Root-cause engine', null, null],
        ['AI investigation explanation', null, null, 'Generated on demand when Groq is online'],
        ['Report generation', false, null, 'Available on demand from Reports'],
    ];

    $('#view').innerHTML = `
        <div class="welcome"><div><div class="eyebrow">Evidence-led investigation</div><h2>Root Cause Analysis</h2><p>Observations and priority are shown separately from unverified causal hypotheses.</p></div><div class="actions"><button class="btn" id="export-investigation">Export summary</button><button class="btn" onclick="navigate('Incident Explorer')">Back to incidents</button></div></div>
        <div class="investigation-toolbar"><label class="field-label" for="investigation-select">Selected incident</label><select class="select" id="investigation-select">${options}</select><span class="badge">${esc(incident.status.toUpperCase())}</span></div>
        <div class="investigation-grid">
            <section class="panel investigation-summary">
                <div class="panel-head"><div><div class="panel-title">Incident summary</div><div class="panel-sub">${esc(incident.incident_id)} · ${new Date(incident.timestamp).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'})} IST</div></div><span class="sev ${esc(incident.severity)}">${esc(incident.severity)}</span></div>
                <h3>${esc(incident.type.replaceAll('_',' '))}</h3>
                <div class="detail-grid"><div class="detail-cell"><small>STATION</small><b>${esc(incident.station_id)}</b></div><div class="detail-cell"><small>EQUIPMENT</small><b>${esc(incident.equipment_id)}</b></div><div class="detail-cell"><small>PRIORITY SCORE</small><b>${incident.priority_score}/100 · ${esc(incident.priority)}</b></div><div class="detail-cell"><small>STATUS</small><b>${esc(incident.status)}</b></div></div>
                <div class="evidence-state"><b>Priority explanation</b><span>${esc(incident.explanation)}</span></div>
            </section>
            <section class="panel">
                <div class="panel-head"><div><div class="panel-title">Evidence summary</div><div class="panel-sub">${detail.evidence.length} source record(s) · ${detail.anomalies.length} linked rule finding(s)</div></div><span class="badge">OBSERVED DATA</span></div>
                ${detail.anomalies.length ? detail.anomalies.map(anomaly => `<div class="evidence-card"><b>${esc(anomaly.metric || anomaly.type)}: ${esc(anomaly.observed_value ?? 'event')}</b><span>${new Date(anomaly.timestamp).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'})} · ${esc(anomaly.station_id)} · ${esc(anomaly.equipment_id)}</span><p>${esc(anomaly.explanation)} ${anomaly.threshold != null ? `Configured threshold: ${esc(JSON.stringify(anomaly.threshold))}.` : ''}</p></div>`).join('') : '<div class="empty compact-empty">No rule anomaly is linked to this incident. The incident was grouped from event severity or explicit event data.</div>'}
                <div class="verification-callout"><b>AI evidence review · advisory</b><span>Groq can assess evidence quality and uncertainty. This review cannot confirm a root cause or change deterministic priority.</span><button class="btn" id="ai-verify-incident">Review evidence with AI</button><div id="ai-verification-result" class="ai-operation-result" aria-live="polite"></div></div>
                <div class="evidence-state unavailable"><b>Evidence gaps</b><span>Maintenance history, independent sensor comparisons, adjacent-equipment correlations, and verified service-impact data are not available from the current APIs. Conflicting signals are not evaluated.</span></div>
            </section>
            <section class="panel">
                <div class="panel-head"><div><div class="panel-title">Diagnostic checks</div><div class="panel-sub">Backend suggestions · not causal findings</div></div><span class="badge">UNCONFIRMED</span></div>
                <div class="cause-unavailable"><b>AI explanation available on demand</b><span>The deterministic processor still supplies incident grouping and priority. Groq explains these observations but does not rank or confirm causes.</span><button class="btn primary" id="ai-explain-incident">Generate AI explanation</button><div id="ai-explanation-result" class="ai-operation-result" aria-live="polite"></div></div>
                ${detail.diagnostic_checks.map((check,index) => `<div class="diagnostic-row"><b>0${index+1}</b><span>${esc(check)}</span></div>`).join('')}
                <p class="panel-sub cause-caution">These checks are recommendations. They do not establish that a listed subsystem caused this incident.</p>
            </section>
            <section class="panel pipeline-panel">
                <div class="panel-head"><div><div class="panel-title">Investigation pipeline</div><div class="panel-sub">Only backend-confirmed stages are marked complete</div></div><span class="tag">CURRENT STATUS</span></div>
                <ol class="pipeline-list">${pipeline.map(([label,complete,timestamp,note]) => `<li class="${complete === null ? 'unavailable' : complete ? 'complete' : 'pending'}"><i></i><div><b>${label}</b><span>${complete === null ? 'Unavailable' : note || 'Completed'}${timestamp ? ` · ${new Date(timestamp).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'})}` : ''}</span></div></li>`).join('')}</ol>
            </section>
            <section class="panel source-evidence-panel">
                <div class="panel-head"><div><div class="panel-title">Supporting source records</div><div class="panel-sub">Raw records returned by the incident evidence endpoint</div></div><span class="tag">${detail.evidence.length} RECORDS</span></div>
                ${detail.evidence.length ? detail.evidence.map(event => `<div class="evidence-record"><div><b>${esc(event.record_id)}</b><span>${new Date(event.timestamp).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'})}</span></div><p>${esc(event.raw_log || JSON.stringify(event))}</p></div>`).join('') : '<div class="empty compact-empty">No linked raw records were returned.</div>'}
            </section>
        </div>`;

    $('#investigation-select').onchange = event => {
        state.selectedIncidentId = event.target.value;
        state.investigation = null;
        rootCause();
    };
    $('#ai-verify-incident').onclick = async event => {
        const button = event.currentTarget;
        const target = $('#ai-verification-result');
        button.disabled = true;
        target.innerHTML = '<div class="ai-operation-loading">Reviewing the supplied evidence…</div>';
        try {
            const response = await window.MetroPulseAIAPI.verify(incident.incident_id);
            target.innerHTML = `<div class="ai-operation-content"><b>Advisory evidence review · not a confirmed cause</b><pre>${esc(JSON.stringify(response.verification, null, 2))}</pre></div>`;
        } catch (error) {
            target.innerHTML = `<div class="ai-operation-error">${esc(error.message)} <button class="btn ai-operation-retry" data-ai-retry="verify">Retry</button></div>`;
            target.querySelector('[data-ai-retry]').onclick = () => $('#ai-verify-incident').click();
        } finally {
            button.disabled = false;
        }
    };
    $('#ai-explain-incident').onclick = async event => {
        const button = event.currentTarget;
        const target = $('#ai-explanation-result');
        button.disabled = true;
        target.innerHTML = '<div class="ai-operation-loading">Preparing an evidence-grounded explanation…</div>';
        try {
            const response = await window.MetroPulseAIAPI.explain(incident.incident_id);
            target.innerHTML = `<div class="ai-operation-content"><b>AI-generated advisory · ${esc(response.incident_id)}</b><pre>${esc(response.explanation)}</pre></div>`;
        } catch (error) {
            target.innerHTML = `<div class="ai-operation-error">${esc(error.message)} <button class="btn ai-operation-retry" data-ai-retry="explain">Retry</button></div>`;
            target.querySelector('[data-ai-retry]').onclick = () => $('#ai-explain-incident').click();
        } finally {
            button.disabled = false;
        }
    };
    $('#export-investigation').onclick = () => downloadText(`metropulse-${incident.incident_id}-investigation.txt`, investigationReport(detail));
}

function investigationReport(detail) {
    const incident = detail.incident;
    return [
        'MetroPulse by The80 — Simulated Investigation Summary',
        `Incident: ${incident.incident_id}`,
        `Type: ${incident.type}`,
        `Timestamp: ${incident.timestamp}`,
        `Station / equipment: ${incident.station_id} / ${incident.equipment_id}`,
        `Severity / priority: ${incident.severity} / ${incident.priority} (${incident.priority_score}/100)`,
        `Status: ${incident.status}`,
        `Priority explanation: ${incident.explanation}`,
        `Linked anomalies: ${detail.anomalies.length}`,
        `Source evidence records: ${detail.evidence.length}`,
        'AI evidence review: advisory and available on demand when Groq is configured; it does not independently verify observations.',
        'Root cause: unconfirmed; no cause-ranking engine is implemented. AI explanations contextualize the supplied observations only.',
        'Recommended diagnostic checks:',
        ...detail.diagnostic_checks.map(check => `- ${check}`),
        '',
        'All data in this report is simulated or user-provided sample input.',
    ].join('\n');
}

async function reports() {
    $('#view').innerHTML = `<div class="welcome"><div><div class="eyebrow">Traceable summaries · dataset exports</div><h2>Reports</h2><p>Reports summarize the current processed simulated dataset. No unsupported PDF export is offered.</p></div><span class="tag">SIMULATED DATA</span></div><div class="empty">Loading report data…</div>`;
    try {
        const [incidentResponse, anomalyResponse, historyResponse] = await Promise.all([
            api('/api/incidents?limit=500'),
            api('/api/anomalies'),
            api('/api/ingestion/history'),
        ]);
        state.allIncidents = incidentResponse.incidents;
        state.allAnomalies = anomalyResponse.anomalies;
        state.ingestionHistory = historyResponse.history;
        renderReports();
    } catch (error) {
        $('#view').innerHTML = `<div class="panel empty"><strong>Could not load report data</strong><p>${esc(error.message)}</p></div>`;
    }
}

function renderReports() {
    const incidents = state.allIncidents || [];
    const anomalies = state.allAnomalies || [];
    const scenarioRuns = (state.ingestionHistory || []).filter(entry => entry.format === 'SIMULATION');
    const stations = state.data.stations;
    const periodHours = state.reportFilters.period === '24' ? 24 : state.reportFilters.period === '168' ? 168 : 0;
    const cutoff = periodHours ? Date.now() - periodHours * 60 * 60 * 1000 : 0;
    const filtered = incidents.filter(incident =>
        (!state.reportFilters.severity || incident.severity === state.reportFilters.severity || incident.priority === state.reportFilters.severity) &&
        (!state.reportFilters.station || incident.station_id === state.reportFilters.station) &&
        (!state.reportFilters.status || incident.status === state.reportFilters.status) &&
        (!state.reportFilters.category || incident.equipment_category === state.reportFilters.category) &&
        (!cutoff || new Date(incident.timestamp).getTime() >= cutoff)
    );
    const severityCounts = filtered.reduce((counts, incident) => {
        counts[incident.severity] = (counts[incident.severity] || 0) + 1;
        return counts;
    }, {});
    const stationCounts = filtered.reduce((counts, incident) => {
        counts[incident.station_id] = (counts[incident.station_id] || 0) + 1;
        return counts;
    }, {});
    const topStations = Object.entries(stationCounts).sort((a,b) => b[1]-a[1]).slice(0,5);
    const topAnomalies = Object.entries(anomalies.reduce((counts, anomaly) => {
        const category = anomaly.metric || anomaly.type || 'Explicit event';
        counts[category] = (counts[category] || 0) + 1;
        return counts;
    }, {})).sort((a,b) => b[1]-a[1]).slice(0,5);

    $('#view').innerHTML = `
        <div class="welcome"><div><div class="eyebrow">Traceable summaries · dataset exports</div><h2>Reports</h2><p>Incident and anomaly summaries from the current backend dataset · simulation mode</p></div><div class="actions"><button class="btn" id="export-incidents-csv">Export incidents CSV</button><button class="btn primary" id="export-report-json">Export report JSON</button></div></div>
        <div class="report-filters"><label>Severity<select class="select" id="report-severity"><option value="">All severity</option>${['critical','high','medium','low','normal'].map(value => `<option value="${value}">${value}</option>`).join('')}</select></label><label>Status<select class="select" id="report-status"><option value="">All status</option><option value="open">Open</option><option value="monitoring">Monitoring</option></select></label><label>Station<select class="select" id="report-station"><option value="">All stations</option>${stations.map(station => `<option value="${station.station_id}">${esc(station.name)} · ${station.station_id}</option>`).join('')}</select></label><label>Equipment category<select class="select" id="report-category"><option value="">All categories</option>${[...new Set(incidents.map(item=>item.equipment_category))].sort().map(value => `<option value="${esc(value)}">${esc(value)}</option>`).join('')}</select></label><label>Period<select class="select" id="report-period"><option value="all">All time</option><option value="24">Last 24 hours</option><option value="168">Last 7 days</option></select></label><span class="badge">${filtered.length} MATCHING INCIDENTS</span></div>
        <div class="metrics incident-summary">
            ${metric('Incidents', filtered.length, 'Current filter selection', '▤')}
            ${metric('Critical', filtered.filter(item=>item.priority==='critical').length, 'Priority critical', '▲', 'alert')}
            ${metric('Open', filtered.filter(item=>item.status==='open').length, 'Current investigation status', '◉', 'warn')}
            ${metric('Anomalies', anomalies.length, 'Current whole dataset', '⌁', 'warn')}
        </div>
        <div class="report-grid">
            <section class="panel"><div class="panel-head"><div><div class="panel-title">Incidents by severity</div><div class="panel-sub">Filtered incident set</div></div></div>${Object.keys(severityCounts).length ? `<div class="report-bars">${Object.entries(severityCounts).sort((a,b)=>severityRank(b[0])-severityRank(a[0])).map(([name,count]) => `<div class="report-bar-row"><span>${esc(name)}</span><i><b style="width:${count/Math.max(...Object.values(severityCounts))*100}%"></b></i><strong>${count}</strong></div>`).join('')}</div>` : '<div class="empty">No incidents match these filters.</div>'}</section>
            <section class="panel"><div class="panel-head"><div><div class="panel-title">Most affected stations</div><div class="panel-sub">Grouped incidents by station</div></div></div>${topStations.length ? `<div class="report-bars">${topStations.map(([station,count]) => `<div class="report-bar-row"><span>${esc(station)}</span><i><b style="width:${count/Math.max(...topStations.map(item=>item[1]))*100}%"></b></i><strong>${count}</strong></div>`).join('')}</div>` : '<div class="empty">No station totals available.</div>'}</section>
            <section class="panel"><div class="panel-head"><div><div class="panel-title">Common anomaly categories</div><div class="panel-sub">Whole processed dataset</div></div></div>${topAnomalies.length ? `<div class="report-bars">${topAnomalies.map(([name,count]) => `<div class="report-bar-row"><span>${esc(name)}</span><i><b style="width:${count/Math.max(...topAnomalies.map(item=>item[1]))*100}%"></b></i><strong>${count}</strong></div>`).join('')}</div>` : '<div class="empty">No anomaly categories available.</div>'}</section>
            <section class="panel"><div class="panel-head"><div><div class="panel-title">Investigation coverage</div><div class="panel-sub">Available backend outputs</div></div><span class="badge">PARTIAL</span></div><div class="report-availability"><p><b>Priority:</b> deterministic score is available on each incident.</p><p><b>Evidence:</b> source records and linked rule findings are available per incident.</p><p><b>AI evidence review:</b> advisory assessment is available on demand when Groq is online; it does not confirm causes.</p><p><b>AI explanation:</b> contextualizes the deterministic results and source evidence when Groq is online.</p></div></section>
            <section class="panel"><div class="panel-head"><div><div class="panel-title">Scenario runs</div><div class="panel-sub">Generated simulation inputs in ingestion history</div></div><span class="tag">${scenarioRuns.length} RUNS</span></div>${scenarioRuns.length ? `<div class="scenario-runs">${scenarioRuns.slice(0,6).map(entry => `<div class="setting-row"><span>${esc(entry.filename.replace('scenario_','').replace('.json',''))}<small>${new Date(entry.created_at).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'})}</small></span><b>${entry.accepted} events</b></div>`).join('')}</div>` : '<div class="empty">No generated scenarios in ingestion history.</div>'}</section>
        </div>
        <section class="panel report-timeline"><div class="panel-head"><div><div class="panel-title">Events processed over time</div><div class="panel-sub">Hourly counts from the current dashboard response</div></div><span class="tag">SIMULATED</span></div>${bars(state.data.events_by_hour)}</section>
        <section class="panel table-panel report-incident-table"><div class="panel-head"><div><div class="panel-title">Incident report data</div><div class="panel-sub">${filtered.length} filtered incident records</div></div></div><div id="report-incidents"></div></section>`;

    $('#report-severity').value = state.reportFilters.severity;
    $('#report-status').value = state.reportFilters.status;
    $('#report-station').value = state.reportFilters.station;
    $('#report-category').value = state.reportFilters.category;
    $('#report-period').value = state.reportFilters.period;
    $('#report-incidents').innerHTML = incidentTable(filtered);
    $$('#report-incidents [data-incident]').forEach(row => row.onclick = () => openIncident(row.dataset.incident));
    $('#report-severity').onchange = event => {state.reportFilters.severity = event.target.value; renderReports()};
    $('#report-status').onchange = event => {state.reportFilters.status = event.target.value; renderReports()};
    $('#report-station').onchange = event => {state.reportFilters.station = event.target.value; renderReports()};
    $('#report-category').onchange = event => {state.reportFilters.category = event.target.value; renderReports()};
    $('#report-period').onchange = event => {state.reportFilters.period = event.target.value; renderReports()};
    $('#export-incidents-csv').onclick = () => downloadText('metropulse-incidents.csv', incidentsCsv(filtered), 'text/csv');
    $('#export-report-json').onclick = () => downloadText('metropulse-report.json', JSON.stringify({simulated:true,generated_at:new Date().toISOString(),filters:state.reportFilters,incidents:filtered,anomalies},null,2), 'application/json');
}

function incidentsCsv(incidents) {
    const columns = ['incident_id','timestamp','station_id','equipment_id','equipment_category','type','severity','status','priority','priority_score','event_count'];
    const quote = value => `"${String(value ?? '').replaceAll('"','""')}"`;
    return [columns.join(','), ...incidents.map(incident => columns.map(column => quote(incident[column])).join(','))].join('\n');
}

async function settings() {
    $('#view').innerHTML = `<div class="welcome"><div><div class="eyebrow">Supported configuration · service status</div><h2>Settings</h2><p>Read-only values reflect backend configuration. Secrets are never displayed.</p></div><span class="tag">BACKEND MANAGED</span></div><div class="empty">Loading backend settings…</div>`;
    try {
        const [config, health, aiStatus] = await Promise.all([api('/api/config'), api('/api/health'), window.MetroPulseAIAPI.status()]);
        state.config = config;
        state.health = health;
        state.aiStatus = aiStatus;
        renderSettings();
    } catch (error) {
        $('#view').innerHTML = `<div class="panel empty"><strong>Could not load settings</strong><p>${esc(error.message)}</p></div>`;
    }
}

function renderSettings() {
    const config = state.config;
    const health = state.health;
    $('#view').innerHTML = `
        <div class="welcome"><div><div class="eyebrow">Supported configuration · service status</div><h2>Settings</h2><p>Configuration below is read-only and supplied by the backend.</p></div><span class="health-pill healthy"><i></i>${esc(health.status.toUpperCase())}</span></div>
        <div class="settings-grid">
            <section class="panel"><div class="panel-head"><div><div class="panel-title">Demo network</div><div class="panel-sub">Fictional network configuration</div></div><span class="badge">READ ONLY</span></div><div class="setting-row"><span>Mode</span><b>${esc(health.mode)}</b></div><div class="setting-row"><span>Stations</span><b>${config.network.stations}</b></div><div class="setting-row"><span>Network identity</span><b>Fictional Pune Metro</b></div><div class="setting-row"><span>Data source</span><b>Generated or uploaded sample data</b></div></section>
            <section class="panel"><div class="panel-head"><div><div class="panel-title">Detection thresholds</div><div class="panel-sub">Configured in backend/services/processor.py</div></div><span class="badge">RULE BASED</span></div><div class="setting-table"><div class="setting-row setting-header"><span>Metric</span><span>Threshold</span></div>${Object.entries(config.thresholds).map(([metricName,value]) => `<div class="setting-row"><span>${esc(metricName.replaceAll('_',' '))}</span><b>${metricName==='voltage_v'?`${value}–420 V`: `${esc(value)}${metricName==='temperature_c'?' °C':metricName==='latency_ms'?' ms':''}`}</b></div>`).join('')}</div></section>
            <section class="panel"><div class="panel-head"><div><div class="panel-title">Supported scenarios</div><div class="panel-sub">Available through /api/simulation/generate</div></div><span class="badge">${Object.keys(config.scenarios).length} SCENARIOS</span></div><div class="setting-table">${Object.entries(config.scenarios).map(([key,value]) => `<div class="setting-row"><span>${esc(key.replaceAll('_',' '))}<small>${esc(value.event_type)} · ${esc(value.equipment_category)}</small></span><b>${esc(value.severity)}</b></div>`).join('')}</div></section>
            <section class="panel"><div class="panel-head"><div><div class="panel-title">Analysis capabilities</div><div class="panel-sub">LLM output is advisory and follows deterministic evidence</div></div></div><div class="setting-row"><span>Rule detection</span><b class="capability-enabled">Available</b></div><div class="setting-row"><span>Evidence retrieval</span><b class="capability-enabled">Available per incident</b></div><div class="setting-row"><span>AI evidence review</span><b>${state.aiStatus.available ? 'Available · advisory' : 'Unavailable'}</b></div><div class="setting-row"><span>AI provider / model</span><b>${esc(state.aiStatus.available ? `${state.aiStatus.provider} · ${state.aiStatus.model}` : state.aiStatus.status.replaceAll('_',' '))}</b></div><p class="panel-sub settings-note">No provider secrets or API keys are stored in or returned to the frontend. An AI review never confirms a cause or controls infrastructure.</p></section>
            <section class="panel settings-reset"><div class="panel-head"><div><div class="panel-title">Demo data controls</div><div class="panel-sub">Reset replaces the current in-memory demo dataset.</div></div><span class="badge">DESTRUCTIVE</span></div><button class="btn danger-button" id="settings-reset">Reset demo dataset</button></section>
        </div>`;
    $('#settings-reset').onclick = resetDemo;
}

async function resetDemo() {
    if (!window.confirm('Reset the in-memory demo dataset and clear uploaded/scenario records?')) return;
    try {
        await api('/api/simulation/control?action=reset', {method:'POST'});
        state.data = await api('/api/dashboard');
        state.allIncidents = null;
        state.allAnomalies = null;
        state.selectedIncidentId = null;
        state.investigation = null;
        state.scenario = 'baseline';
        state.lastScenarioEvents = 0;
        state.reportFilters = {severity:'',station:'',status:'',category:'',period:'all'};
        render();
        toast('Demo dataset reset to baseline.');
    } catch (error) {
        toast(error.message);
    }
}

function downloadText(filename, contents, type='text/plain') {
    const blob = new Blob([contents], {type:`${type};charset=utf-8`});
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
}

async function openIncident(id) {
    try {
        const detail = await api(`/api/incidents/${encodeURIComponent(id)}`);
        const incident = detail.incident;
        const root = document.createElement('div');
        root.innerHTML = `
            <div class="drawer-backdrop"></div>
            <aside class="drawer" role="dialog" aria-modal="true" aria-labelledby="incident-drawer-title">
                <button class="drawer-close" aria-label="Close incident details">×</button>
                <div class="detail-id">${esc(incident.incident_id)} · INCIDENT DETAIL</div>
                <h2 id="incident-drawer-title">${esc(incident.type.replaceAll('_',' '))}</h2>
                <span class="sev ${esc(incident.severity)}">${esc(incident.severity)} SEVERITY</span>
                <div class="detail-grid">
                    <div class="detail-cell"><small>STATION</small><b>${esc(incident.station_id)}</b></div>
                    <div class="detail-cell"><small>EQUIPMENT</small><b>${esc(incident.equipment_id)}</b></div>
                    <div class="detail-cell"><small>PRIORITY</small><b>${esc(incident.priority.toUpperCase())} · ${incident.priority_score}/100</b></div>
                    <div class="detail-cell"><small>STATUS</small><b>${esc(incident.status.toUpperCase())}</b></div>
                </div>
                <div class="detail-block"><h3>Why this was prioritized</h3><div class="evidence readable-evidence">${esc(incident.explanation)}</div><p class="panel-sub">This deterministic prototype score uses source severity, linked event count, and rule findings.</p></div>
                <div class="detail-block"><h3>Observed findings · ${detail.anomalies.length}</h3>${detail.anomalies.length ? detail.anomalies.map(anomaly => `<div class="evidence">${new Date(anomaly.timestamp).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'})}<br>${esc(anomaly.metric || anomaly.type)} = ${esc(anomaly.observed_value)} ${anomaly.threshold != null ? `(configured threshold ${esc(JSON.stringify(anomaly.threshold))})` : ''}<br>${esc(anomaly.explanation)}</div>`).join('') : '<div class="panel-sub">No threshold anomaly is attached. Event severity and type remain source observations.</div>'}</div>
                <div class="verification-callout"><b>Verification pending</b><span>No independent verification engine is configured. An anomaly does not confirm a cause.</span></div>
                <div class="detail-block"><h3>Supporting raw records · ${detail.evidence.length}</h3>${detail.evidence.length ? detail.evidence.map(event => `<div class="evidence">${esc(event.raw_log || JSON.stringify(event))}</div>`).join('') : '<div class="panel-sub">No source records were returned.</div>'}</div>
                <div class="detail-block"><h3>Suggested diagnostic checks</h3>${detail.diagnostic_checks.map(check => `<div class="evidence readable-evidence">• ${esc(check)}</div>`).join('')}</div>
                <div class="actions drawer-actions"><button class="btn primary" id="drawer-root-cause">Open investigation workspace</button><button class="btn" id="drawer-evidence">View anomaly evidence</button></div>
                <p class="panel-sub">${esc(detail.note)} All records are simulated or user-provided sample input.</p>
            </aside>`;
        document.body.append(root);
        const close = () => root.remove();
        $('.drawer-close', root).onclick = close;
        $('.drawer-backdrop', root).onclick = close;
        $('#drawer-root-cause', root).onclick = () => {
            state.selectedIncidentId = incident.incident_id;
            state.investigation = detail;
            close();
            state.page = 'Root Cause Analysis';
            render();
        };
        $('#drawer-evidence', root).onclick = () => {
            state.selectedIncidentId = incident.incident_id;
            close();
            state.page = 'Anomaly & Evidence';
            render();
        };
    } catch (error) {
        toast(error.message);
    }
}
