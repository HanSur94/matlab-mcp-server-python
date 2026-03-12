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
        // Engine counts
        document.getElementById('gauge-engines').textContent = `${health.engines.busy}/${health.engines.total}`;
    }

    // Gauges
    const util = data.pool && data.pool.utilization_pct != null ? data.pool.utilization_pct.toFixed(0) : '0';
    document.getElementById('gauge-pool').textContent = `${util}%`;
    document.getElementById('gauge-jobs').textContent = data.jobs ? data.jobs.active : 0;
    document.getElementById('gauge-completed').textContent = data.jobs ? data.jobs.completed_total : 0;
    document.getElementById('gauge-sessions').textContent = data.sessions ? data.sessions.active : 0;

    const errRate = (data.errors && data.errors.total > 0 && health)
        ? (data.errors.total / (health.uptime_seconds / 60)).toFixed(2)
        : '0';
    document.getElementById('gauge-errors').textContent = errRate;

    const avgMs = (data.jobs && data.jobs.avg_execution_ms != null)
        ? `${data.jobs.avg_execution_ms.toFixed(0)}ms`
        : '-';
    document.getElementById('gauge-avg-exec').textContent = avgMs;
}

async function updateCharts() {
    const metrics = [
        { id: 'chart-pool', metric: 'pool.utilization_pct', title: 'Pool Utilization (%)', color: '#1a73e8', fill: 'tozeroy' },
        { id: 'chart-jobs', metric: 'jobs.completed_total', title: 'Jobs Completed', color: '#4caf50', type: 'bar' },
        { id: 'chart-exec', metric: 'jobs.avg_execution_ms', title: 'Avg Execution (ms)', color: '#1a1a2e' },
        { id: 'chart-sessions', metric: 'sessions.active_count', title: 'Active Sessions', color: '#9c27b0', fill: 'tozeroy' },
        { id: 'chart-memory', metric: 'system.memory_mb', title: 'Memory (MB)', color: '#ff9800', fill: 'tozeroy' },
        { id: 'chart-errors', metric: 'errors.total', title: 'Total Errors', color: '#f44336', type: 'bar' },
    ];

    for (const m of metrics) {
        const result = await fetchJSON(`/dashboard/api/history?metric=${m.metric}&hours=${currentRange}`);
        const el = document.getElementById(m.id);
        if (!el) continue;

        if (!result || !result.data || result.data.length === 0) {
            if (!charts[m.id]) {
                el.innerHTML = '<div class="no-data">No data yet</div>';
            }
            continue;
        }

        const x = result.data.map(d => d.timestamp);
        const y = result.data.map(d => d.value);

        const trace = {
            x, y,
            type: m.type || 'scatter',
            mode: m.type === 'bar' ? undefined : 'lines',
            name: m.title,
            line: { color: m.color, width: 2 },
            marker: { color: m.color },
        };
        if (m.fill) trace.fill = m.fill;
        if (m.fill) trace.fillcolor = m.color + '20';

        const layout = {
            margin: { t: 8, r: 12, b: 30, l: 50 },
            height: 200,
            xaxis: { type: 'date', gridcolor: '#f0f0f0' },
            yaxis: { gridcolor: '#f0f0f0', rangemode: 'tozero' },
            paper_bgcolor: 'white',
            plot_bgcolor: 'white',
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
                type: 'scatter', mode: 'lines', name: 'Avg',
                line: { color: '#1a1a2e', width: 2 },
            });
        }
        traces.push({
            x: p95.data.map(d => d.timestamp),
            y: p95.data.map(d => d.value),
            type: 'scatter', mode: 'lines', name: 'P95',
            line: { color: '#f44336', dash: 'dash', width: 2 },
        });
        const layout = {
            margin: { t: 8, r: 12, b: 30, l: 50 },
            height: 200,
            xaxis: { type: 'date', gridcolor: '#f0f0f0' },
            yaxis: { gridcolor: '#f0f0f0', rangemode: 'tozero' },
            paper_bgcolor: 'white',
            plot_bgcolor: 'white',
            showlegend: true,
            legend: { x: 0.02, y: 0.98, bgcolor: 'rgba(255,255,255,0.8)' },
        };
        Plotly.react('chart-exec', traces, layout);
    }
}

let currentEventFilter = '';

function filterEvents(type) {
    currentEventFilter = type;
    updateEvents();
}

function truncate(str, len) {
    return str.length > len ? str.slice(0, len) + '...' : str;
}

async function updateEvents() {
    const typeParam = currentEventFilter ? `&type=${currentEventFilter}` : '';
    const result = await fetchJSON(`/dashboard/api/events?limit=50${typeParam}`);
    if (!result || !result.events) return;

    const tbody = document.getElementById('events-body');
    tbody.innerHTML = '';

    if (result.events.length === 0) {
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = 5;
        td.textContent = 'No events yet';
        td.style.textAlign = 'center';
        td.style.color = '#999';
        td.style.padding = '24px';
        tr.appendChild(td);
        tbody.appendChild(tr);
        return;
    }

    for (const ev of result.events) {
        const tr = document.createElement('tr');
        let parsed = {};
        try { parsed = JSON.parse(ev.details); } catch { parsed = {}; }

        // Time
        const tdTs = document.createElement('td');
        tdTs.textContent = new Date(ev.timestamp).toLocaleTimeString();

        // Type badge
        const tdType = document.createElement('td');
        const badge = document.createElement('span');
        badge.textContent = ev.event_type;
        badge.className = `badge badge-${ev.event_type.replace(/[^a-z0-9_]/gi, '_')}`;
        tdType.appendChild(badge);

        // Code
        const tdCode = document.createElement('td');
        const code = parsed.code || '';
        tdCode.textContent = truncate(code, 60);
        tdCode.title = code;
        tdCode.className = 'code-cell';

        // Output
        const tdOutput = document.createElement('td');
        const output = parsed.output || parsed.error || '';
        tdOutput.textContent = truncate(output, 80);
        tdOutput.title = output;
        tdOutput.className = output.includes('[stderr]') ? 'output-cell error-text' : 'output-cell';

        // Duration
        const tdDuration = document.createElement('td');
        const ms = parsed.execution_ms;
        tdDuration.textContent = ms != null ? `${ms.toFixed(1)}ms` : '-';
        tdDuration.className = 'duration-cell';

        tr.append(tdTs, tdType, tdCode, tdOutput, tdDuration);
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
