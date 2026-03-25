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
        loadSyncOverview();
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

        // This week's summary (match current ISO week)
        if (weekly.length > 0) {
            const now = new Date();
            const jan1 = new Date(now.getFullYear(), 0, 1);
            const dayOfYear = Math.floor((now - jan1) / 86400000) + 1;
            const dayOfWeek = now.getDay() || 7; // 1=Mon..7=Sun
            const isoWeek = Math.floor((dayOfYear - dayOfWeek + 10) / 7);
            const isoYear = now.getFullYear();
            const currentWeekKey = `${isoYear}-W${String(isoWeek).padStart(2, '0')}`;
            const thisWeek = weekly.find(w => w.week === currentWeekKey) || {rides: 0, duration_h: 0, tss: 0};
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

// Track which section we came from when opening ride detail
let _rideDetailReturnTo = 'rides';
let _currentRideId = null;
let _currentWorkoutId = null;

async function showRideDetail(rideId) {
    // Switch to rides section and show the detail panel
    const ridesSection = document.getElementById('rides');
    const listView = document.getElementById('rides-list-view');
    const panel = document.getElementById('ride-detail-panel');

    // Remember which tab we came from
    const activeBtn = document.querySelector('.nav-btn.active');
    _rideDetailReturnTo = activeBtn ? activeBtn.dataset.section : 'rides';

    // Activate rides section
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    document.querySelector('[data-section="rides"]')?.classList.add('active');
    ridesSection.classList.add('active');

    // Hide list, show detail
    listView.style.display = 'none';
    panel.style.display = 'block';
    document.getElementById('ride-detail-title').textContent = 'Loading...';
    document.getElementById('ride-workout-name').style.display = 'none';
    document.getElementById('ride-crosshair-tooltip').style.display = 'none';
    document.getElementById('ride-selection-stats').style.display = 'none';

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

        // Fetch planned workout for the ride's date
        let workout = null;
        try {
            workout = await api(`/api/plan/workouts/by-date/${ride.date}`);
            if (workout && workout.name) {
                const woLabel = document.getElementById('ride-workout-name');
                woLabel.textContent = `Planned: ${workout.name}`;
                woLabel.style.display = 'block';
            }
        } catch (e) { /* no workout for this date */ }

        // Populate notes
        _currentRideId = rideId;
        _currentWorkoutId = workout?.id || null;
        const isCompleted = !!(ride.duration_s || ride.records?.length);

        // Pre-ride section (from planned workout)
        const preSection = document.getElementById('ride-pre-section');
        const coachPreSection = document.getElementById('ride-coach-pre-section');
        const athletePreSection = document.getElementById('ride-athlete-pre-section');
        const preTextarea = document.getElementById('ride-athlete-pre-notes');
        const preReadonly = document.getElementById('ride-athlete-pre-readonly');
        const preActions = document.getElementById('ride-pre-actions');

        if (workout) {
            preSection.style.display = 'block';
            // Coach's pre-ride notes
            if (workout.coach_notes) {
                document.getElementById('ride-coach-pre-notes').textContent = workout.coach_notes;
                coachPreSection.style.display = 'block';
            } else {
                coachPreSection.style.display = 'none';
            }
            // Athlete's pre-ride notes
            if (isCompleted) {
                if (workout.athlete_notes) {
                    athletePreSection.style.display = 'block';
                    preTextarea.style.display = 'none';
                    preReadonly.style.display = 'block';
                    preReadonly.textContent = workout.athlete_notes;
                    preActions.style.display = 'none';
                } else {
                    athletePreSection.style.display = 'none';
                    preActions.style.display = 'none';
                }
            } else {
                athletePreSection.style.display = 'block';
                preTextarea.style.display = 'block';
                preTextarea.value = workout.athlete_notes || '';
                preReadonly.style.display = 'none';
                preActions.style.display = 'flex';
            }
            // Hide entire pre section if nothing to show
            if (coachPreSection.style.display === 'none' && athletePreSection.style.display === 'none') {
                preSection.style.display = 'none';
            }
        } else {
            preSection.style.display = 'none';
        }

        // Post-ride section (on the ride)
        const postSection = document.getElementById('ride-post-section');
        const postActions = document.getElementById('ride-post-actions');
        if (isCompleted) {
            postSection.style.display = 'block';
            document.getElementById('ride-post-comments').value = ride.post_ride_comments || '';
            postActions.style.display = 'flex';
        } else {
            postSection.style.display = 'none';
            postActions.style.display = 'none';
        }

        // Coach's post-ride analysis
        const coachPostSection = document.getElementById('ride-coach-post-section');
        if (ride.coach_comments) {
            document.getElementById('ride-coach-post-notes').textContent = ride.coach_comments;
            coachPostSection.style.display = 'block';
        } else {
            coachPostSection.style.display = 'none';
        }
        document.getElementById('ride-comments-status').style.display = 'none';
        const preStatus = document.getElementById('ride-pre-status');
        if (preStatus) preStatus.style.display = 'none';

        drawRideTimeline(ride, workout);
    } catch (e) {
        console.error('Ride detail error:', e);
        document.getElementById('ride-detail-title').textContent = 'Error loading ride';
    }
}

