# Backlog — Future Work

## ADK Tools vs REST API Architecture Refactor

**Status:** Deferred — out of scope for v1.3.1. Requires major rethinking.

**Context:** The ADK tools and REST API endpoints both independently query PostgreSQL via `get_db()`. There is meaningful code duplication (e.g., `get_ftp_history` has identical SQL in both paths). However, the two paths intentionally shape data differently for their consumers (LLM context vs frontend UI).

**Key questions to resolve:**
- Should there be a shared data-access / repository layer?
- How to handle the differing response shapes (coaching-optimized dicts vs Pydantic models)?
- Extract most-duplicated queries (`get_latest_ftp`, `get_ftp_history_rows`, `get_power_bests_rows`, `get_current_pmc_row`) into `server/queries.py`?
- Does a service layer add value or just indirection for this project's scale?

**Files involved:**
- `server/coaching/tools.py` — 7 read tools, direct DB queries
- `server/coaching/planning_tools.py` — 12 planning tools, direct DB queries
- `server/routers/` — REST endpoints, direct DB queries
- Shared services that already work well: `server/services/workout_generator.py`, `server/services/intervals_icu.py`

**Duplication inventory:**
| ADK Tool | REST Endpoint | Duplication Level |
|---|---|---|
| `get_pmc_metrics()` | `GET /api/pmc/current` | High |
| `get_recent_rides()` | `GET /api/rides` | Medium |
| `get_power_bests()` | `GET /api/analysis/power-curve` | High |
| `get_ftp_history()` | `GET /api/analysis/ftp-history` | Very High (identical SQL) |
| `get_training_summary()` | `GET /api/rides/summary/monthly` | Medium |
| `get_periodization_status()` | `GET /api/plan/macro` | Medium |
| `get_week_summary()` | `GET /api/plan/week/{date}` | High |

---

## In-App Notification System

**Status:** Deferred — no infrastructure exists yet.

**Context:** The weight resolver abstraction (`server/services/weight.py`) logs a warning when it falls back to the 75.0 kg default, meaning the athlete's W/kg, caloric balance, and coaching prescriptions may be materially wrong. This warning is only visible in server logs — the user has no awareness of it.

More broadly, there are likely other silent degraded-accuracy situations in the app (e.g., missing FTP, no recent weight sync, stale Withings token) that warrant surfacing to the user without being disruptive.

**Proposed design (when this is tackled):**
- A persistent `notifications` table: `(id, type, message, severity, created_at, dismissed_at)`
- A `GET /api/notifications` endpoint returning active (non-dismissed) alerts
- A `POST /api/notifications/{id}/dismiss` endpoint
- A small notification badge/panel in the UI (top nav or Settings page)
- Notifications written by backend logic at the point of detection (e.g., weight resolver, Withings token expiry, stale sync)

**Initial candidates for notifications:**
- Weight resolver fell back to default — "No weight data found. W/kg and caloric balance may be inaccurate. Connect Withings or set your weight in Settings."
- Withings token expired — "Withings connection needs to be re-authorized."
- No Intervals.icu sync in >7 days — "Ride data may be stale."
- FTP is 0 or unset — "FTP not configured. TSS calculations will be inaccurate."

**Related:** `plans/design-weight-architecture.md` — weight resolver default fallback section.
