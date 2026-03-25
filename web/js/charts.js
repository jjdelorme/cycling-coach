/**
 * Chart.js chart configurations.
 */

const chartDefaults = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
        legend: { labels: { color: '#eee', font: { size: 11 } } },
    },
    scales: {
        x: { ticks: { color: '#999', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.05)' } },
        y: { ticks: { color: '#999', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.05)' } },
    },
};

let pmcChart, monthlyChart, powerCurveChart, efChart, zonesChart, ftpChart, rideTimelineChart;

function drawPMCChart(data) {
    const ctx = document.getElementById('pmc-chart').getContext('2d');
    if (pmcChart) pmcChart.destroy();

    // Downsample for performance (show every Nth point)
    const step = Math.max(1, Math.floor(data.length / 365));
    const filtered = data.filter((_, i) => i % step === 0 || i === data.length - 1);

    pmcChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: filtered.map(d => d.date),
            datasets: [
                {
                    label: 'CTL (Fitness)',
                    data: filtered.map(d => d.ctl),
                    borderColor: '#00d4aa',
                    borderWidth: 2,
                    pointRadius: 0,
                    fill: false,
                },
                {
                    label: 'ATL (Fatigue)',
                    data: filtered.map(d => d.atl),
                    borderColor: '#e94560',
                    borderWidth: 2,
                    pointRadius: 0,
                    fill: false,
                },
                {
                    label: 'TSB (Form)',
                    data: filtered.map(d => d.tsb),
                    borderColor: '#f5c518',
                    borderWidth: 1.5,
                    pointRadius: 0,
                    fill: true,
                    backgroundColor: 'rgba(245, 197, 24, 0.05)',
                },
            ],
        },
        options: {
            ...chartDefaults,
            plugins: {
                ...chartDefaults.plugins,
                tooltip: {
                    callbacks: {
                        title: (items) => items[0]?.label || '',
                    },
                },
            },
        },
    });
}

function drawMonthlyChart(data) {
    const ctx = document.getElementById('monthly-chart').getContext('2d');
    if (monthlyChart) monthlyChart.destroy();

    monthlyChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.map(d => d.month),
            datasets: [
                {
                    label: 'Hours',
                    data: data.map(d => d.duration_h),
                    backgroundColor: 'rgba(0, 212, 170, 0.6)',
                    yAxisID: 'y',
                },
                {
                    label: 'TSS',
                    data: data.map(d => d.tss),
                    backgroundColor: 'rgba(233, 69, 96, 0.4)',
                    yAxisID: 'y1',
                },
            ],
        },
        options: {
            ...chartDefaults,
            scales: {
                ...chartDefaults.scales,
                y: { ...chartDefaults.scales.y, position: 'left', title: { display: true, text: 'Hours', color: '#999' } },
                y1: { ...chartDefaults.scales.y, position: 'right', title: { display: true, text: 'TSS', color: '#999' }, grid: { drawOnChartArea: false } },
            },
        },
    });
}

