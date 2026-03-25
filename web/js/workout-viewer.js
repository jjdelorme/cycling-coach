/**
 * Workout detail viewer - inline panel with power profile visualization and export.
 */

let workoutChart = null;
let _currentViewWorkoutId = null;

function initWorkoutViewer() {
    // No-op; viewer opens/closes based on calendar day selection
}

function closeWorkoutDetail() {
    document.getElementById('workout-detail').style.display = 'none';
    if (workoutChart) {
        workoutChart.destroy();
        workoutChart = null;
    }
}

async function showWorkoutDetail(workoutId) {
    const panel = document.getElementById('workout-detail');
    panel.style.display = 'block';
    document.getElementById('workout-detail-title').textContent = 'Loading...';
    document.getElementById('workout-detail-summary').innerHTML = '';
    document.getElementById('workout-steps-table').innerHTML = '';
    document.getElementById('workout-detail-actions').innerHTML = '';

    // Scroll to the panel
    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });

    try {
        const w = await api(`/api/plan/workouts/${workoutId}`);
        renderWorkoutDetail(w);
    } catch (e) {
        document.getElementById('workout-detail-title').textContent = 'Error loading workout';
        console.error('Workout detail error:', e);
    }
}

function renderWorkoutDetail(w) {
    document.getElementById('workout-detail-title').textContent = w.name || 'Workout';

    // Summary bar
    const totalMin = Math.round((w.total_duration_s || 0) / 60);
    const hours = Math.floor(totalMin / 60);
    const mins = totalMin % 60;
    const durStr = hours > 0 ? `${hours}h ${mins}m` : `${mins}m`;

    // Compute avg/max power from steps
    let totalPowerTime = 0, weightedPower = 0, maxWatts = 0;
    for (const s of w.steps) {
        weightedPower += s.power_watts * s.duration_s;
        totalPowerTime += s.duration_s;
        if (s.power_watts > maxWatts) maxWatts = s.power_watts;
        if (s.power_high_watts && s.power_high_watts > maxWatts) maxWatts = s.power_high_watts;
    }
    const avgWatts = totalPowerTime > 0 ? Math.round(weightedPower / totalPowerTime) : 0;

    // Estimate IF and TSS
    const ifactor = w.ftp > 0 ? (avgWatts / w.ftp) : 0;
    const tssEst = totalPowerTime > 0 ? Math.round((totalPowerTime * avgWatts * ifactor) / (w.ftp * 3600) * 100) : 0;

    document.getElementById('workout-detail-summary').innerHTML = `
        <div class="ws-item"><span class="ws-label">Duration</span><span class="ws-value">${durStr}</span></div>
        <div class="ws-item"><span class="ws-label">FTP</span><span class="ws-value">${w.ftp}w</span></div>
        <div class="ws-item"><span class="ws-label">Avg Power</span><span class="ws-value">${avgWatts}w</span></div>
        <div class="ws-item"><span class="ws-label">Max Target</span><span class="ws-value">${maxWatts}w</span></div>
        <div class="ws-item"><span class="ws-label">IF (est)</span><span class="ws-value">${ifactor.toFixed(2)}</span></div>
        <div class="ws-item"><span class="ws-label">TSS (est)</span><span class="ws-value">${tssEst}</span></div>
    `;

    // Draw power profile chart
    drawWorkoutProfile(w);

    // Steps table
    renderStepsTable(w);

    // Actions
    let actionsHtml = '';
    if (w.has_xml) {
        actionsHtml += `<button id="sync-garmin-btn" class="btn-sync" data-id="${w.id}" title="Sync to Garmin via intervals.icu" style="display:none;">Sync to Garmin</button>`;
        actionsHtml += `<a href="/api/plan/workouts/${w.id}/download?fmt=tcx" download><button class="btn-secondary">Download .TCX</button></a>`;
        actionsHtml += `<a href="/api/plan/workouts/${w.id}/download?fmt=zwo" download><button class="btn-secondary">Download .ZWO</button></a>`;
    }
    document.getElementById('workout-detail-actions').innerHTML = actionsHtml;

    // Check if intervals.icu is configured and show sync button
    if (w.has_xml) {
        checkIntegrations(w.id);
    }

    // Notes section
    const notesPanel = document.getElementById('workout-notes');
    const coachNotesSection = document.getElementById('workout-coach-notes-section');
    const athleteNotesSection = document.getElementById('workout-athlete-notes-section');

    if (w.id) {
        _currentViewWorkoutId = w.id;
        notesPanel.style.display = 'block';

        if (w.coach_notes) {
            document.getElementById('workout-coach-notes').textContent = w.coach_notes;
            coachNotesSection.style.display = 'block';
        } else {
            coachNotesSection.style.display = 'none';
        }

        document.getElementById('workout-athlete-notes').value = w.athlete_notes || '';
        athleteNotesSection.style.display = 'block';
        document.getElementById('workout-notes-status').style.display = 'none';
    } else {
        notesPanel.style.display = 'none';
    }
}

