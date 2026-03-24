/**
 * Main application logic and navigation.
 */

const API = '';

async function api(path) {
    const resp = await fetch(API + path);
    if (!resp.ok) throw new Error(`API error: ${resp.status}`);
    return resp.json();
}

async function apiPost(path, body) {
    const resp = await fetch(API + path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error(`API error: ${resp.status}`);
    return resp.json();
}

// Navigation
document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
        btn.classList.add('active');
        const name = btn.dataset.section;
        const section = document.getElementById(name);
        section.classList.add('active');
        closeWorkoutDetail();
        loadSection(name);
    });
});

// Analysis tab switching
document.querySelectorAll('.analysis-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.analysis-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.analysis-panel').forEach(p => p.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById('analysis-' + tab.dataset.tab).classList.add('active');
    });
});

const loaded = {};

function loadSection(name) {
    // Calendar always refreshes; others load once
    if (name === 'calendar') {
        if (!loaded[name]) {
            loaded[name] = true;
            initCalendar();
        } else {
            renderCalendar();
        }
        return;
    }
    if (name === 'settings') {
        loadSettings();
        return;
    }
    if (loaded[name]) return;
    loaded[name] = true;
    switch (name) {
        case 'dashboard': loadDashboard(); break;
        case 'rides': loadRides(); break;
        case 'analysis': loadAnalysis(); break;
        case 'plan': loadPlan(); break;
    }
}

function refreshCalendar() {
    if (loaded['calendar']) {
        renderCalendar();
    }
}

