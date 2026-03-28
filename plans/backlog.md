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
