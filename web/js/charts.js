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

    const labels = { 5: '5s', 30: '30s', 60: '1min', 300: '5min', 1200: '20min', 3600: '60min' };

    powerCurveChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.map(d => labels[d.duration_s] || d.duration_s + 's'),
            datasets: [{
                label: 'Best Power (watts)',
                data: data.map(d => d.power),
                backgroundColor: data.map((_, i) => {
                    const colors = ['#e94560', '#f5c518', '#00d4aa', '#0f3460', '#9b59b6', '#3498db'];
                    return colors[i % colors.length];
                }),
            }],
        },
        options: {
            ...chartDefaults,
            plugins: {
                ...chartDefaults.plugins,
                tooltip: {
                    callbacks: {
                        afterLabel: (item) => `Date: ${data[item.dataIndex]?.date || ''}`,
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