function closeRideDetail() {
    document.getElementById('ride-detail-panel').style.display = 'none';
    document.getElementById('rides-list-view').style.display = '';

    // Return to the tab we came from
    if (_rideDetailReturnTo && _rideDetailReturnTo !== 'rides') {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
        document.querySelector(`[data-section="${_rideDetailReturnTo}"]`)?.classList.add('active');
        document.getElementById(_rideDetailReturnTo)?.classList.add('active');
    }
}

document.getElementById('close-ride-detail')?.addEventListener('click', closeRideDetail);

// Save post-ride notes (on the ride)
document.getElementById('ride-comments-save')?.addEventListener('click', async () => {
    if (!_currentRideId) return;
    const status = document.getElementById('ride-comments-status');
    try {
        await fetch(`/api/rides/${_currentRideId}/comments`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                post_ride_comments: document.getElementById('ride-post-comments').value || null,
            }),
        });
        status.textContent = 'Saved!';
        status.style.color = 'var(--green)';
        status.style.display = 'inline';
        setTimeout(() => status.style.display = 'none', 3000);
    } catch (e) {
        status.textContent = 'Save failed';
        status.style.color = 'var(--red)';
        status.style.display = 'inline';
    }
});

// Save pre-ride notes (on the planned workout)
document.getElementById('ride-pre-save')?.addEventListener('click', async () => {
    if (!_currentWorkoutId) return;
    const status = document.getElementById('ride-pre-status');
    try {
        await fetch(`/api/plan/workouts/${_currentWorkoutId}/notes`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                athlete_notes: document.getElementById('ride-athlete-pre-notes').value || null,
            }),
        });
        status.textContent = 'Saved!';
        status.style.color = 'var(--green)';
        status.style.display = 'inline';
        setTimeout(() => status.style.display = 'none', 3000);
    } catch (e) {
        status.textContent = 'Save failed';
        status.style.color = 'var(--red)';
        status.style.display = 'inline';
    }
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
    const keys = ['athlete_profile', 'coaching_principles', 'coach_role', 'plan_management', 'intervals_icu_api_key', 'intervals_icu_athlete_id'];
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

