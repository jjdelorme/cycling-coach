#!/usr/bin/env bash
# seed_svc_pgdb.sh — Initialize schema and load seed data into svc-pgdb.
#
# Usage:
#   ./scripts/seed_svc_pgdb.sh
#
# The script:
#   1. Runs init_db() to create the schema (idempotent).
#   2. Loads data from tests/integration/seed/seed_data.json.gz.
#   3. Generates synthetic daily_metrics/rides rows for the last 7 days if missing.
#   4. Prints a summary of row counts per table.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Activate the Python venv
# shellcheck disable=SC1091
source "$REPO_ROOT/venv/bin/activate"

SVC_DB_URL="postgresql://postgres:testpwd@svc-pgdb/postgres"

echo "==> Verifying connection to svc-pgdb..."
python3 -c "
import psycopg2, os
url = '$SVC_DB_URL'
conn = psycopg2.connect(url)
cur = conn.cursor()
cur.execute('SELECT version()')
print('   Connected:', cur.fetchone()[0][:60])
conn.close()
"

echo "==> Running init_db() to create/update schema..."
CYCLING_COACH_DATABASE_URL="$SVC_DB_URL" python3 -c "
import os
os.environ['CYCLING_COACH_DATABASE_URL'] = '$SVC_DB_URL'
from server.database import init_db
init_db()
print('   Schema ready.')
"

echo "==> Loading seed data from tests/integration/seed/seed_data.json.gz..."
CYCLING_COACH_DATABASE_URL="$SVC_DB_URL" python3 -c "
import gzip, json, os, sys
from pathlib import Path

os.environ['CYCLING_COACH_DATABASE_URL'] = '$SVC_DB_URL'
from server.database import get_db

SEED_FILE = Path('tests/integration/seed/seed_data.json.gz')

TABLE_ORDER = [
    'rides',
    'ride_records',
    'ride_laps',
    'power_bests',
    'daily_metrics',
    'periodization_phases',
    'planned_workouts',
    'athlete_settings',
    'coach_settings',
    'workout_templates',
]

with gzip.open(SEED_FILE, 'rt') as f:
    data = json.load(f)

loaded = {}
skipped = {}

with get_db() as conn:
    for table in TABLE_ORDER:
        rows = data.get(table, [])
        if not rows:
            loaded[table] = 0
            continue
        cols = list(rows[0].keys())
        placeholders = ', '.join(['%s'] * len(cols))
        col_names = ', '.join(cols)
        sql = f'INSERT INTO {table} ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'
        inserted = 0
        for row in rows:
            cur = conn.execute(sql, tuple(row.get(c) for c in cols))
            inserted += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        loaded[table] = inserted

    # Reset sequences so new inserts don't collide with seed IDs
    for table in ['rides', 'ride_records', 'ride_laps', 'power_bests',
                  'periodization_phases', 'planned_workouts', 'athlete_settings',
                  'workout_templates']:
        conn.execute(f'''
            SELECT setval(pg_get_serial_sequence('{table}', 'id'),
                          COALESCE((SELECT MAX(id) FROM {table}), 1))
        ''')

print()
print('Seed load results:')
for table in TABLE_ORDER:
    print(f'  {table}: {loaded.get(table, 0)} rows inserted')
"

echo "==> Generating synthetic recent data directly into DB (no file writes)..."
CYCLING_COACH_DATABASE_URL="$SVC_DB_URL" python3 - <<'PYEOF'
import gzip, json, os, random
from datetime import date, timedelta
from pathlib import Path
from server.database import get_db

SEED_FILE = Path('tests/integration/seed/seed_data.json.gz')
TODAY = date.today()
LOOKBACK = 14
random.seed(42)

with gzip.open(SEED_FILE, 'rt') as f:
    seed_data = json.load(f)

dm_sorted = sorted(seed_data.get('daily_metrics', []), key=lambda r: r['date'])
existing_dm_dates = {r['date'] for r in dm_sorted}
existing_ride_dates = {r['date'] for r in seed_data.get('rides', [])}

if dm_sorted:
    last = dm_sorted[-1]
    ctl, atl = last['ctl'], last['atl']
    ftp = last.get('ftp') or 261.0
    weight = last.get('weight') or 74.0
    last_known = date.fromisoformat(last['date'])
else:
    ctl, atl, ftp, weight = 80.0, 85.0, 261.0, 74.0
    last_known = TODAY - timedelta(days=LOOKBACK)

start = max(TODAY - timedelta(days=LOOKBACK - 1), last_known + timedelta(days=1))

if start > TODAY:
    print('   Recent data is already up to date — no synthetic rows needed.')