function drawPowerCurveChart(data) {
    const ctx = document.getElementById('power-curve-chart').getContext('2d');
    if (powerCurveChart) powerCurveChart.destroy();

    // Sort by duration and build scatter points for the curve
    const sorted = [...data].sort((a, b) => a.duration_s - b.duration_s);
    const points = sorted.map(d => ({ x: d.duration_s, y: d.power }));

    // Format duration for axis labels and tooltips
    function fmtDur(s) {
        if (s < 60) return s + 's';
        if (s < 3600) return Math.round(s / 60) + 'min';
        return (s / 3600).toFixed(1).replace('.0', '') + 'h';
    }

    powerCurveChart = new Chart(ctx, {
        type: 'line',
        data: {
            datasets: [{
                label: 'Best Power',
                data: points,
                borderColor: '#00d4aa',
                borderWidth: 2.5,
                pointRadius: 5,
                pointBackgroundColor: '#00d4aa',
                pointBorderColor: '#1a1a2e',
                pointBorderWidth: 2,
                pointHoverRadius: 8,
                fill: true,
                backgroundColor: 'rgba(0, 212, 170, 0.1)',
                tension: 0.4,
                cubicInterpolationMode: 'monotone',
            }],
        },
        options: {
            ...chartDefaults,
            scales: {
                x: {
                    type: 'logarithmic',
                    title: { display: true, text: 'Duration', color: '#999' },
                    ticks: {
                        color: '#999',
                        font: { size: 10 },
                        callback: (val) => fmtDur(val),
                        autoSkip: false,
                    },
                    afterBuildTicks: (axis) => {
                        axis.ticks = [5, 30, 60, 300, 1200, 3600].map(v => ({ value: v }));
                    },
                    grid: { color: 'rgba(255,255,255,0.05)' },
                },
                y: {
                    type: 'logarithmic',
                    title: { display: true, text: 'Power (watts)', color: '#999' },
                    ticks: {
                        color: '#999',
                        font: { size: 10 },
                        callback: (val) => val >= 1000 ? (val/1000) + 'kw' : val + 'w',
                        autoSkip: false,
                    },
                    afterBuildTicks: (axis) => {
                        axis.ticks = [100, 200, 300, 500, 750, 1000, 2000, 3000, 5000]
                            .filter(v => v >= (axis.min * 0.8) && v <= (axis.max * 1.2))
                            .map(v => ({ value: v }));
                    },
                    grid: { color: 'rgba(255,255,255,0.05)' },
                },
            },
            plugins: {
                ...chartDefaults.plugins,
                tooltip: {
                    callbacks: {
                        title: (items) => fmtDur(items[0]?.parsed?.x || 0),
                        label: (item) => {
                            const d = sorted[item.dataIndex];
                            return `${Math.round(item.parsed.y)}w (${d?.date || ''})`;
                        },
                    },
                },
            },
        },
    });
}

function drawEFChart(data) {
    const ctx = document.getElementById('ef-chart').getContext('2d');
    if (efChart) efChart.destroy();

    // Filter to rides > 30min for meaningful EF
    const filtered = data.filter(d => d.duration_s > 1800);

    efChart = new Chart(ctx, {
        type: 'scatter',
        data: {
            datasets: [{
                label: 'Efficiency Factor (NP/HR)',
                data: filtered.map(d => ({ x: d.date, y: d.ef })),
                backgroundColor: 'rgba(0, 212, 170, 0.5)',
                pointRadius: 4,
            }],
        },
        options: {
            ...chartDefaults,
            scales: {
                x: { ...chartDefaults.scales.x, type: 'category', labels: filtered.map(d => d.date) },
                y: { ...chartDefaults.scales.y, title: { display: true, text: 'EF (NP/HR)', color: '#999' } },
            },
        },
    });
}

function drawZonesChart(data) {
    const ctx = document.getElementById('zones-chart').getContext('2d');
    if (zonesChart) zonesChart.destroy();

    const zoneNames = ['Z0 Coast', 'Z1 Recovery', 'Z2 Endurance', 'Z3 Tempo', 'Z4 Threshold', 'Z5 VO2max', 'Z6 Anaerobic'];
    const pcts = data.percentages;
    const colors = ['#666', '#3498db', '#00d4aa', '#f5c518', '#e67e22', '#e94560', '#9b59b6'];

    zonesChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: zoneNames,
            datasets: [{
                data: zoneNames.map((_, i) => pcts['z' + i] || 0),
                backgroundColor: colors,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'right', labels: { color: '#eee', font: { size: 11 } } },
            },
        },
    });
}