function drawWorkoutProfile(w) {
    const canvas = document.getElementById('workout-profile-chart');
    if (workoutChart) {
        workoutChart.destroy();
        workoutChart = null;
    }

    if (!w.steps || w.steps.length === 0) {
        canvas.parentElement.style.display = 'none';
        return;
    }
    canvas.parentElement.style.display = 'block';

    const totalDuration = w.steps.reduce((sum, s) => Math.max(sum, s.start_s + s.duration_s), 0);
    // Sample at ~1 point per 5 seconds, cap at 600 points
    const sampleInterval = Math.max(5, Math.floor(totalDuration / 600));
    const numPoints = Math.ceil(totalDuration / sampleInterval);

    const labels = [];
    const powerData = [];
    const bgColors = [];

    for (let i = 0; i < numPoints; i++) {
        const t = i * sampleInterval;
        labels.push(fmtTime(t));

        // Find which step we're in
        let watts = 0;
        let pct = 0;
        for (const step of w.steps) {
            if (t >= step.start_s && t < step.start_s + step.duration_s) {
                if ((step.type === 'Warmup' || step.type === 'Cooldown') && step.power_low_watts && step.power_high_watts) {
                    const progress = (t - step.start_s) / step.duration_s;
                    if (step.type === 'Warmup') {
                        watts = Math.round(step.power_low_watts + progress * (step.power_high_watts - step.power_low_watts));
                    } else {
                        watts = Math.round(step.power_high_watts + progress * (step.power_low_watts - step.power_high_watts));
                    }
                    pct = watts / w.ftp;
                } else {
                    watts = step.power_watts || 0;
                    pct = step.power_pct || 0;
                }
                break;
            }
        }
        powerData.push(watts);
        bgColors.push(zoneColor(pct, 0.7));
    }

    // Build annotation boxes for each step (zone-colored, time-proportional)
    const annotations = {};
    w.steps.forEach((step, idx) => {
        const xMin = Math.floor(step.start_s / sampleInterval);
        const xMax = Math.min(numPoints - 1, Math.floor((step.start_s + step.duration_s) / sampleInterval));
        const pct = step.power_pct || 0.5;

        annotations['step' + idx] = {
            type: 'box',
            xMin: xMin,
            xMax: xMax,
            yMin: 0,
            yMax: step.power_watts || 0,
            backgroundColor: zoneColor(pct, 0.2),
            borderColor: zoneColor(pct, 0.6),
            borderWidth: 1,
            borderRadius: 2,
            label: {
                display: step.duration_s > (totalDuration * 0.04),
                content: step.label || step.type,
                position: 'start',
                color: 'rgba(255,255,255,0.6)',
                font: { size: 9 },
                padding: 2,
            },
        };
    });

    workoutChart = new Chart(canvas, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Target Power',
                data: powerData,
                borderColor: 'rgba(245, 197, 24, 0.8)',
                borderWidth: 1.5,
                pointRadius: 0,
                fill: true,
                backgroundColor: 'rgba(245, 197, 24, 0.08)',
                stepped: 'before',
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        title: (items) => {
                            const i = items[0].dataIndex;
                            return labels[i];
                        },
                        label: (item) => {
                            const watts = item.raw;
                            const pct = Math.round((watts / w.ftp) * 100);
                            return `${watts}w (${pct}% FTP)`;
                        },
                    },
                },
                annotation: { annotations },
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#999', font: { size: 10 }, maxTicksLimit: 15 },
                },
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(255,255,255,0.08)' },
                    ticks: { color: '#999', callback: (v) => v + 'w' },
                    title: { display: true, text: 'Watts', color: '#999' },
                },
            },
        },
    });
}

