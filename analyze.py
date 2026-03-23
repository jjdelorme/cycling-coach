#!/usr/bin/env python3
"""
Comprehensive training analysis tool for cycling coaching.
Reads all JSON ride files and ZWO planned workouts, produces a full season report.
"""

import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from collections import defaultdict
import math

BASE_DIR = '/home/jasondel/dev/coach'
PLANNED_DIR = os.path.join(BASE_DIR, 'planned_workouts')

# ─── DATA LOADING ───────────────────────────────────────────────────────────

def load_ride(filepath):
    """Extract key metrics from a single ride JSON file."""
    with open(filepath) as f:
        data = json.load(f)

    session = data.get('session', [{}])[0]
    sport = data.get('sport', [{}])[0]
    user = data.get('user_profile', [{}])[0]
    records = data.get('record', [])

    ride = {
        'file': os.path.basename(filepath),
        'date': session.get('start_time', session.get('timestamp', '')),
        'sport': sport.get('sport', 'unknown'),
        'sub_sport': sport.get('sub_sport', 'unknown'),
        'sport_name': sport.get('name', ''),
        'duration_s': session.get('total_timer_time', 0),
        'elapsed_s': session.get('total_elapsed_time', 0),
        'distance_m': session.get('total_distance', 0),
        'avg_power': session.get('avg_power', 0),
        'normalized_power': session.get('normalized_power', 0),
        'max_power': session.get('max_power', 0),
        'avg_hr': session.get('avg_heart_rate', 0),
        'max_hr': session.get('max_heart_rate', 0),
        'avg_cadence': session.get('avg_cadence', 0),
        'total_ascent': session.get('total_ascent', 0),
        'total_descent': session.get('total_descent', 0),
        'total_calories': session.get('total_calories', 0),
        'tss': session.get('training_stress_score', 0),
        'intensity_factor': session.get('intensity_factor', 0),
        'ftp': session.get('threshold_power', 0),
        'total_work_kj': (session.get('total_work', 0) or 0) / 1000,
        'training_effect': session.get('total_training_effect', 0),
        'anaerobic_te': session.get('total_anaerobic_training_effect', 0),
        'avg_temp': session.get('avg_temperature', None),
        'weight': user.get('weight', None),
        'age': user.get('age', None),
    }

    # Compute power distribution from records
    if records:
        powers = [r.get('power', 0) for r in records if r.get('power') is not None]
        hrs = [r.get('heart_rate', 0) for r in records if r.get('heart_rate') is not None]
        ride['record_count'] = len(records)

        if powers:
            ride['power_samples'] = len(powers)
            # Power zones (based on FTP)
            ftp = ride['ftp'] or 244  # fallback
            ride['time_z1'] = sum(1 for p in powers if p < ftp * 0.55)
            ride['time_z2'] = sum(1 for p in powers if ftp * 0.55 <= p < ftp * 0.75)
            ride['time_z3'] = sum(1 for p in powers if ftp * 0.75 <= p < ftp * 0.90)
            ride['time_z4'] = sum(1 for p in powers if ftp * 0.90 <= p < ftp * 1.05)
            ride['time_z5'] = sum(1 for p in powers if ftp * 1.05 <= p < ftp * 1.20)
            ride['time_z6'] = sum(1 for p in powers if p >= ftp * 1.20)
            ride['time_z0'] = sum(1 for p in powers if p == 0)

            # Variability Index
            if ride['avg_power'] and ride['avg_power'] > 0:
                ride['variability_index'] = (ride['normalized_power'] or 0) / ride['avg_power']
            else:
                ride['variability_index'] = 0

            # Compute 20-min best power (rolling window)
            if len(powers) >= 1200:
                window = 1200
                best_20 = max(sum(powers[i:i+window]) / window for i in range(len(powers) - window + 1))
                ride['best_20min_power'] = round(best_20)
            else:
                ride['best_20min_power'] = None

            # Compute 5-min best power
            if len(powers) >= 300:
                window = 300
                best_5 = max(sum(powers[i:i+window]) / window for i in range(len(powers) - window + 1))
                ride['best_5min_power'] = round(best_5)
            else:
                ride['best_5min_power'] = None

            # 1-min best power
            if len(powers) >= 60:
                window = 60
                best_1 = max(sum(powers[i:i+window]) / window for i in range(len(powers) - window + 1))
                ride['best_1min_power'] = round(best_1)
            else:
                ride['best_1min_power'] = None

        if hrs:
            ftp_hr = ride.get('max_hr', 185)  # approximate LTHR
            ride['hr_z1'] = sum(1 for h in hrs if h < ftp_hr * 0.68)
            ride['hr_z2'] = sum(1 for h in hrs if ftp_hr * 0.68 <= h < ftp_hr * 0.83)
            ride['hr_z3'] = sum(1 for h in hrs if ftp_hr * 0.83 <= h < ftp_hr * 0.94)
            ride['hr_z4'] = sum(1 for h in hrs if ftp_hr * 0.94 <= h < ftp_hr * 1.05)
            ride['hr_z5'] = sum(1 for h in hrs if h >= ftp_hr * 1.05)
    else:
        ride['record_count'] = 0

    return ride


