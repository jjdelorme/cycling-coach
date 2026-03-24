/**
 * Workout detail viewer - power profile visualization and ZWO export.
 */

let workoutChart = null;

function initWorkoutModal() {
    document.getElementById('workout-modal-close').addEventListener('click', closeWorkoutModal);
    document.getElementById('workout-modal').addEventListener('click', (e) => {
        if (e.target.id === 'workout-modal') closeWorkoutModal();
    });
}

function closeWorkoutModal() {
    document.getElementById('workout-modal').style.display = 'none';
    if (workoutChart) {
        workoutChart.destroy();
        workoutChart = null;
    }
}

async function showWorkoutDetail(workoutId) {
    const modal = document.getElementById('workout-modal');
    modal.style.display = 'flex';
    document.getElementById('workout-modal-title').textContent = 'Loading...';
    document.getElementById('workout-modal-summary').innerHTML = '';
    document.getElementById('workout-steps-table').innerHTML = '';
    document.getElementById('workout-modal-actions').innerHTML = '';

    try {
        const w = await api(`/api/plan/workouts/${workoutId}`);
        renderWorkoutDetail(w);
    } catch (e) {
        document.getElementById('workout-modal-title').textContent = 'Error loading workout';
        console.error('Workout detail error:', e);
    }
}

function renderWorkoutDetail(w) {
    document.getElementById('workout-modal-title').textContent = w.name || 'Workout';

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

    document.getElementById('workout-modal-summary').innerHTML = `
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
        actionsHtml += `<a href="/api/plan/workouts/${w.id}/download?fmt=fit" download><button>Download .FIT (Garmin)</button></a>`;
        actionsHtml += `<a href="/api/plan/workouts/${w.id}/download?fmt=zwo" download><button class="btn-secondary">Download .ZWO</button></a>`;
    }
    document.getElementById('workout-modal-actions').innerHTML = actionsHtml;
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

    // Build bar-like segments: each step becomes one or more data points
    const labels = [];
    const data = [];
    const bgColors = [];
    const borderColors = [];

    for (const step of w.steps) {
        // For warmup/cooldown, show as gradient with multiple sub-segments
        if (step.type === 'Warmup' || step.type === 'Cooldown') {
            const segs = 5;
            const segDur = step.duration_s / segs;
            const lowW = step.power_low_watts || Math.round(step.power_watts * 0.7);
            const highW = step.power_high_watts || Math.round(step.power_watts * 1.3);
            for (let i = 0; i < segs; i++) {
                const t = i / (segs - 1);
                const watts = step.type === 'Warmup'
                    ? Math.round(lowW + t * (highW - lowW))
                    : Math.round(highW + t * (lowW - highW));
                const startSec = step.start_s + i * segDur;
                labels.push(fmtTime(startSec));
                data.push({ x: segDur, y: watts });
                bgColors.push(zoneColor(watts / w.ftp, 0.7));
                borderColors.push(zoneColor(watts / w.ftp, 1));
            }
        } else {
            labels.push(fmtTime(step.start_s));
            data.push({ x: step.duration_s, y: step.power_watts });
            bgColors.push(zoneColor(step.power_pct, 0.7));
            borderColors.push(zoneColor(step.power_pct, 1));
        }
    }

    // Use a bar chart where bar width represents duration
    workoutChart = new Chart(canvas, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Power (watts)',
                data: data.map(d => d.y),
                backgroundColor: bgColors,
                borderColor: borderColors,
                borderWidth: 1,
                borderRadius: 2,
                barPercentage: 1.0,
                categoryPercentage: 1.0,
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
                            const durMin = Math.round(data[i].x / 60);
                            return `${labels[i]} — ${durMin}min`;
                        },
                        label: (item) => {
                            const watts = item.raw;
                            const pct = Math.round((watts / w.ftp) * 100);
                            return `${watts}w (${pct}% FTP)`;
                        },
                    },
                },
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#999', font: { size: 10 } },
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

// Initialize
initWorkoutModal();