function drawFTPChart(data) {
    const ctx = document.getElementById('ftp-chart').getContext('2d');
    if (ftpChart) ftpChart.destroy();

    ftpChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.map(d => d.month),
            datasets: [
                {
                    label: 'FTP (watts)',
                    data: data.map(d => d.ftp),
                    borderColor: '#00d4aa',
                    borderWidth: 2,
                    pointRadius: 4,
                    pointBackgroundColor: '#00d4aa',
                    fill: false,
                    yAxisID: 'y',
                },
                {
                    label: 'W/kg',
                    data: data.map(d => d.w_per_kg),
                    borderColor: '#f5c518',
                    borderWidth: 2,
                    pointRadius: 4,
                    pointBackgroundColor: '#f5c518',
                    fill: false,
                    yAxisID: 'y1',
                },
            ],
        },
        options: {
            ...chartDefaults,
            scales: {
                ...chartDefaults.scales,
                y: { ...chartDefaults.scales.y, position: 'left', title: { display: true, text: 'FTP (watts)', color: '#999' } },
                y1: { ...chartDefaults.scales.y, position: 'right', title: { display: true, text: 'W/kg', color: '#999' }, grid: { drawOnChartArea: false } },
            },
        },
    });
}

function drawRideTimeline(ride, workout) {
    const container = document.querySelector('.ride-timeline-container');
    const canvas = document.getElementById('ride-timeline-chart');
    // Remove any previous "no data" message
    container.querySelector('.no-data-msg')?.remove();

    if (!ride.records || ride.records.length === 0) {
        if (rideTimelineChart) { rideTimelineChart.destroy(); rideTimelineChart = null; }
        canvas.style.display = 'none';
        const msg = document.createElement('p');
        msg.className = 'no-data-msg';
        msg.style.cssText = 'color:var(--text-muted);text-align:center;padding:2rem;';
        msg.textContent = 'No per-second data available for this ride.';
        container.appendChild(msg);
        return;
    }
    canvas.style.display = '';
    const ctx = canvas.getContext('2d');
    if (rideTimelineChart) rideTimelineChart.destroy();

    const records = ride.records;
    const step = Math.max(1, Math.floor(records.length / 800));
    const sampled = records.filter((_, i) => i % step === 0);
    const timeLabels = sampled.map((_, i) => {
        const totalSec = i * step;
        const h = Math.floor(totalSec / 3600);
        const m = Math.floor((totalSec % 3600) / 60);
        if (h > 0) return `${h}:${String(m).padStart(2, '0')}`;
        return `${m}m`;
    });

    // Build workout interval boxes as an annotation plugin
    const annotations = {};
    if (workout && workout.steps && workout.steps.length > 0) {
        const rideDurationS = records.length;
        const workoutDurationS = workout.total_duration_s || workout.steps.reduce((s, st) => s + st.duration_s, 0);

        workout.steps.forEach((s, idx) => {
            // Map workout time to chart index
            const xMin = Math.floor((s.start_s / rideDurationS) * sampled.length);
            const xMax = Math.floor(((s.start_s + s.duration_s) / rideDurationS) * sampled.length);
            const pct = s.power_pct || 0.5;

            annotations['wo' + idx] = {
                type: 'box',
                xMin: Math.max(0, xMin),
                xMax: Math.min(sampled.length - 1, xMax),
                yMin: 0,
                yMax: s.power_watts || 0,
                backgroundColor: _woZoneColor(pct, 0.18),
                borderColor: _woZoneColor(pct, 0.5),
                borderWidth: 1,
                borderRadius: 2,
                label: {
                    display: s.duration_s > (rideDurationS * 0.04),
                    content: s.label || s.type,
                    position: 'start',
                    color: 'rgba(255,255,255,0.6)',
                    font: { size: 9 },
                    padding: 2,
                },
            };
        });
    }

    const hasPower = sampled.some(r => r.power > 0);
    const datasets = [];

    if (hasPower) {
        datasets.push({
            label: 'Power (W)',
            data: sampled.map(r => r.power),
            borderColor: 'rgba(0, 212, 170, 0.8)',
            borderWidth: 1.2,
            pointRadius: 0,
            fill: true,
            backgroundColor: 'rgba(0, 212, 170, 0.08)',
            yAxisID: 'y',
            order: 2,
        });
    }

    datasets.push({
        label: 'HR (bpm)',
        data: sampled.map(r => r.heart_rate),
        borderColor: 'rgba(233, 69, 96, 0.7)',
        borderWidth: 1.2,
        pointRadius: 0,
        fill: false,
        yAxisID: 'y1',
        order: 3,
    });

    const hasCadence = sampled.some(r => r.cadence > 0);
    if (hasCadence) {
        datasets.push({
            label: 'Cadence',
            data: sampled.map(r => r.cadence),
            borderColor: 'rgba(245, 197, 24, 0.5)',
            borderWidth: 1,
            pointRadius: 0,
            fill: false,
            yAxisID: 'y2',
            order: 4,
        });
    }

    const hasElevation = sampled.some(r => r.altitude > 0);
    if (hasElevation) {
        datasets.push({
            label: 'Elevation',
            data: sampled.map(r => r.altitude),
            borderColor: 'rgba(255, 255, 255, 0.15)',
            borderWidth: 1,
            pointRadius: 0,
            fill: true,
            backgroundColor: 'rgba(255, 255, 255, 0.04)',
            yAxisID: 'y3',
            order: 5,
        });
    }

    // Crosshair plugin
    const crosshairPlugin = {
        id: 'rideCrosshair',
        afterDraw(chart) {
            const meta = chart._rideMeta;
            if (!meta) return;

            const { ctx: c, chartArea: { top, bottom, left, right } } = chart;

            // Draw selection highlight
            if (meta.selStart !== null && meta.selEnd !== null) {
                const x1 = chart.scales.x.getPixelForValue(Math.min(meta.selStart, meta.selEnd));
                const x2 = chart.scales.x.getPixelForValue(Math.max(meta.selStart, meta.selEnd));
                c.save();
                c.fillStyle = 'rgba(0, 212, 170, 0.12)';
                c.fillRect(x1, top, x2 - x1, bottom - top);
                c.strokeStyle = 'rgba(0, 212, 170, 0.5)';
                c.lineWidth = 1;
                c.strokeRect(x1, top, x2 - x1, bottom - top);
                c.restore();
            }

            // Draw crosshair line
            if (meta.hoverIdx !== null) {
                const x = chart.scales.x.getPixelForValue(meta.hoverIdx);
                c.save();
                c.beginPath();
                c.moveTo(x, top);
                c.lineTo(x, bottom);
                c.strokeStyle = 'rgba(255,255,255,0.4)';
                c.lineWidth = 1;
                c.setLineDash([4, 3]);
                c.stroke();
                c.restore();
            }
        }
    };

    rideTimelineChart = new Chart(ctx, {
        type: 'line',
        data: { labels: timeLabels, datasets },
        plugins: [crosshairPlugin],
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: {
                    labels: { color: '#eee', font: { size: 11 }, usePointStyle: true, pointStyle: 'line' },
                    onClick: (e, legendItem, legend) => {
                        const idx = legendItem.datasetIndex;
                        const ci = legend.chart;
                        ci.getDatasetMeta(idx).hidden = !ci.getDatasetMeta(idx).hidden;
                        ci.update();
                    },
                },
                tooltip: { enabled: false },
                annotation: { annotations },
            },
            scales: {
                x: {
                    ticks: { color: '#999', font: { size: 10 }, maxTicksLimit: 20 },
                    grid: { color: 'rgba(255,255,255,0.05)' },
                },
                y: {
                    type: 'linear',
                    position: 'left',
                    title: { display: true, text: 'Watts', color: '#00d4aa', font: { size: 11 } },
                    ticks: { color: '#999', font: { size: 10 } },
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    beginAtZero: true,
                },
                y1: {
                    type: 'linear',
                    position: 'right',
                    title: { display: true, text: 'BPM', color: '#e94560', font: { size: 11 } },
                    ticks: { color: '#999', font: { size: 10 } },
                    grid: { drawOnChartArea: false },
                },
                y2: {
                    type: 'linear',
                    position: 'right',
                    display: false,
                    beginAtZero: true,
                    grid: { drawOnChartArea: false },
                },
                y3: {
                    type: 'linear',
                    position: 'right',
                    display: false,
                    grid: { drawOnChartArea: false },
                },
            },
        },
    });

    // Build workout step lookup: maps sample index -> step info
    let _woStepLookup = null;
    if (workout && workout.steps && workout.steps.length > 0) {
        const rideDurationS = records.length;
        _woStepLookup = (sampleIdx) => {
            const timeSec = sampleIdx * step;
            for (const s of workout.steps) {
                if (timeSec >= s.start_s && timeSec < s.start_s + s.duration_s) {
                    return s;
                }
            }
            return null;
        };
    }

    // Interactive crosshair + selection state
    rideTimelineChart._rideMeta = {
        hoverIdx: null,
        selStart: null,
        selEnd: null,
        dragging: false,
        locked: false,  // locked = selection made, waiting for click to reset
        sampled,
        step,
        woStepLookup: _woStepLookup,
    };

    const tooltip = document.getElementById('ride-crosshair-tooltip');
    const selStats = document.getElementById('ride-selection-stats');

    canvas.addEventListener('mousemove', (e) => {
        const meta = rideTimelineChart._rideMeta;
        const rect = canvas.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const chartArea = rideTimelineChart.chartArea;
        if (!chartArea) return;

        if (x < chartArea.left || x > chartArea.right) {
            meta.hoverIdx = null;
            tooltip.style.display = 'none';
            rideTimelineChart.draw();
            return;
        }

        const idx = rideTimelineChart.scales.x.getValueForPixel(x);
        const i = Math.round(Math.max(0, Math.min(idx, sampled.length - 1)));
        meta.hoverIdx = i;

        // Update dragging selection
        if (meta.dragging && !meta.locked) {
            meta.selEnd = i;
        }

        // Show tooltip
        const rec = sampled[i];
        if (rec) {
            const timeSec = i * step;
            const h = Math.floor(timeSec / 3600);
            const m = Math.floor((timeSec % 3600) / 60);
            const s = timeSec % 60;
            const timeStr = h > 0 ? `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}` : `${m}:${String(s).padStart(2,'0')}`;

            let html = `<div><span class="tt-label">Time:</span> ${timeStr}</div>`;
            if (hasPower) html += `<div><span class="tt-label">Power:</span> <span class="tt-power">${rec.power || 0}w</span></div>`;
            html += `<div><span class="tt-label">HR:</span> <span class="tt-hr">${rec.heart_rate || 0}</span></div>`;
            if (hasCadence) html += `<div><span class="tt-label">Cadence:</span> <span class="tt-cadence">${rec.cadence || 0}</span></div>`;
            if (rec.speed) html += `<div><span class="tt-label">Speed:</span> <span class="tt-speed">${(rec.speed * 3.6).toFixed(1)} km/h</span></div>`;
            if (rec.altitude) html += `<div><span class="tt-label">Elevation:</span> <span style="color:#888;font-weight:600">${Math.round(rec.altitude)}m</span></div>`;
            if (_woStepLookup) {
                const woStep = _woStepLookup(i);
                if (woStep) {
                    const targetStr = woStep.power_low_watts && woStep.power_high_watts
                        ? `${woStep.power_low_watts}-${woStep.power_high_watts}w`
                        : `${woStep.power_watts}w`;
                    html += `<div style="border-top:1px solid var(--border);margin-top:3px;padding-top:3px;"><span class="tt-label">Target:</span> <span style="color:var(--yellow);font-weight:600">${targetStr}</span></div>`;
                    html += `<div><span class="tt-label" style="font-size:0.7rem">${woStep.label || woStep.type}</span></div>`;
                }
            }
            tooltip.innerHTML = html;
            tooltip.style.display = 'block';
        }

        rideTimelineChart.draw();

        // Update selection stats while dragging
        if (meta.dragging && meta.selStart !== null && meta.selEnd !== null) {
            _showSelectionStats(meta, sampled, hasPower, hasCadence, selStats, _woStepLookup);
        }
    });

    canvas.addEventListener('mouseleave', () => {
        const meta = rideTimelineChart._rideMeta;
        meta.hoverIdx = null;
        if (!meta.locked) {
            meta.dragging = false;
            meta.selStart = null;
            meta.selEnd = null;
            selStats.style.display = 'none';
        }
        tooltip.style.display = 'none';
        rideTimelineChart.draw();
    });

    canvas.addEventListener('mousedown', (e) => {
        const meta = rideTimelineChart._rideMeta;
        if (meta.locked) {
            // Click to reset
            meta.locked = false;
            meta.selStart = null;
            meta.selEnd = null;
            meta.dragging = false;
            selStats.style.display = 'none';
            rideTimelineChart.draw();
            return;
        }

        const rect = canvas.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const chartArea = rideTimelineChart.chartArea;
        if (!chartArea || x < chartArea.left || x > chartArea.right) return;

        const idx = Math.round(rideTimelineChart.scales.x.getValueForPixel(x));
        meta.selStart = Math.max(0, Math.min(idx, sampled.length - 1));
        meta.selEnd = meta.selStart;
        meta.dragging = true;
    });

    canvas.addEventListener('mouseup', () => {
        const meta = rideTimelineChart._rideMeta;
        if (meta.dragging) {
            meta.dragging = false;
            if (meta.selStart !== null && meta.selEnd !== null && Math.abs(meta.selEnd - meta.selStart) > 2) {
                meta.locked = true;
                _showSelectionStats(meta, sampled, hasPower, hasCadence, selStats, _woStepLookup);
            } else {
                meta.selStart = null;
                meta.selEnd = null;
                selStats.style.display = 'none';
            }
            rideTimelineChart.draw();
        }
    });

    canvas.style.cursor = 'crosshair';
}