def load_planned_workout(filepath):
    """Extract key info from a ZWO planned workout file."""
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
    except ET.ParseError:
        return None

    fname = os.path.basename(filepath)
    date_str = fname[:10]

    name_el = root.find('name')
    sport_el = root.find('sportType')
    workout_el = root.find('workout')

    total_duration = 0
    intervals = []
    if workout_el is not None:
        for child in workout_el:
            dur = float(child.get('Duration', 0))
            total_duration += dur
            power = child.get('Power') or child.get('PowerLow')
            power_high = child.get('PowerHigh')
            intervals.append({
                'type': child.tag,
                'duration': dur,
                'power': float(power) if power else None,
                'power_high': float(power_high) if power_high else None,
            })

    return {
        'file': fname,
        'date': date_str,
        'name': name_el.text if name_el is not None else fname,
        'sport': sport_el.text if sport_el is not None else 'bike',
        'total_duration_s': total_duration,
        'total_duration_min': round(total_duration / 60),
        'interval_count': len(intervals),
        'intervals': intervals,
    }


def load_all_rides():
    rides = []
    json_files = sorted([f for f in os.listdir(BASE_DIR) if f.endswith('.json')])
    for f in json_files:
        try:
            ride = load_ride(os.path.join(BASE_DIR, f))
            if ride['duration_s'] and ride['duration_s'] > 0:
                rides.append(ride)
        except Exception as e:
            print(f"  WARN: Failed to load {f}: {e}", file=sys.stderr)
    return rides


def load_all_planned():
    planned = []
    if not os.path.isdir(PLANNED_DIR):
        return planned
    for f in sorted(os.listdir(PLANNED_DIR)):
        if f.endswith('.zwo'):
            pw = load_planned_workout(os.path.join(PLANNED_DIR, f))
            if pw:
                planned.append(pw)
    return planned


# ─── ANALYSIS ────────────────────────────────────────────────────────────────

def iso_week(date_str):
    """Return ISO year-week string from date."""
    try:
        dt = datetime.fromisoformat(date_str[:10])
        iso = dt.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    except:
        return "unknown"


def month_key(date_str):
    try:
        return date_str[:7]
    except:
        return "unknown"


def compute_ctl_atl_tsb(rides):
    """Compute daily CTL (fitness), ATL (fatigue), TSB (form) using exponential decay."""
    if not rides:
        return []

    dates = sorted(set(r['date'][:10] for r in rides if r.get('date')))
    if not dates:
        return []

    start = datetime.fromisoformat(dates[0])
    end = datetime.fromisoformat(dates[-1])

    # Daily TSS
    daily_tss = defaultdict(float)
    for r in rides:
        if r.get('date') and r.get('tss'):
            daily_tss[r['date'][:10]] += r['tss']

    ctl = 0
    atl = 0
    pmc = []
    day = start
    while day <= end:
        ds = day.strftime('%Y-%m-%d')
        tss = daily_tss.get(ds, 0)
        ctl = ctl + (tss - ctl) / 42
        atl = atl + (tss - atl) / 7
        tsb = ctl - atl
        pmc.append({
            'date': ds,
            'tss': round(tss, 1),
            'ctl': round(ctl, 1),
            'atl': round(atl, 1),
            'tsb': round(tsb, 1),
        })
        day += timedelta(days=1)

    return pmc


