/**
 * Calendar view - monthly calendar with ride and planned workout data.
 */

let calYear, calMonth;

function initCalendar() {
    const now = new Date();
    calYear = now.getFullYear();
    calMonth = now.getMonth(); // 0-indexed
    renderCalendar();

    document.getElementById('cal-prev').addEventListener('click', () => {
        calMonth--;
        if (calMonth < 0) { calMonth = 11; calYear--; }
        renderCalendar();
    });

    document.getElementById('cal-next').addEventListener('click', () => {
        calMonth++;
        if (calMonth > 11) { calMonth = 0; calYear++; }
        renderCalendar();
    });
}

async function renderCalendar() {
    const monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'];
    document.getElementById('cal-month-label').textContent = `${monthNames[calMonth]} ${calYear}`;

    const startStr = `${calYear}-${String(calMonth + 1).padStart(2, '0')}-01`;
    const endDate = new Date(calYear, calMonth + 1, 0);
    const endStr = `${calYear}-${String(calMonth + 1).padStart(2, '0')}-${String(endDate.getDate()).padStart(2, '0')}`;

    let rides = [], planned = [];
    try {
        [rides, planned] = await Promise.all([
            api(`/api/rides?start_date=${startStr}&end_date=${endStr}&limit=100`),
            api(`/api/plan/week/${startStr}`).then(d => d.planned).catch(() => []),
        ]);
        // Also fetch all planned for the month
        const allWeeks = [];
        let d = new Date(calYear, calMonth, 1);
        while (d.getMonth() === calMonth) {
            const dateStr = d.toISOString().slice(0, 10);
            allWeeks.push(api(`/api/plan/week/${dateStr}`).then(w => w.planned).catch(() => []));
            d.setDate(d.getDate() + 7);
        }
        const weekResults = await Promise.all(allWeeks);
        planned = weekResults.flat();
    } catch (e) {
        console.error('Calendar data error:', e);
    }

    // Build lookup maps
    const ridesByDate = {};
    rides.forEach(r => {
        if (!ridesByDate[r.date]) ridesByDate[r.date] = [];
        ridesByDate[r.date].push(r);
    });

    const plannedByDate = {};
    planned.forEach(p => {
        if (p.date && !plannedByDate[p.date]) plannedByDate[p.date] = [];
        if (p.date) plannedByDate[p.date].push(p);
    });

    const grid = document.getElementById('calendar-grid');
    const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    let html = dayNames.map(d => `<div class="cal-header">${d}</div>`).join('');

    const firstDay = new Date(calYear, calMonth, 1);
    let startDow = firstDay.getDay(); // 0=Sunday
    startDow = startDow === 0 ? 6 : startDow - 1; // Convert to Mon=0

    // Empty cells before first day
    for (let i = 0; i < startDow; i++) {
        html += '<div class="cal-day empty"></div>';
    }

    const daysInMonth = endDate.getDate();
    for (let day = 1; day <= daysInMonth; day++) {
        const dateStr = `${calYear}-${String(calMonth + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        const dayRides = ridesByDate[dateStr] || [];
        const dayPlanned = plannedByDate[dateStr] || [];

        let content = `<div class="day-num">${day}</div>`;

        dayRides.forEach(r => {
            const tss = r.tss ? Math.round(r.tss) : 0;
            content += `<div class="day-ride">${r.sub_sport || 'ride'} ${tss ? tss + 'TSS' : ''}</div>`;
        });

        dayPlanned.forEach(p => {
            content += `<div class="day-planned">${p.name || 'planned'}</div>`;
        });

        if (dayRides.length > 0) {
            const totalTss = dayRides.reduce((s, r) => s + (r.tss || 0), 0);
            if (totalTss > 0) content += `<div class="day-tss">${Math.round(totalTss)} TSS</div>`;
        }

        html += `<div class="cal-day" data-date="${dateStr}">${content}</div>`;
    }

    grid.innerHTML = html;

    // Click handler for day detail
    grid.querySelectorAll('.cal-day:not(.empty)').forEach(el => {
        el.addEventListener('click', () => showDayDetail(el.dataset.date, ridesByDate, plannedByDate));
    });
}

function showDayDetail(date, ridesByDate, plannedByDate) {
    const detail = document.getElementById('day-detail');
    const dayRides = ridesByDate[date] || [];
    const dayPlanned = plannedByDate[date] || [];

    let html = `<h3>${date}</h3>`;

    if (dayRides.length > 0) {
        html += '<h4>Rides</h4>';
        dayRides.forEach(r => {
            html += `<p>${r.sub_sport || r.sport}: ${fmtDuration(r.duration_s)}, ${fmtDistance(r.distance_m)}, ${r.tss ? Math.round(r.tss) + ' TSS' : ''}, Power: ${r.avg_power || '--'}w / NP: ${r.normalized_power || '--'}w, HR: ${r.avg_hr || '--'}</p>`;
        });
    }

    if (dayPlanned.length > 0) {
        html += '<h4>Planned</h4>';
        dayPlanned.forEach(p => {
            html += `<p>${p.name || 'Workout'} (${Math.round((p.total_duration_s || 0) / 60)}min)</p>`;
        });
    }

    if (dayRides.length === 0 && dayPlanned.length === 0) {
        html += '<p>Rest day</p>';
    }

    detail.innerHTML = html;
    detail.classList.add('visible');
}