function renderStepsTable(w) {
    if (!w.steps || w.steps.length === 0) {
        document.getElementById('workout-steps-table').innerHTML = '<p style="color:var(--text-muted);font-size:0.85rem;">No structured steps available</p>';
        return;
    }

    let html = `<table>
        <thead><tr>
            <th>Step</th>
            <th>Time</th>
            <th>Duration</th>
            <th>Power</th>
            <th>Zone</th>
        </tr></thead><tbody>`;

    for (const s of w.steps) {
        const durMin = Math.floor(s.duration_s / 60);
        const durSec = s.duration_s % 60;
        const durStr = durSec > 0 ? `${durMin}:${String(durSec).padStart(2, '0')}` : `${durMin}:00`;
        const startStr = fmtTime(s.start_s);
        const endStr = fmtTime(s.start_s + s.duration_s);

        let powerStr, pctStr;
        if (s.power_low_watts !== undefined && s.power_high_watts !== undefined) {
            powerStr = `${s.power_low_watts}w → ${s.power_high_watts}w`;
            pctStr = `${Math.round(s.power_low_pct * 100)}% → ${Math.round(s.power_high_pct * 100)}%`;
        } else {
            powerStr = `${s.power_watts}w`;
            pctStr = `${Math.round(s.power_pct * 100)}% FTP`;
        }

        const zoneClass = zoneClassForPct(s.power_pct);

        html += `<tr>
            <td><strong>${s.type}</strong><br><span style="color:var(--text-muted);font-size:0.7rem;">${s.label}</span></td>
            <td>${startStr} → ${endStr}</td>
            <td>${durStr}</td>
            <td>${powerStr}<br><span style="color:var(--text-muted);font-size:0.7rem;">${pctStr}</span></td>
            <td><div class="step-zone-bar ${zoneClass}" style="width:60px;"></div></td>
        </tr>`;
    }

    html += '</tbody></table>';
    document.getElementById('workout-steps-table').innerHTML = html;
}

function fmtTime(seconds) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    return `${m}:${String(s).padStart(2, '0')}`;
}

function zoneColor(pct, alpha) {
    if (pct < 0.56) return `rgba(126, 200, 227, ${alpha})`;      // Z1
    if (pct < 0.76) return `rgba(0, 212, 170, ${alpha})`;        // Z2
    if (pct < 0.91) return `rgba(245, 197, 24, ${alpha})`;       // Z3
    if (pct < 1.06) return `rgba(232, 145, 58, ${alpha})`;       // Z4
    if (pct < 1.21) return `rgba(233, 69, 96, ${alpha})`;        // Z5
    return `rgba(155, 89, 182, ${alpha})`;                        // Z6
}

function zoneClassForPct(pct) {
    if (pct < 0.56) return 'zone-z1';
    if (pct < 0.76) return 'zone-z2';
    if (pct < 0.91) return 'zone-z3';
    if (pct < 1.06) return 'zone-z4';
    if (pct < 1.21) return 'zone-z5';
    return 'zone-z6';
}

// intervals.icu sync

async function checkIntegrations(workoutId) {
    try {
        const status = await api('/api/plan/integrations/status');
        if (status.intervals_icu) {
            const btn = document.getElementById('sync-garmin-btn');
            if (btn) {
                btn.style.display = '';
                btn.onclick = () => syncToGarmin(workoutId);
            }
        }
    } catch (e) {
        // Integration not available, keep button hidden
    }
}

async function syncToGarmin(workoutId) {
    const btn = document.getElementById('sync-garmin-btn');
    const origText = btn.textContent;
    btn.textContent = 'Syncing...';
    btn.disabled = true;

    try {
        const resp = await apiPost(`/api/plan/workouts/${workoutId}/sync`, {});
        btn.textContent = 'Synced!';
        btn.style.background = 'var(--green)';
        btn.style.color = 'var(--bg)';
        setTimeout(() => {
            btn.textContent = origText;
            btn.disabled = false;
            btn.style.background = '';
            btn.style.color = '';
        }, 3000);
    } catch (e) {
        btn.textContent = 'Sync failed';
        btn.style.background = 'var(--red)';
        setTimeout(() => {
            btn.textContent = origText;
            btn.disabled = false;
            btn.style.background = '';
        }, 3000);
        console.error('Garmin sync error:', e);
    }
}

async function showTemplateDetail(templateId) {
    const panel = document.getElementById('workout-detail');
    panel.style.display = 'block';
    document.getElementById('workout-detail-title').textContent = 'Loading...';
    document.getElementById('workout-detail-summary').innerHTML = '';
    document.getElementById('workout-steps-table').innerHTML = '';
    document.getElementById('workout-detail-actions').innerHTML = '';

    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });

    try {
        const t = await api(`/api/plan/templates/${templateId}`);
        renderWorkoutDetail(t);
    } catch (e) {
        document.getElementById('workout-detail-title').textContent = 'Error loading template';
        console.error('Template detail error:', e);
    }
}

// Save workout athlete notes
document.getElementById('workout-notes-save')?.addEventListener('click', async () => {
    if (!_currentViewWorkoutId) return;
    const status = document.getElementById('workout-notes-status');
    try {
        await fetch(`/api/plan/workouts/${_currentViewWorkoutId}/notes`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                athlete_notes: document.getElementById('workout-athlete-notes').value || null,
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

// Initialize
initWorkoutViewer();