def weekly_summary(rides):
    """Aggregate rides by ISO week."""
    weeks = defaultdict(lambda: {
        'rides': 0, 'duration_h': 0, 'tss': 0, 'distance_km': 0,
        'ascent_m': 0, 'calories': 0, 'work_kj': 0,
        'best_20min': None, 'avg_if': [], 'sports': [],
    })

    for r in rides:
        wk = iso_week(r.get('date', ''))
        w = weeks[wk]
        w['rides'] += 1
        w['duration_h'] += (r.get('duration_s', 0) or 0) / 3600
        w['tss'] += r.get('tss', 0) or 0
        w['distance_km'] += (r.get('distance_m', 0) or 0) / 1000
        w['ascent_m'] += r.get('total_ascent', 0) or 0
        w['calories'] += r.get('total_calories', 0) or 0
        w['work_kj'] += r.get('total_work_kj', 0) or 0
        if r.get('intensity_factor'):
            w['avg_if'].append(r['intensity_factor'])
        if r.get('best_20min_power'):
            if w['best_20min'] is None or r['best_20min_power'] > w['best_20min']:
                w['best_20min'] = r['best_20min_power']
        w['sports'].append(r.get('sub_sport', 'unknown'))

    result = {}
    for wk, w in sorted(weeks.items()):
        w['duration_h'] = round(w['duration_h'], 1)
        w['tss'] = round(w['tss'], 1)
        w['distance_km'] = round(w['distance_km'], 1)
        w['ascent_m'] = round(w['ascent_m'])
        w['work_kj'] = round(w['work_kj'])
        w['avg_if'] = round(sum(w['avg_if']) / len(w['avg_if']), 3) if w['avg_if'] else 0
        w['sport_mix'] = dict((s, w['sports'].count(s)) for s in set(w['sports']))
        del w['sports']
        result[wk] = w

    return result


def monthly_summary(rides):
    """Aggregate rides by month."""
    months = defaultdict(lambda: {
        'rides': 0, 'duration_h': 0, 'tss': 0, 'distance_km': 0,
        'ascent_m': 0, 'calories': 0,
        'avg_power': [], 'avg_hr': [], 'best_20min': None,
    })

    for r in rides:
        mk = month_key(r.get('date', ''))
        m = months[mk]
        m['rides'] += 1
        m['duration_h'] += (r.get('duration_s', 0) or 0) / 3600
        m['tss'] += r.get('tss', 0) or 0
        m['distance_km'] += (r.get('distance_m', 0) or 0) / 1000
        m['ascent_m'] += r.get('total_ascent', 0) or 0
        m['calories'] += r.get('total_calories', 0) or 0
        if r.get('avg_power'):
            m['avg_power'].append(r['avg_power'])
        if r.get('avg_hr'):
            m['avg_hr'].append(r['avg_hr'])
        if r.get('best_20min_power'):
            if m['best_20min'] is None or r['best_20min_power'] > m['best_20min']:
                m['best_20min'] = r['best_20min_power']

    result = {}
    for mk, m in sorted(months.items()):
        m['duration_h'] = round(m['duration_h'], 1)
        m['tss'] = round(m['tss'])
        m['distance_km'] = round(m['distance_km'])
        m['ascent_m'] = round(m['ascent_m'])
        m['avg_power'] = round(sum(m['avg_power']) / len(m['avg_power'])) if m['avg_power'] else 0
        m['avg_hr'] = round(sum(m['avg_hr']) / len(m['avg_hr'])) if m['avg_hr'] else 0
        result[mk] = m

    return result


