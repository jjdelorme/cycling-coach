"""Athlete settings endpoints."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from server.auth import CurrentUser, require_read, require_write
from server.database import get_all_athlete_settings, set_athlete_setting, ATHLETE_SETTINGS_DEFAULTS

router = APIRouter(prefix="/api/athlete", tags=["athlete"])


@router.get("/settings")
async def get_settings(user: CurrentUser = Depends(require_read)):
    """Get all athlete settings (LTHR, max HR, FTP, weight, etc.)."""
    return get_all_athlete_settings()


class AthleteSettingUpdate(BaseModel):
    key: str
    value: str


@router.put("/settings")
async def update_setting(req: AthleteSettingUpdate, user: CurrentUser = Depends(require_write)):
    """Update a single athlete setting."""
    valid_keys = set(ATHLETE_SETTINGS_DEFAULTS.keys())
    if req.key not in valid_keys:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=f"Invalid key. Must be one of: {', '.join(sorted(valid_keys))}",
        )
    set_athlete_setting(req.key, req.value)

    # Sync with intervals.icu if applicable
    if req.key == "ftp":
        try:
            from server.services.intervals_icu import update_ftp
            update_ftp(int(req.value))
        except (ValueError, Exception) as e:
            import logging
            logging.getLogger(__name__).warning("Failed to sync FTP to intervals.icu: %s", e)
    elif req.key == "weight_kg":
        try:
            from server.services.intervals_icu import update_weight
            update_weight(float(req.value))
        except (ValueError, Exception) as e:
            import logging
            logging.getLogger(__name__).warning("Failed to sync weight to intervals.icu: %s", e)

    return {"status": "updated", "key": req.key}
