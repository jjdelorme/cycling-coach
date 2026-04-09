#!/usr/bin/env python3
"""Generate synthetic recent rows for daily_metrics and rides in the seed file.

Appends synthetic rows for any missing dates in the last 14 days
(relative to today) so integration tests have "recent" data.

Usage:
    python tests/integration/seed/generate_recent.py [--today YYYY-MM-DD]
"""

import argparse
import gzip
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

SEED_FILE = Path(__file__).parent / "seed_data.json.gz"


def _next_id(rows: list, key: str = "id") -> int:
    if not rows:
        return 1
    return max(r.get(key, 0) for r in rows) + 1


def generate_recent(today: date, lookback_days: int = 14) -> None:
    random.seed(42)  # deterministic output

    with gzip.open(SEED_FILE, "rt") as f:
        data = json.load(f)

    existing_dm_dates = {r["date"] for r in data.get("daily_metrics", [])}
    existing_ride_dates = {r["date"] for r in data.get("rides", [])}

    # Determine current CTL/ATL from the last known daily_metrics entry
    dm_sorted = sorted(data.get("daily_metrics", []), key=lambda r: r["date"])
    if dm_sorted:
        last = dm_sorted[-1]
        ctl = last["ctl"]
        atl = last["atl"]
        ftp = last.get("ftp") or 261.0
        weight = last.get("weight") or 74.0
    else:
        ctl, atl, ftp, weight = 80.0, 85.0, 261.0, 74.0

    new_dm_rows = []
    new_ride_rows = []
    next_ride_id = _next_id(data.get("rides", []))

    # Walk forward from day after last known date up to today
    start = today - timedelta(days=lookback_days - 1)
    # But never generate before what already exists
    if dm_sorted:
        last_known = date.fromisoformat(dm_sorted[-1]["date"])
        start = max(start, last_known + timedelta(days=1))

    if start > today:
        print("Seed data is already up to date — no new rows needed.")
        return

    print(f"Generating synthetic rows from {start} to {today}...")

    current = start
    while current <= today:
        date_str = current.isoformat()

        # Decide whether to generate a ride on this day (70% chance, skip Mondays)
        add_ride = (current.weekday() != 0) and (random.random() < 0.70)

        if date_str not in existing_dm_dates:
            if add_ride:
                tss_today = round(random.uniform(60, 120), 1)
            else:
                tss_today = 0.0

            # EWA: CTL (42-day), ATL (7-day)
            ctl = round(ctl + (tss_today - ctl) / 42, 1)
            atl = round(atl + (tss_today - atl) / 7, 1)
            tsb = round(ctl - atl, 1)

            new_dm_rows.append({
                "date": date_str,
                "total_tss": tss_today,
                "ctl": ctl,
                "atl": atl,
                "tsb": tsb,
                "weight": weight,
                "ftp": ftp,
                "notes": None,
            })
        else:
            # Update running EWA from existing data even if we skip generating
            existing = next(r for r in data["daily_metrics"] if r["date"] == date_str)
            tss_today = existing.get("total_tss") or 0.0
            ctl = round(ctl + (tss_today - ctl) / 42, 1)
            atl = round(atl + (tss_today - atl) / 7, 1)
            add_ride = False  # don't double-add rides for existing dates

        if add_ride and date_str not in existing_ride_dates:
            tss = tss_today
            duration_s = round(random.uniform(3600, 7200), 0)
            avg_power = random.randint(175, 230)
            np_ = int(avg_power * random.uniform(1.02, 1.08))
            kcal = random.randint(800, 1500)

            ride = {
                "id": next_ride_id,
                "date": date_str,
                "filename": f"synthetic-{date_str}-{next_ride_id}.json",
                "sport": "cycling",
                "sub_sport": "generic",
                "duration_s": duration_s,
                "distance_m": round(duration_s * random.uniform(7.5, 10.0), 1),
                "avg_power": avg_power,
                "normalized_power": np_,
                "max_power": int(np_ * random.uniform(1.3, 1.6)),
                "avg_hr": random.randint(135, 155),
                "max_hr": random.randint(165, 178),
                "avg_cadence": random.randint(85, 95),
                "total_ascent": random.randint(200, 1200),
                "total_descent": random.randint(200, 1200),
                "total_calories": kcal,
                "tss": tss,
                "intensity_factor": round(np_ / ftp, 3),
                "ftp": int(ftp),
                "total_work_kj": round(avg_power * duration_s / 1000, 1),
                "training_effect": round(random.uniform(2.5, 4.5), 1),
                "variability_index": round(np_ / avg_power, 3),
                "best_1min_power": int(np_ * random.uniform(1.15, 1.25)),
                "best_5min_power": int(np_ * random.uniform(1.05, 1.12)),
                "best_20min_power": int(np_ * random.uniform(0.95, 1.02)),
                "best_60min_power": int(np_ * random.uniform(0.85, 0.92)),
                "weight": weight,
                "start_lat": round(44.166893 + random.uniform(-0.01, 0.01), 6),
                "start_lon": round(-71.164314 + random.uniform(-0.01, 0.01), 6),
                "post_ride_comments": None,
                "coach_comments": None,
                "title": f"Synthetic ride {date_str}",
                "start_time": f"{date_str}T10:00:00",
                # Synthetic rides have no per-second ride_records, so mark
                # has_power_data=False to prevent tools from querying records.
                "has_power_data": False,
                "data_status": "cleaned",
            }
            new_ride_rows.append(ride)
            next_ride_id += 1

        current += timedelta(days=1)

    if not new_dm_rows and not new_ride_rows:
        print("No new rows to add.")
        return

    data.setdefault("daily_metrics", []).extend(new_dm_rows)
    data.setdefault("rides", []).extend(new_ride_rows)

    with gzip.open(SEED_FILE, "wt") as f:
        json.dump(data, f, separators=(",", ":"))

    print(f"Added {len(new_dm_rows)} daily_metrics rows and {len(new_ride_rows)} ride rows.")
    print("Seed file updated.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--today",
        default=date.today().isoformat(),
        help="Reference date (YYYY-MM-DD). Defaults to system today.",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=14,
        help="Number of days to look back (default: 14).",
    )
    args = parser.parse_args()
    generate_recent(date.fromisoformat(args.today), args.lookback)