def planned_vs_actual(rides, planned):
    """Compare planned workouts to actual rides by date."""
    actual_by_date = defaultdict(list)
    for r in rides:
        if r.get('date'):
            actual_by_date[r['date'][:10]].append(r)

    planned_by_date = defaultdict(list)
    for p in planned:
        planned_by_date[p['date']].append(p)

    all_dates = sorted(set(list(actual_by_date.keys()) + list(planned_by_date.keys())))

    compliance = {'planned': 0, 'completed': 0, 'extra': 0, 'missed': 0}
    for d in all_dates:
        p_list = planned_by_date.get(d, [])
        a_list = actual_by_date.get(d, [])
        if p_list:
            compliance['planned'] += len(p_list)
            if a_list:
                compliance['completed'] += len(p_list)
            else:
                compliance['missed'] += len(p_list)
        if a_list and not p_list:
            compliance['extra'] += len(a_list)

    if compliance['planned'] > 0:
        compliance['compliance_pct'] = round(100 * compliance['completed'] / compliance['planned'], 1)
    else:
        compliance['compliance_pct'] = 0

    return compliance


def power_curve_bests(rides):
    """Track best power outputs across the season."""
    bests = {
        '1min': [], '5min': [], '20min': [],
    }
    for r in rides:
        date = r.get('date', '')[:10]
        if r.get('best_1min_power'):
            bests['1min'].append((date, r['best_1min_power']))
        if r.get('best_5min_power'):
            bests['5min'].append((date, r['best_5min_power']))
        if r.get('best_20min_power'):
            bests['20min'].append((date, r['best_20min_power']))

    result = {}
    for dur, entries in bests.items():
        if entries:
            entries.sort(key=lambda x: x[1], reverse=True)
            result[dur] = {
                'best': entries[0],
                'top5': entries[:5],
            }
    return result


def zone_distribution(rides):
    """Aggregate power zone distribution across all rides."""
    totals = {f'z{i}': 0 for i in range(7)}
    total_samples = 0
    for r in rides:
        for i in range(7):
            key = f'time_z{i}'
            if key in r:
                totals[f'z{i}'] += r[key]
                total_samples += r[key]

    if total_samples > 0:
        pcts = {k: round(100 * v / total_samples, 1) for k, v in totals.items()}
    else:
        pcts = totals

    return {'seconds': totals, 'percentages': pcts, 'total_samples': total_samples}


def ftp_progression(rides):
    """Track FTP changes over time."""
    ftp_by_date = {}
    for r in rides:
        if r.get('ftp') and r.get('date'):
            d = r['date'][:10]
            ftp_by_date[d] = r['ftp']

    # Group by month to show progression
    monthly = {}
    for d, ftp in sorted(ftp_by_date.items()):
        mk = d[:7]
        monthly[mk] = ftp  # last value for month

    return monthly


def identify_training_phases(weekly):
    """Identify build/recovery/peak phases based on TSS trends."""
    weeks = sorted(weekly.items())
    phases = []
    for i, (wk, data) in enumerate(weeks):
        tss = data['tss']
        prev_tss = weeks[i-1][1]['tss'] if i > 0 else tss
        if tss < prev_tss * 0.7 and tss < 300:
            phase = 'recovery'
        elif tss > 500:
            phase = 'build'
        elif data['duration_h'] > 12:
            phase = 'volume'
        else:
            phase = 'maintenance'
        phases.append((wk, phase, data))

    return phases


# ─── REPORT ──────────────────────────────────────────────────────────────────

