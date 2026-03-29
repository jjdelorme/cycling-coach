"""PMC (Performance Management Chart) endpoints."""

from fastapi import APIRouter, Depends, Query
from typing import Optional

from server.auth import CurrentUser, require_read
from server.database import get_db
from server.models.schemas import PMCEntry
from server.queries import get_current_pmc_row

router = APIRouter(prefix="/api/pmc", tags=["pmc"])


@router.get("", response_model=list[PMCEntry])
def get_pmc(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    user: CurrentUser = Depends(require_read),
):
    query = "SELECT * FROM daily_metrics WHERE 1=1"
    params = []
    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
    query += " ORDER BY date"

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [PMCEntry(**dict(r)) for r in rows]


@router.get("/current", response_model=PMCEntry)
def get_current_pmc(user: CurrentUser = Depends(require_read)):
    with get_db() as conn:
        row = get_current_pmc_row(conn)
    if not row:
        return PMCEntry(date="unknown")
    return PMCEntry(**row)
