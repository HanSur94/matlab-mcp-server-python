const REFRESH_INTERVAL = 10000;
let currentRange = 1; // hours
const charts = {};

async function fetchJSON(url) {
    try {
        const res = await fetch(url);
        return await res.json();
    } catch (e) {
        console.error('Fetch error:', e);
        return null;
    }
}

function formatUptime(seconds) {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
    if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h`;
    return `${(seconds / 86400).toFixed(1)}d`;
}

async function updateCurrent() {
    const data = await fetchJSON('/dashboard/api/current');
    if (!data) return;

    // Health
    const health = await fetchJSON('/health');
    if (health) {
        document.getElementById('status-dot').className = `dot ${health.status}`;
        document.getElementById('status-text').textContent = health.status.charAt(0).toUpperCase() + health.status.slice(1);
        document.getElementById('uptime').textContent = `Up ${formatUptime(health.uptime_seconds)}`;
    }

    // Gauges
    document.getElementById('gauge-pool').textContent = `${data.pool.utilization_pct.toFixed(0)}%`;
    document.getElementById('gauge-jobs').textContent = data.jobs.active;
    document.getElementById('gauge-sessions').textContent = data.sessions.active;

    const errRate = data.errors.total > 0 ? (data.errors.total / (health ? health.uptime_seconds / 60 : 1)).toFixed(2) : '0';
    document.getElementById('gauge-errors').textContent = errRate;
}

async function updateCharts() {
    const metrics = [
        { id: 'chart-pool', metric: 'pool.utilization_pct', title: 'Pool Utilization (%)', type: 'scatter', fill: 'tozeroy' },
        { id: 'chart-jobs', metric: 'jobs.completed_total', title: 'Jobs Completed', type: 'bar' },
        { id: 'chart-exec', metric: 'jobs.avg_execution_ms', title: 'Avg Execution Time (ms)', type: 'scatter' },
        { id: 'chart-sessions', metric: 'sessions.active_count', title: 'Active Sessions', type: 'scatter' },
        { id: 'chart-memory', metric: 'system.memory_mb', title: 'Memory (MB)', type: 'scatter' },
    ];

    for (const m of metrics) {
        const result = await fetchJSON(`/dashboard/api/history?metric=${m.metric}&hours=${currentRange}`);
        if (!result || !result.data) continue;

        const x = result.data.map(d => d.timestamp);
        const y = result.data.map(d => d.value);

        const trace = { x, y, type: m.type, name: m.title };
        if (m.fill) trace.fill = m.fill;
        trace.line = { color: '#1a1a2e' };

        const layout = {
            margin: { t: 10, r: 10, b: 30, l: 50 },
            height: 200,
            xaxis: { type: 'date' },
            yaxis: { title: '' },
        };

        if (charts[m.id]) {
            Plotly.react(m.id, [trace], layout);
        } else {
            Plotly.newPlot(m.id, [trace], layout, { responsive: true, displayModeBar: false });
            charts[m.id] = true;
        }
    }

    // P95 overlay on execution time chart
    const p95 = await fetchJSON(`/dashboard/api/history?metric=jobs.p95_execution_ms&hours=${currentRange}`);
    if (p95 && p95.data && p95.data.length > 0) {
        const avgResult = await fetchJSON(`/dashboard/api/history?metric=jobs.avg_execution_ms&hours=${currentRange}`);
        const traces = [];
        if (avgResult && avgResult.data) {
            traces.push({
                x: avgResult.data.map(d => d.timestamp),
                y: avgResult.data.map(d => d.value),
                type: 'scatter', name: 'Avg', line: { color: '#1a1a2e' },
            });
        }
        traces.push({
            x: p95.data.map(d => d.timestamp),
            y: p95.data.map(d => d.value),
            type: 'scatter', name: 'P95', line: { color: '#f44336', dash: 'dash' },
        });
        const layout = { margin: { t: 10, r: 10, b: 30, l: 50 }, height: 200, xaxis: { type: 'date' } };
        Plotly.react('chart-exec', traces, layout);
    }
}

let currentEventFilter = '';

function filterEvents(type) {
    currentEventFilter = type;
    updateEvents();
}

async function updateEvents() {
    const typeParam = currentEventFilter ? `&type=${currentEventFilter}` : '';
    const result = await fetchJSON(`/dashboard/api/events?limit=50${typeParam}`);
    if (!result || !result.events) return;

    const tbody = document.getElementById('events-body');
    tbody.innerHTML = '';
    for (const ev of result.events) {
        const tr = document.createElement('tr');
        const ts = new Date(ev.timestamp).toLocaleTimeString();
        let details = '';
        try { details = JSON.stringify(JSON.parse(ev.details)); } catch { details = ev.details; }
        const tdTs = document.createElement('td');
        tdTs.textContent = ts;
        const tdType = document.createElement('td');
        tdType.textContent = ev.event_type;
        tdType.className = `type type-${ev.event_type.replace(/[^a-z0-9_]/gi, '_')}`;
        const tdDetails = document.createElement('td');
        tdDetails.textContent = details;
        tr.append(tdTs, tdType, tdDetails);
        tbody.appendChild(tr);
    }
}

function setRange(evt, hours) {
    currentRange = hours;
    document.querySelectorAll('.time-range button').forEach(b => b.classList.remove('active'));
    evt.target.classList.add('active');
    updateCharts();
}

async function refresh() {
    await updateCurrent();
    await updateCharts();
    await updateEvents();
}

// Wait for Plotly.js to load, then start
window.plotlyReady.then(function() {
    refresh();
    setInterval(refresh, REFRESH_INTERVAL);
});