def generate_report(rides, planned):
    report = {}

    # Athlete profile (from first ride with data)
    for r in rides:
        if r.get('weight') and r.get('age'):
            report['athlete'] = {
                'weight_kg': r['weight'],
                'age': r['age'],
                'ftp_start': r.get('ftp', 0),
            }
            break

    # Update with last ride info
    for r in reversed(rides):
        if r.get('ftp'):
            report['athlete']['ftp_current'] = r['ftp']
            if r.get('weight'):
                report['athlete']['weight_current'] = r['weight']
                report['athlete']['w_per_kg'] = round(r['ftp'] / r['weight'], 2)
            break

    # Date range
    dates = [r['date'][:10] for r in rides if r.get('date')]
    report['date_range'] = {'start': min(dates), 'end': max(dates), 'total_rides': len(rides)}

    # Season totals
    report['season_totals'] = {
        'total_hours': round(sum((r.get('duration_s', 0) or 0) / 3600 for r in rides), 1),
        'total_distance_km': round(sum((r.get('distance_m', 0) or 0) / 1000 for r in rides)),
        'total_ascent_m': round(sum(r.get('total_ascent', 0) or 0 for r in rides)),
        'total_tss': round(sum(r.get('tss', 0) or 0 for r in rides)),
        'total_calories': sum(r.get('total_calories', 0) or 0 for r in rides),
        'total_work_kj': round(sum(r.get('total_work_kj', 0) or 0 for r in rides)),
        'total_rides': len(rides),
    }

    report['monthly'] = monthly_summary(rides)
    report['weekly'] = weekly_summary(rides)
    report['pmc'] = compute_ctl_atl_tsb(rides)
    report['power_bests'] = power_curve_bests(rides)
    report['zone_distribution'] = zone_distribution(rides)
    report['ftp_progression'] = ftp_progression(rides)
    report['planned_vs_actual'] = planned_vs_actual(rides, planned)
    report['training_phases'] = [(wk, phase) for wk, phase, _ in identify_training_phases(report['weekly'])]

    # Sport type breakdown
    sport_hours = defaultdict(float)
    for r in rides:
        sport_hours[r.get('sub_sport', 'unknown')] += (r.get('duration_s', 0) or 0) / 3600
    report['sport_breakdown'] = {k: round(v, 1) for k, v in sorted(sport_hours.items(), key=lambda x: -x[1])}

    return report