// Format helpers
function fmtDuration(s) {
    if (!s) return '--';
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function fmtDistance(m) {
    if (!m) return '--';
    return (m / 1000).toFixed(1) + ' km';
}

// Dashboard
async function loadDashboard() {
    try {
        const [pmc, monthly, phases, weekly] = await Promise.all([
            api('/api/pmc/current'),
            api('/api/rides/summary/monthly'),
            api('/api/plan/macro'),
            api('/api/rides/summary/weekly'),
        ]);

        // PMC metrics
        document.getElementById('ctl-value').textContent = pmc.ctl?.toFixed(1) || '--';
        document.getElementById('atl-value').textContent = pmc.atl?.toFixed(1) || '--';
        document.getElementById('tsb-value').textContent = pmc.tsb?.toFixed(1) || '--';

        // Color code TSB
        const tsbCard = document.getElementById('tsb-card');
        if (pmc.tsb > 10) tsbCard.className = 'metric-card green';
        else if (pmc.tsb > -10) tsbCard.className = 'metric-card yellow';
        else tsbCard.className = 'metric-card red';

        // FTP from latest monthly data
        const ftpData = await api('/api/analysis/ftp-history');
        if (ftpData.length > 0) {
            const latest = ftpData[ftpData.length - 1];
            document.getElementById('ftp-value').textContent = latest.ftp + 'w';
            document.getElementById('wkg-value').textContent = latest.w_per_kg ? latest.w_per_kg.toFixed(2) : '--';
        }

        // This week's summary
        if (weekly.length > 0) {
            const thisWeek = weekly[weekly.length - 1];
            document.getElementById('week-summary').textContent =
                `${thisWeek.rides} rides, ${thisWeek.duration_h}h, ${Math.round(thisWeek.tss)} TSS`;
        }

        // Current phase
        const today = new Date().toISOString().slice(0, 10);
        const currentPhase = phases.find(p => p.start_date <= today && p.end_date >= today);
        document.getElementById('current-phase').textContent = currentPhase?.name || 'Off-season';

        // Charts
        const pmcAll = await api('/api/pmc');
        drawPMCChart(pmcAll);
        drawMonthlyChart(monthly);
    } catch (e) {
        console.error('Dashboard error:', e);
    }
}

// Rides list
async function loadRides() {
    try {
        const rides = await api('/api/rides?limit=300');
        renderRidesTable(rides);
    } catch (e) {
        console.error('Rides error:', e);
    }
}

function renderRidesTable(rides) {
    const tbody = document.getElementById('rides-tbody');
    tbody.innerHTML = rides.map(r => `
        <tr data-id="${r.id}">
            <td>${r.date}</td>
            <td>${r.sub_sport || r.sport || '--'}</td>
            <td>${fmtDuration(r.duration_s)}</td>
            <td>${fmtDistance(r.distance_m)}</td>
            <td>${r.tss ? Math.round(r.tss) : '--'}</td>
            <td>${r.avg_power || '--'}</td>
            <td>${r.normalized_power || '--'}</td>
            <td>${r.avg_hr || '--'}</td>
            <td>${r.total_ascent ? r.total_ascent + 'm' : '--'}</td>
        </tr>
    `).join('');

    tbody.querySelectorAll('tr').forEach(tr => {
        tr.addEventListener('click', () => showRideDetail(parseInt(tr.dataset.id)));
    });
}

// Filter handler
document.getElementById('rides-filter-btn')?.addEventListener('click', async () => {
    const start = document.getElementById('rides-start').value;
    const end = document.getElementById('rides-end').value;
    const sport = document.getElementById('rides-sport').value;
    let url = '/api/rides?limit=300';
    if (start) url += `&start_date=${start}`;
    if (end) url += `&end_date=${end}`;
    if (sport) url += `&sport=${sport}`;
    const rides = await api(url);
    renderRidesTable(rides);
});

async function showRideDetail(rideId) {
    const panel = document.getElementById('ride-detail-panel');
    panel.style.display = 'block';
    document.getElementById('ride-detail-title').textContent = 'Loading...';

    try {
        const ride = await api(`/api/rides/${rideId}`);
        document.getElementById('ride-detail-title').textContent =
            `${ride.date} - ${ride.sub_sport || ride.sport}`;

        document.getElementById('ride-detail-metrics').innerHTML = [
            `Duration: ${fmtDuration(ride.duration_s)}`,
            `Distance: ${fmtDistance(ride.distance_m)}`,
            `TSS: ${ride.tss ? Math.round(ride.tss) : '--'}`,
            `Avg Power: ${ride.avg_power || '--'}w`,
            `NP: ${ride.normalized_power || '--'}w`,
            `Avg HR: ${ride.avg_hr || '--'}`,
            `IF: ${ride.intensity_factor?.toFixed(2) || '--'}`,
            `Ascent: ${ride.total_ascent || '--'}m`,
        ].map(s => `<div class="metric-card"><span class="metric-value" style="font-size:1rem">${s}</span></div>`).join('');

        drawRideCharts(ride);
    } catch (e) {
        document.getElementById('ride-detail-title').textContent = 'Error loading ride';
    }
}

document.getElementById('close-ride-detail')?.addEventListener('click', () => {
    document.getElementById('ride-detail-panel').style.display = 'none';
});

// Analysis
async function loadAnalysis() {
    try {
        const [curve, ef, zones, ftp] = await Promise.all([
            api('/api/analysis/power-curve'),
            api('/api/analysis/efficiency'),
            api('/api/analysis/zones'),
            api('/api/analysis/ftp-history'),
        ]);
        drawPowerCurveChart(curve);
        drawEFChart(ef);
        drawZonesChart(zones);
        drawFTPChart(ftp);
    } catch (e) {
        console.error('Analysis error:', e);
    }
}

// Plan
async function loadPlan() {
    const results = await Promise.allSettled([
        api('/api/plan/macro'),
        api('/api/plan/compliance'),
        api('/api/plan/templates'),
    ]);

    const phases = results[0].status === 'fulfilled' ? results[0].value : [];
    const compliance = results[1].status === 'fulfilled' ? results[1].value : null;
    const templates = results[2].status === 'fulfilled' ? results[2].value : [];

    try { drawGantt(phases); } catch (e) { console.error('Gantt error:', e); }
    try { if (compliance) renderCompliance(compliance); } catch (e) { console.error('Compliance error:', e); }
    try { renderTemplates(templates); } catch (e) { console.error('Templates render error:', e); }
    try { initTemplateFilters(templates); } catch (e) { console.error('Template filters error:', e); }
}

function renderTemplates(templates, filter = '') {
    const container = document.getElementById('templates-list');
    const filtered = filter ? templates.filter(t => t.category === filter) : templates;

    if (!filtered.length) {
        container.innerHTML = '<p style="color:var(--text-muted);">No templates found.</p>';
        return;
    }

    container.innerHTML = filtered.map(t => {
        const totalS = t.steps.reduce((sum, s) => {
            if (s.type === 'Intervals' || s.type === 'IntervalsT')
                return sum + (s.repeat || 1) * ((s.on_duration_seconds || 0) + (s.off_duration_seconds || 0));
            return sum + (s.duration_seconds || 0);
        }, 0);
        const durMin = Math.round(totalS / 60);

        const stepsHtml = t.steps.map(s => {
            if (s.type === 'Intervals' || s.type === 'IntervalsT') {
                return `<div class="step-row"><span>${s.repeat}x Intervals</span><span>${Math.round(s.on_duration_seconds/60)}min on @ ${Math.round(s.on_power*100)}% / ${Math.round(s.off_duration_seconds/60)}min off</span></div>`;
            } else if (s.type === 'Warmup' || s.type === 'Cooldown') {
                return `<div class="step-row"><span>${s.type}</span><span>${Math.round((s.duration_seconds||0)/60)}min ${Math.round(s.power_low*100)}-${Math.round(s.power_high*100)}%</span></div>`;
            } else {
                const dur = s.duration_seconds ? `${Math.round(s.duration_seconds/60)}min` : 'fill';
                return `<div class="step-row"><span>Steady</span><span>${dur} @ ${Math.round(s.power*100)}% FTP</span></div>`;
            }
        }).join('');

        return `<div class="template-card" onclick="showTemplateDetail(${t.id})" style="cursor:pointer;" title="Click to view details">
            <h4>${t.name}</h4>
            <div class="template-meta">
                <span class="template-badge">${t.category}</span>
                <span>${durMin > 0 ? durMin + 'min' : 'variable'}</span>
                <span>${t.source}</span>
            </div>
            <div class="template-desc">${t.description || ''}</div>
            <div class="template-steps">${stepsHtml}</div>
        </div>`;
    }).join('');
}

function initTemplateFilters(templates) {
    document.querySelectorAll('.template-filter').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.template-filter').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            renderTemplates(templates, btn.dataset.cat);
        });
    });
}

