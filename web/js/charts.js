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

let pmcChart, monthlyChart, powerCurveChart, efChart, zonesChart, ftpChart, ridePowerChart, rideHRChart;

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

function drawRideCharts(ride) {
    if (!ride.records || ride.records.length === 0) return;

    const records = ride.records;
    // Downsample to ~500 points
    const step = Math.max(1, Math.floor(records.length / 500));
    const sampled = records.filter((_, i) => i % step === 0);
    const timeLabels = sampled.map((_, i) => Math.round(i * step / 60) + 'm');

    // Power chart
    const pCtx = document.getElementById('ride-power-chart').getContext('2d');
    if (ridePowerChart) ridePowerChart.destroy();
    ridePowerChart = new Chart(pCtx, {
        type: 'line',
        data: {
            labels: timeLabels,
            datasets: [{
                label: 'Power (watts)',
                data: sampled.map(r => r.power),
                borderColor: 'rgba(0, 212, 170, 0.7)',
                borderWidth: 1,
                pointRadius: 0,
                fill: true,
                backgroundColor: 'rgba(0, 212, 170, 0.1)',
            }],
        },
        options: chartDefaults,
    });

    // HR chart
    const hCtx = document.getElementById('ride-hr-chart').getContext('2d');
    if (rideHRChart) rideHRChart.destroy();
    rideHRChart = new Chart(hCtx, {
        type: 'line',
        data: {
            labels: timeLabels,
            datasets: [{
                label: 'Heart Rate (bpm)',
                data: sampled.map(r => r.heart_rate),
                borderColor: 'rgba(233, 69, 96, 0.7)',
                borderWidth: 1,
                pointRadius: 0,
                fill: true,
                backgroundColor: 'rgba(233, 69, 96, 0.1)',
            }],
        },
        options: chartDefaults,
    });
}