def print_report(report):
    print("=" * 80)
    print("ANNUAL TRAINING ANALYSIS REPORT")
    print("=" * 80)

    # Athlete
    a = report.get('athlete', {})
    print(f"\nATHLETE PROFILE:")
    print(f"  Age: {a.get('age', '?')}  Weight: {a.get('weight_kg', '?')} kg")
    print(f"  FTP Start: {a.get('ftp_start', '?')}w  FTP Current: {a.get('ftp_current', '?')}w")
    print(f"  W/kg: {a.get('w_per_kg', '?')}")

    dr = report['date_range']
    print(f"\nDATE RANGE: {dr['start']} to {dr['end']} ({dr['total_rides']} rides)")

    # Season totals
    st = report['season_totals']
    print(f"\nSEASON TOTALS:")
    print(f"  Hours: {st['total_hours']}  Distance: {st['total_distance_km']} km  Ascent: {st['total_ascent_m']} m")
    print(f"  TSS: {st['total_tss']}  Calories: {st['total_calories']}  Work: {st['total_work_kj']} kJ")
    print(f"  Avg hours/week: {round(st['total_hours'] / max(1, len(report['weekly'])), 1)}")

    # Sport breakdown
    print(f"\nSPORT BREAKDOWN (hours):")
    for sport, hrs in report['sport_breakdown'].items():
        print(f"  {sport}: {hrs}h")

    # FTP Progression
    print(f"\nFTP PROGRESSION:")
    for month, ftp in report['ftp_progression'].items():
        print(f"  {month}: {ftp}w")

    # Power bests
    print(f"\nPOWER BESTS:")
    for dur, data in report['power_bests'].items():
        best_date, best_val = data['best']
        print(f"  Best {dur}: {best_val}w on {best_date}")

    # Zone distribution
    zd = report['zone_distribution']['percentages']
    print(f"\nPOWER ZONE DISTRIBUTION (% of total ride time):")
    zone_names = ['Z0/Coast', 'Z1/Active Recovery', 'Z2/Endurance', 'Z3/Tempo', 'Z4/Threshold', 'Z5/VO2max', 'Z6/Anaerobic']
    for i in range(7):
        print(f"  {zone_names[i]}: {zd.get(f'z{i}', 0)}%")

    # Planned vs Actual
    pva = report['planned_vs_actual']
    print(f"\nPLANNED vs ACTUAL:")
    print(f"  Planned workouts: {pva['planned']}")
    print(f"  Completed: {pva['completed']}  Missed: {pva['missed']}  Extra: {pva['extra']}")
    print(f"  Compliance: {pva['compliance_pct']}%")

    # Monthly summary
    print(f"\nMONTHLY SUMMARY:")
    print(f"  {'Month':<10} {'Rides':>5} {'Hours':>6} {'TSS':>6} {'Dist km':>8} {'Ascent':>7} {'AvgPow':>7} {'AvgHR':>6} {'Best20':>7}")
    for mk, m in report['monthly'].items():
        print(f"  {mk:<10} {m['rides']:>5} {m['duration_h']:>6.1f} {m['tss']:>6} {m['distance_km']:>8} {m['ascent_m']:>7} {m['avg_power']:>7} {m['avg_hr']:>6} {str(m['best_20min'] or '-'):>7}")

    # Weekly summary (abbreviated - show every week)
    print(f"\nWEEKLY SUMMARY:")
    print(f"  {'Week':<10} {'Rides':>5} {'Hours':>6} {'TSS':>6} {'Dist km':>8} {'Ascent':>7} {'IF':>5} {'Best20':>7} {'Sports'}")
    for wk, w in report['weekly'].items():
        sports = '/'.join(f"{k}:{v}" for k, v in w['sport_mix'].items())
        print(f"  {wk:<10} {w['rides']:>5} {w['duration_h']:>6.1f} {w['tss']:>6.0f} {w['distance_km']:>8.0f} {w['ascent_m']:>7} {w['avg_if']:>5.3f} {str(w['best_20min'] or '-'):>7} {sports}")

    # PMC highlights
    pmc = report['pmc']
    if pmc:
        peak_ctl = max(pmc, key=lambda x: x['ctl'])
        peak_atl = max(pmc, key=lambda x: x['atl'])
        low_tsb = min(pmc, key=lambda x: x['tsb'])
        high_tsb = max(pmc, key=lambda x: x['tsb'])
        print(f"\nPERFORMANCE MANAGEMENT CHART HIGHLIGHTS:")
        print(f"  Peak CTL (fitness): {peak_ctl['ctl']} on {peak_ctl['date']}")
        print(f"  Peak ATL (fatigue): {peak_atl['atl']} on {peak_atl['date']}")
        print(f"  Lowest TSB (form): {low_tsb['tsb']} on {low_tsb['date']}")
        print(f"  Highest TSB (form): {high_tsb['tsb']} on {high_tsb['date']}")
        # Current
        print(f"  Current CTL: {pmc[-1]['ctl']}  ATL: {pmc[-1]['atl']}  TSB: {pmc[-1]['tsb']}")

    # Training phases
    print(f"\nTRAINING PHASES (by week):")
    current_phase = None
    phase_start = None
    for wk, phase in report['training_phases']:
        if phase != current_phase:
            if current_phase:
                print(f"  {phase_start} to {wk}: {current_phase}")
            current_phase = phase
            phase_start = wk
    if current_phase:
        print(f"  {phase_start} to end: {current_phase}")

    print("\n" + "=" * 80)


# ─── MAIN ────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("Loading ride data...", file=sys.stderr)
    rides = load_all_rides()
    print(f"Loaded {len(rides)} rides.", file=sys.stderr)

    print("Loading planned workouts...", file=sys.stderr)
    planned = load_all_planned()
    print(f"Loaded {len(planned)} planned workouts.", file=sys.stderr)

    print("Analyzing...", file=sys.stderr)
    report = generate_report(rides, planned)

    # Print human-readable report
    print_report(report)

    # Also save full JSON report
    json_path = os.path.join(BASE_DIR, 'training_report.json')
    # PMC is big, save separately
    pmc_data = report.pop('pmc', [])
    with open(json_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    pmc_path = os.path.join(BASE_DIR, 'pmc_data.json')
    with open(pmc_path, 'w') as f:
        json.dump(pmc_data, f, indent=2)

    print(f"\nFull report saved to {json_path}", file=sys.stderr)
    print(f"PMC data saved to {pmc_path}", file=sys.stderr)