function drawGantt(phases) {
    const container = document.getElementById('periodization-gantt');
    if (!phases.length) { container.innerHTML = '<p>No periodization data</p>'; return; }

    const allStart = new Date(phases[0].start_date);
    const allEnd = new Date(phases[phases.length - 1].end_date);
    const totalDays = (allEnd - allStart) / 86400000;

    const colors = ['#0f3460', '#e94560', '#f5c518', '#00d4aa', '#9b59b6'];

    container.innerHTML = phases.map((p, i) => {
        const start = (new Date(p.start_date) - allStart) / 86400000;
        const dur = (new Date(p.end_date) - new Date(p.start_date)) / 86400000;
        const left = (start / totalDays * 100).toFixed(1);
        const width = (dur / totalDays * 100).toFixed(1);
        return `<div class="gantt-row">
            <div class="gantt-label">${p.name}</div>
            <div class="gantt-bar-container">
                <div class="gantt-bar" style="left:${left}%;width:${width}%;background:${colors[i % colors.length]}">
                    ${p.start_date} - ${p.end_date}
                </div>
            </div>
        </div>`;
    }).join('');
}

function renderCompliance(data) {
    document.getElementById('compliance-stats').innerHTML = `
        <div class="metric-card"><span class="metric-label">Planned</span><span class="metric-value">${data.planned}</span></div>
        <div class="metric-card"><span class="metric-label">Completed</span><span class="metric-value">${data.completed}</span></div>
        <div class="metric-card"><span class="metric-label">Missed</span><span class="metric-value">${data.missed}</span></div>
        <div class="metric-card"><span class="metric-label">Extra Rides</span><span class="metric-value">${data.extra}</span></div>
        <div class="metric-card"><span class="metric-label">Compliance</span><span class="metric-value">${data.compliance_pct}%</span></div>
    `;
}

// Settings
async function loadSettings() {
    try {
        const settings = await api('/api/coaching/settings');
        for (const [key, value] of Object.entries(settings)) {
            const el = document.getElementById(`setting-${key}`);
            if (el) el.value = value;
        }
    } catch (e) {
        console.error('Settings load error:', e);
    }
}

document.getElementById('settings-save')?.addEventListener('click', async () => {
    const keys = ['athlete_profile', 'coaching_principles', 'coach_role', 'plan_management'];
    const status = document.getElementById('settings-status');
    try {
        for (const key of keys) {
            const el = document.getElementById(`setting-${key}`);
            if (el) {
                await fetch('/api/coaching/settings', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ key, value: el.value }),
                });
            }
        }
        status.textContent = 'Saved!';
        status.style.color = 'var(--green)';
        status.style.display = 'inline';
        setTimeout(() => status.style.display = 'none', 3000);
    } catch (e) {
        status.textContent = 'Save failed';
        status.style.color = 'var(--red)';
        status.style.display = 'inline';
        console.error('Settings save error:', e);
    }
});

document.getElementById('settings-reset')?.addEventListener('click', async () => {
    if (!confirm('Reset all settings to defaults? This cannot be undone.')) return;
    try {
        await apiPost('/api/coaching/settings/reset', {});
        await loadSettings();
        const status = document.getElementById('settings-status');
        status.textContent = 'Reset to defaults!';
        status.style.color = 'var(--green)';
        status.style.display = 'inline';
        setTimeout(() => status.style.display = 'none', 3000);
    } catch (e) {
        console.error('Settings reset error:', e);
    }
});

// Boot
loadSection('dashboard');