function _woZoneColor(pct, alpha) {
    if (pct < 0.56) return `rgba(126, 200, 227, ${alpha})`;
    if (pct < 0.76) return `rgba(0, 212, 170, ${alpha})`;
    if (pct < 0.91) return `rgba(245, 197, 24, ${alpha})`;
    if (pct < 1.06) return `rgba(232, 145, 58, ${alpha})`;
    if (pct < 1.21) return `rgba(233, 69, 96, ${alpha})`;
    return `rgba(155, 89, 182, ${alpha})`;
}

function _showSelectionStats(meta, sampled, hasPower, hasCadence, el, woStepLookup) {
    const lo = Math.min(meta.selStart, meta.selEnd);
    const hi = Math.max(meta.selStart, meta.selEnd);
    const slice = sampled.slice(lo, hi + 1);
    if (slice.length === 0) return;

    const avg = (arr) => arr.length ? Math.round(arr.reduce((a, b) => a + b, 0) / arr.length) : 0;
    const durationSec = slice.length * meta.step;
    const durMin = Math.floor(durationSec / 60);
    const durSec = durationSec % 60;

    let html = `<div class="sel-item"><span class="sel-label">Duration:</span> <span class="sel-value">${durMin}:${String(durSec).padStart(2,'0')}</span></div>`;
    if (hasPower) {
        const powers = slice.map(r => r.power).filter(v => v > 0);
        html += `<div class="sel-item"><span class="sel-label">Avg Power:</span> <span class="sel-value" style="color:var(--green)">${avg(powers)}w</span></div>`;
    }
    const hrs = slice.map(r => r.heart_rate).filter(v => v > 0);
    html += `<div class="sel-item"><span class="sel-label">Avg HR:</span> <span class="sel-value" style="color:var(--red)">${avg(hrs)}</span></div>`;
    if (hasCadence) {
        const cads = slice.map(r => r.cadence).filter(v => v > 0);
        html += `<div class="sel-item"><span class="sel-label">Avg Cadence:</span> <span class="sel-value" style="color:var(--yellow)">${avg(cads)}</span></div>`;
    }

    // Weighted average target power from workout steps across selection
    if (woStepLookup) {
        let targetSum = 0, targetCount = 0;
        for (let j = lo; j <= hi; j++) {
            const ws = woStepLookup(j);
            if (ws && ws.power_watts) {
                targetSum += ws.power_watts;
                targetCount++;
            }
        }
        if (targetCount > 0) {
            const avgTarget = Math.round(targetSum / targetCount);
            html += `<div class="sel-item"><span class="sel-label">Target:</span> <span class="sel-value" style="color:var(--yellow)">${avgTarget}w</span></div>`;
        }
    }

    el.innerHTML = html;
    el.style.display = 'flex';
}