// Sync
document.getElementById('sync-now-btn')?.addEventListener('click', async () => {
    const btn = document.getElementById('sync-now-btn');
    const statusText = document.getElementById('sync-status-text');
    const progress = document.getElementById('sync-progress');
    const progressBar = document.getElementById('sync-progress-bar');
    const logEl = document.getElementById('sync-log');

    btn.disabled = true;
    btn.textContent = 'Syncing...';
    statusText.textContent = '';
    logEl.textContent = '';
    progress.style.display = 'block';
    progressBar.style.width = '0%';

    try {
        const res = await fetch('/api/sync/start', { method: 'POST' });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Sync failed to start');
        }
        const { sync_id, ws_url } = await res.json();

        // Use WebSocket for live updates
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const ws = new WebSocket(`${protocol}//${location.host}${ws_url}`);

        ws.onmessage = (e) => {
            const msg = JSON.parse(e.data);
            if (msg.type === 'ping') return;

            // Update progress bar (estimate based on phase)
            if (msg.phase === 'rides') progressBar.style.width = '33%';
            if (msg.phase === 'workouts') progressBar.style.width = '66%';
            if (msg.phase === 'pmc') progressBar.style.width = '85%';

            if (msg.detail) {
                const line = document.createElement('div');
                line.textContent = msg.detail;
                logEl.appendChild(line);
                logEl.scrollTop = logEl.scrollHeight;
            }

            if (msg.status === 'completed') {
                progressBar.style.width = '100%';
                progressBar.style.background = 'var(--green)';
                statusText.textContent = `Done — ${msg.rides_downloaded || 0} rides, ${msg.workouts_uploaded || 0} workouts synced`;
                statusText.style.color = 'var(--green)';
                btn.disabled = false;
                btn.textContent = 'Sync Now';
                loadSyncOverview();
            } else if (msg.status === 'failed') {
                progressBar.style.width = '100%';
                progressBar.style.background = 'var(--red)';
                statusText.textContent = 'Sync failed';
                statusText.style.color = 'var(--red)';
                btn.disabled = false;
                btn.textContent = 'Sync Now';
            }
        };

        ws.onerror = () => {
            // Fall back to polling if WebSocket fails
            pollSync(sync_id, btn, statusText, progressBar, logEl);
        };

        ws.onclose = (e) => {
            if (btn.disabled) {
                // Closed before completion — fall back to polling
                pollSync(sync_id, btn, statusText, progressBar, logEl);
            }
        };
    } catch (e) {
        statusText.textContent = e.message;
        statusText.style.color = 'var(--red)';
        progress.style.display = 'none';
        btn.disabled = false;
        btn.textContent = 'Sync Now';
    }
});

async function pollSync(syncId, btn, statusText, progressBar, logEl) {
    const poll = async () => {
        try {
            const res = await fetch(`/api/sync/status/${syncId}`);
            const msg = await res.json();
            if (msg.status === 'completed') {
                progressBar.style.width = '100%';
                progressBar.style.background = 'var(--green)';
                statusText.textContent = `Done — ${msg.rides_downloaded || 0} rides, ${msg.workouts_uploaded || 0} workouts synced`;
                statusText.style.color = 'var(--green)';
                btn.disabled = false;
                btn.textContent = 'Sync Now';
                loadSyncOverview();
                return;
            } else if (msg.status === 'failed') {
                progressBar.style.width = '100%';
                progressBar.style.background = 'var(--red)';
                statusText.textContent = 'Sync failed';
                statusText.style.color = 'var(--red)';
                btn.disabled = false;
                btn.textContent = 'Sync Now';
                return;
            }
            setTimeout(poll, 2000);
        } catch { setTimeout(poll, 2000); }
    };
    poll();
}

async function loadSyncOverview() {
    try {
        const overview = await api('/api/sync/overview');
        const el = document.getElementById('sync-last');
        if (!el) return;
        if (overview.last_sync) {
            const ls = overview.last_sync;
            const when = ls.completed_at || ls.started_at;
            const date = new Date(when);
            const ago = timeAgo(date);
            const rides = ls.rides_downloaded || 0;
            const workouts = ls.workouts_uploaded || 0;
            el.textContent = `Last sync: ${ago} — ${rides} rides downloaded, ${workouts} workouts uploaded`;
        } else {
            el.textContent = 'Never synced';
        }
    } catch { /* ignore */ }
}

function timeAgo(date) {
    const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
    if (seconds < 60) return 'just now';
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
}

// Boot
loadSection('dashboard');