else:
    print(f'   Generating synthetic rows from {start} to {TODAY}...')
    new_dm, new_rides = [], []
    with get_db() as conn:
        # Find next ride id from the live DB
        row = conn.execute('SELECT COALESCE(MAX(id), 0) AS max_id FROM rides').fetchone()
        next_ride_id = row['max_id'] + 1

        current = start
        while current <= TODAY:
            date_str = current.isoformat()
            add_ride = (current.weekday() != 0) and (random.random() < 0.70)

            if date_str not in existing_dm_dates:
                tss_today = round(random.uniform(60, 120), 1) if add_ride else 0.0
                ctl = round(ctl + (tss_today - ctl) / 42, 1)
                atl = round(atl + (tss_today - atl) / 7, 1)
                tsb = round(ctl - atl, 1)
                conn.execute(
                    'INSERT INTO daily_metrics (date, total_tss, ctl, atl, tsb, weight, ftp, notes) '
                    'VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING',
                    (date_str, tss_today, ctl, atl, tsb, weight, ftp, None)
                )
                new_dm.append(date_str)
            else:
                existing = next(r for r in dm_sorted if r['date'] == date_str)
                tss_today = existing.get('total_tss') or 0.0
                ctl = round(ctl + (tss_today - ctl) / 42, 1)
                atl = round(atl + (tss_today - atl) / 7, 1)
                add_ride = False

            if add_ride and date_str not in existing_ride_dates:
                tss = tss_today
                duration_s = round(random.uniform(3600, 7200), 0)
                avg_power = random.randint(175, 230)
                np_ = int(avg_power * random.uniform(1.02, 1.08))
                kcal = random.randint(800, 1500)
                conn.execute(
                    'INSERT INTO rides (date, filename, sport, sub_sport, duration_s, distance_m, '
                    'avg_power, normalized_power, max_power, avg_hr, max_hr, avg_cadence, '
                    'total_ascent, total_descent, total_calories, tss, intensity_factor, ftp, '
                    'total_work_kj, training_effect, variability_index, best_1min_power, '
                    'best_5min_power, best_20min_power, best_60min_power, weight, '
                    'post_ride_comments, coach_comments, title, start_time, has_power_data, data_status) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) '
                    'ON CONFLICT DO NOTHING',
                    (date_str, f'synthetic-{date_str}-{next_ride_id}.json', 'cycling', 'generic',
                     duration_s, round(duration_s * random.uniform(7.5, 10.0), 1),
                     avg_power, np_, int(np_ * random.uniform(1.3, 1.6)),
                     random.randint(135, 155), random.randint(165, 178), random.randint(85, 95),
                     random.randint(200, 1200), random.randint(200, 1200), kcal,
                     tss, round(np_ / ftp, 3), int(ftp),
                     round(avg_power * duration_s / 1000, 1), round(random.uniform(2.5, 4.5), 1),
                     round(np_ / avg_power, 3), int(np_ * random.uniform(1.15, 1.25)),
                     int(np_ * random.uniform(1.05, 1.12)), int(np_ * random.uniform(0.95, 1.02)),
                     int(np_ * random.uniform(0.85, 0.92)), weight,
                     None, None, f'Synthetic ride {date_str}', f'{date_str}T10:00:00',
                     False, 'cleaned')
                )
                new_rides.append(date_str)
                next_ride_id += 1

            current += timedelta(days=1)

        conn.execute("""
            SELECT setval(pg_get_serial_sequence('rides', 'id'),
                          COALESCE((SELECT MAX(id) FROM rides), 1))
        """)

    print(f'   Inserted {len(new_dm)} daily_metrics rows, {len(new_rides)} ride rows.')
PYEOF

echo ""
echo "==> Row counts in svc-pgdb:"
CYCLING_COACH_DATABASE_URL="$SVC_DB_URL" python3 -c "
import os
os.environ['CYCLING_COACH_DATABASE_URL'] = '$SVC_DB_URL'
from server.database import get_db

tables = [
    'rides', 'ride_records', 'ride_laps', 'power_bests',
    'daily_metrics', 'periodization_phases', 'planned_workouts',
    'athlete_settings', 'coach_settings', 'workout_templates',
    'sync_runs', 'users',
]
with get_db() as conn:
    for t in tables:
        try:
            row = conn.execute(f'SELECT COUNT(*) AS cnt FROM {t}').fetchone()
            print(f'  {t}: {row[\"cnt\"]} rows')
        except Exception as e:
            print(f'  {t}: ERROR - {e}')
"

echo ""
echo "==> svc-pgdb seeding complete."
