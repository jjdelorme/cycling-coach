# Feature Implementation Plan: Withings Body Weight Integration

## Analysis & Context

*   **Objective:** Integrate with the Withings Health API (OAuth 2.0) to pull daily body weight measurements from a user's Withings Body+ scale and store them in the database, surfacing them in the PMC pipeline and as a new Weight Trend chart on the Analysis page.
*   **Requested By:** User (Jason)
*   **Status:** Ready for Engineer

## High-Level Intent

### Key Existing Infrastructure to Reuse
- `daily_metrics.weight REAL` — already in DB schema (line 130 of `server/database.py`), already shown on Dashboard metric card
- `coach_settings` key-value table — stores intervals.icu tokens; Withings tokens go here too (via `get_setting` / `set_setting`)
- `server/services/intervals_icu.py` — the model for a new `server/services/withings.py`
- `server/routers/sync.py` — the model for `server/routers/withings.py`
- `server/ingest.py:compute_daily_pmc()` — weight priority lookup pattern (lines 451–456)
- `frontend/src/pages/Settings.tsx` System tab — add Withings card alongside intervals.icu (line 578+)
- `frontend/src/pages/Analysis.tsx` — add `'weight'` tab using `usePMC()` data (weight already in PMC payload)
- `usePMC()` hook in `frontend/src/hooks/useApi.ts` (line 61–63) — PMCEntry already has `weight?: number`

### Withings API Details
- **OAuth 2.0 Auth URL**: `https://account.withings.com/oauth2_user/authorize2`
- **Token endpoint**: `POST https://wbsapi.withings.net/v2/oauth2` (action=requesttoken / action=refreshaccesstoken)
- **Scope**: `user.metrics`
- **Measurement endpoint**: `POST https://wbsapi.withings.net/measure` (action=getmeas, meastype=1)
  - meastype=1 = weight (kg); value decoded as `value × 10^unit` (unit is a negative integer, e.g. value=7500, unit=-2 → 75.00 kg)
  - startdate/enddate = Unix timestamps
- **Token refresh**: Refresh tokens are long-lived; access tokens expire in ~3 hours (check `expires_in` field)
- **Token response shape**: `{ "status": 0, "body": { "access_token": "...", "refresh_token": "...", "expires_in": 10800, "userid": "...", ... } }`
- **Measurement response shape**: `{ "status": 0, "body": { "measuregrps": [ { "date": 1234567890, "measures": [ { "value": 7500, "type": 1, "unit": -2 } ] } ] } }`

### Proposed New DB Table
```sql
CREATE TABLE IF NOT EXISTS body_measurements (
    id SERIAL PRIMARY KEY,
    date TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'withings',
    weight_kg REAL,
    fat_percent REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, source)
);
```

### Weight Priority in PMC After This Feature (compute_daily_pmc)
1. Withings measurement for the date (highest — from scale, most accurate)
2. Most recent ride weight on or before this date (Garmin device weight)
3. athlete_settings weight_kg active on this date (manual entry)
4. Default 0

### New Files
- `server/services/withings.py`
- `server/routers/withings.py`
- `tests/unit/test_withings.py`
- `tests/integration/test_withings_integration.py`

### Modified Files
- `server/database.py` — body_measurements table DDL in `_SCHEMA`, Withings keys in `SETTINGS_DEFAULTS`, migration in `init_db()`
- `server/config.py` — WITHINGS_CLIENT_ID, WITHINGS_CLIENT_SECRET, WITHINGS_REDIRECT_URI
- `server/ingest.py` — updated `compute_daily_pmc()` weight priority
- `server/main.py` — register withings router
- `frontend/src/lib/api.ts` — 5 Withings API helpers
- `frontend/src/hooks/useApi.ts` — `useWithingsStatus` hook
- `frontend/src/pages/Settings.tsx` — Withings card in System tab
- `frontend/src/pages/Analysis.tsx` — weight trend tab
- `frontend/src/types/api.ts` — `WithingsStatus` interface
- `plans/00_MASTER_ROADMAP.md` — register Campaign 11

### Sync Design
- **Manual-only**: "Sync Weight" button in Settings → POST /api/withings/sync
- No background/scheduled sync (matches intervals.icu pattern)
- Sync fetches last 90 days of Withings measurements, upserts to body_measurements, triggers PMC recompute

### OAuth Flow
1. User clicks "Connect Withings" in Settings → GET /api/withings/auth-url
2. Frontend opens URL in new tab
3. User authorizes on Withings → redirected to /api/withings/callback?code=...&state=...
4. Backend validates state, exchanges code for tokens, stores in coach_settings, returns HTML redirect to /settings
5. CSRF protection: `withings_oauth_state` stored in coach_settings, validated on callback, cleared after use

### Environment Variables (new)
```
WITHINGS_CLIENT_ID=...
WITHINGS_CLIENT_SECRET=...
WITHINGS_REDIRECT_URI=http://localhost:8000/api/withings/callback
```

---

## Micro-Step Checklist

- [x] Phase 1: Database & Config Foundation
  - [x] Step 1.A: Add `body_measurements` table DDL to `_SCHEMA` in `server/database.py`
  - [x] Step 1.B: Add Withings token keys to `SETTINGS_DEFAULTS` in `server/database.py`
  - [x] Step 1.C: Add Withings migration to `init_db()` in `server/database.py`
  - [x] Step 1.D: Add Withings env vars to `server/config.py`

- [x] Phase 2: Withings Service Layer (TDD)
  - [x] Step 2.A: Write unit tests for `is_configured` / `is_connected` in `tests/unit/test_withings.py`
  - [x] Step 2.B: Implement `is_configured` / `is_connected` in `server/services/withings.py`
  - [x] Step 2.C: Write unit tests for `get_auth_url`
  - [x] Step 2.D: Implement `get_auth_url` (generate state, store in coach_settings, build URL)
  - [x] Step 2.E: Write unit tests for `exchange_code`
  - [x] Step 2.F: Implement `exchange_code` (POST to Withings, store tokens in coach_settings)
  - [x] Step 2.G: Write unit tests for `_get_valid_access_token` / `_refresh_tokens`
  - [x] Step 2.H: Implement `_get_valid_access_token` + `_refresh_tokens`
  - [x] Step 2.I: Write unit tests for `fetch_weight_measurements` (mock httpx.post)
  - [x] Step 2.J: Implement `fetch_weight_measurements` (value×10^unit decoding)
  - [x] Step 2.K: Write unit tests for `store_measurements`
  - [x] Step 2.L: Implement `store_measurements` (upsert to body_measurements)
  - [x] Step 2.M: Write unit tests for `sync_weight` / `get_status` / `disconnect`
  - [x] Step 2.N: Implement `sync_weight` / `get_status` / `disconnect`

- [x] Phase 3: Withings Router (TDD)
  - [x] Step 3.A: Write integration tests for GET /api/withings/status (in test_withings_integration.py)
  - [x] Step 3.B: Implement GET /api/withings/status
  - [x] Step 3.C: Implement GET /api/withings/auth-url (require_write)
  - [x] Step 3.D: Implement GET /api/withings/callback (no auth — OAuth redirect target)
  - [x] Step 3.E: Write integration tests for POST /api/withings/sync
  - [x] Step 3.F: Implement POST /api/withings/sync (require_write)
  - [x] Step 3.G: Implement DELETE /api/withings/disconnect (require_write)
  - [x] Step 3.H: Register router in `server/main.py`

- [x] Phase 4: PMC Weight Priority Update (TDD)
  - [x] Step 4.A: Write integration test for Withings weight priority in PMC
  - [x] Step 4.B: Update `compute_daily_pmc()` in `server/ingest.py`

- [x] Phase 5: Frontend — Settings Withings Card
  - [x] Step 5.A: Add `WithingsStatus` interface to `frontend/src/types/api.ts`
  - [x] Step 5.B: Add 5 API helpers to `frontend/src/lib/api.ts`
  - [x] Step 5.C: Add `useWithingsStatus` hook to `frontend/src/hooks/useApi.ts`
  - [x] Step 5.D: Add Withings card UI to Settings System tab in `frontend/src/pages/Settings.tsx`

- [x] Phase 6: Frontend — Analysis Weight Tab
  - [x] Step 6.A: Add `'weight'` to `Tab` type in `frontend/src/pages/Analysis.tsx`
  - [x] Step 6.B: Add weight tab entry to `TABS` array
  - [x] Step 6.C: Implement `WeightChart` component using `usePMC()` data
  - [x] Step 6.D: Render `WeightChart` in tab content area

- [x] Phase 7: Master Roadmap Update
  - [x] Step 7.A: Add Campaign 11 entry to `plans/00_MASTER_ROADMAP.md` (already present)

---

## Step-by-Step Implementation Details

### Phase 1: Database & Config Foundation

#### Step 1.A — Add `body_measurements` table to `_SCHEMA` in `server/database.py`

**File:** `server/database.py`  
**Where:** Inside the `_SCHEMA` string (line 27), after the `users` table block (currently ends near line 242) and before the `ALTER TABLE` migration statements.

Add this block immediately before the `ALTER TABLE rides ADD COLUMN IF NOT EXISTS has_power_data` line (currently around line 250):

```python
CREATE TABLE IF NOT EXISTS body_measurements (
    id SERIAL PRIMARY KEY,
    date TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'withings',
    weight_kg REAL,
    fat_percent REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, source)
);

CREATE INDEX IF NOT EXISTS idx_body_measurements_date ON body_measurements(date);
CREATE INDEX IF NOT EXISTS idx_body_measurements_source ON body_measurements(source);
```

#### Step 1.B — Add Withings token keys to `SETTINGS_DEFAULTS`

**File:** `server/database.py`  
**Where:** `SETTINGS_DEFAULTS` dict (lines 385–397). Add five new keys at the end of the dict:

```python
SETTINGS_DEFAULTS = {
    # ... existing keys unchanged ...
    "gemini_api_key": "",
    # NEW Withings keys:
    "withings_access_token": "",
    "withings_refresh_token": "",
    "withings_token_expiry": "",   # Unix timestamp string, e.g. "1713600000"
    "withings_user_id": "",        # Withings userid string
    "withings_oauth_state": "",    # Ephemeral CSRF state, cleared after use
}
```

#### Step 1.C — Add Withings migration to `init_db()`

**File:** `server/database.py`  
**Where:** `init_db()` function (line 490). The `body_measurements` table is already in `_SCHEMA` via Step 1.A, so `init_db()` will create it on fresh installs. For *existing* databases that already ran without this table, add a migration block. Add after the existing `v152_migrations` block (after line 529, before `conn.close()`):

```python
    # Migration: body_measurements table for Withings integration
    withings_migrations = [
        """CREATE TABLE IF NOT EXISTS body_measurements (
            id SERIAL PRIMARY KEY,
            date TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'withings',
            weight_kg REAL,
            fat_percent REAL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, source)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_body_measurements_date ON body_measurements(date)",
        "CREATE INDEX IF NOT EXISTS idx_body_measurements_source ON body_measurements(source)",
    ]
    for stmt in withings_migrations:
        try:
            cur = conn.cursor()
            cur.execute(stmt)
            conn.commit()
            cur.close()
        except Exception as e:
            logger.warning("migration_skipped", reason=str(e), stmt=stmt[:80])
            conn.rollback()
```

#### Step 1.D — Add Withings env vars to `server/config.py`

**File:** `server/config.py`  
**Where:** After the last existing line (line 24, `INTERVALS_ICU_DISABLED = ...`). Add:

```python
# Withings integration
WITHINGS_CLIENT_ID = os.getenv("WITHINGS_CLIENT_ID", "")
WITHINGS_CLIENT_SECRET = os.getenv("WITHINGS_CLIENT_SECRET", "")
WITHINGS_REDIRECT_URI = os.getenv("WITHINGS_REDIRECT_URI", "http://localhost:8000/api/withings/callback")
```

---

### Phase 2: Withings Service Layer

#### Step 2.A — Write unit tests for `is_configured` / `is_connected`

**File:** `tests/unit/test_withings.py` (new file)

```python
"""Unit tests for Withings service layer."""

import pytest
from unittest.mock import patch, MagicMock
import time


@patch("server.services.withings.WITHINGS_CLIENT_ID", "")
@patch("server.services.withings.WITHINGS_CLIENT_SECRET", "")
def test_is_configured_false_when_no_credentials():
    from server.services.withings import is_configured
    assert is_configured() is False


@patch("server.services.withings.WITHINGS_CLIENT_ID", "client_id")
@patch("server.services.withings.WITHINGS_CLIENT_SECRET", "client_secret")
def test_is_configured_true_when_credentials_set():
    from server.services.withings import is_configured
    assert is_configured() is True


@patch("server.services.withings.get_setting")
def test_is_connected_false_when_no_token(mock_get_setting):
    mock_get_setting.return_value = ""
    from server.services.withings import is_connected
    assert is_connected() is False


@patch("server.services.withings.get_setting")
def test_is_connected_true_when_token_exists(mock_get_setting):
    mock_get_setting.return_value = "some_access_token"
    from server.services.withings import is_connected
    assert is_connected() is True
```

#### Step 2.B — Implement `is_configured` / `is_connected` in `server/services/withings.py`

**File:** `server/services/withings.py` (new file)

```python
"""Withings Health API integration for syncing body weight measurements."""

import secrets
import time
import httpx
from datetime import datetime, timezone

from server.config import WITHINGS_CLIENT_ID, WITHINGS_CLIENT_SECRET, WITHINGS_REDIRECT_URI
from server.database import get_setting, set_setting, get_db
from server.logging_config import get_logger

logger = get_logger(__name__)

WITHINGS_AUTH_URL = "https://account.withings.com/oauth2_user/authorize2"
WITHINGS_TOKEN_URL = "https://wbsapi.withings.net/v2/oauth2"
WITHINGS_MEASURE_URL = "https://wbsapi.withings.net/measure"


def is_configured() -> bool:
    """Return True if Withings OAuth app credentials are set in environment."""
    return bool(WITHINGS_CLIENT_ID and WITHINGS_CLIENT_SECRET)


def is_connected() -> bool:
    """Return True if the user has authorized Withings (access token stored)."""
    return bool(get_setting("withings_access_token"))
```

#### Step 2.C — Write unit tests for `get_auth_url`

Add to `tests/unit/test_withings.py`:

```python
@patch("server.services.withings.WITHINGS_CLIENT_ID", "my_client_id")
@patch("server.services.withings.WITHINGS_REDIRECT_URI", "http://localhost:8000/api/withings/callback")
@patch("server.services.withings.set_setting")
@patch("server.services.withings.secrets.token_urlsafe", return_value="test_state_abc")
def test_get_auth_url_returns_correct_url(mock_token, mock_set_setting):
    from server.services.withings import get_auth_url
    url = get_auth_url()
    assert "account.withings.com/oauth2_user/authorize2" in url
    assert "client_id=my_client_id" in url
    assert "scope=user.metrics" in url
    assert "state=test_state_abc" in url
    assert "response_type=code" in url
    assert "redirect_uri=http%3A" in url or "redirect_uri=http://localhost" in url
    # Verify state was stored
    mock_set_setting.assert_called_once_with("withings_oauth_state", "test_state_abc")
```

#### Step 2.D — Implement `get_auth_url`

Add to `server/services/withings.py`:

```python
def get_auth_url() -> str:
    """Generate Withings OAuth authorization URL and store CSRF state."""
    state = secrets.token_urlsafe(32)
    set_setting("withings_oauth_state", state)

    from urllib.parse import urlencode
    params = {
        "response_type": "code",
        "client_id": WITHINGS_CLIENT_ID,
        "scope": "user.metrics",
        "redirect_uri": WITHINGS_REDIRECT_URI,
        "state": state,
    }
    return f"{WITHINGS_AUTH_URL}?{urlencode(params)}"
```

#### Step 2.E — Write unit tests for `exchange_code`

Add to `tests/unit/test_withings.py`:

```python
@patch("server.services.withings.WITHINGS_CLIENT_ID", "client_id")
@patch("server.services.withings.WITHINGS_CLIENT_SECRET", "client_secret")
@patch("server.services.withings.WITHINGS_REDIRECT_URI", "http://localhost:8000/api/withings/callback")
@patch("server.services.withings.get_setting", return_value="expected_state")
@patch("server.services.withings.set_setting")
@patch("httpx.post")
def test_exchange_code_success(mock_post, mock_set, mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": 0,
        "body": {
            "access_token": "access_abc",
            "refresh_token": "refresh_xyz",
            "expires_in": 10800,
            "userid": "12345",
        }
    }
    mock_post.return_value = mock_response

    from server.services.withings import exchange_code
    result = exchange_code(code="auth_code_123", state="expected_state")
    assert result["status"] == "success"


@patch("server.services.withings.get_setting", return_value="correct_state")
def test_exchange_code_rejects_bad_state(mock_get):
    from server.services.withings import exchange_code
    result = exchange_code(code="auth_code_123", state="WRONG_STATE")
    assert result["status"] == "error"
    assert "state" in result["message"].lower()
```

#### Step 2.F — Implement `exchange_code` + token storage

Add to `server/services/withings.py`:

```python
def exchange_code(code: str, state: str) -> dict:
    """Exchange OAuth authorization code for tokens. Validates CSRF state."""
    stored_state = get_setting("withings_oauth_state")
    if not stored_state or stored_state != state:
        logger.warning("withings_oauth_state_mismatch", received=state)
        return {"status": "error", "message": "Invalid OAuth state — possible CSRF. Please try connecting again."}

    payload = {
        "action": "requesttoken",
        "grant_type": "authorization_code",
        "client_id": WITHINGS_CLIENT_ID,
        "client_secret": WITHINGS_CLIENT_SECRET,
        "code": code,
        "redirect_uri": WITHINGS_REDIRECT_URI,
    }

    resp = httpx.post(WITHINGS_TOKEN_URL, data=payload, timeout=15.0)
    if resp.status_code != 200:
        logger.error("withings_token_exchange_failed", status=resp.status_code)
        return {"status": "error", "message": f"Withings API error: {resp.status_code}"}

    data = resp.json()
    if data.get("status") != 0:
        logger.error("withings_token_exchange_error", withings_status=data.get("status"))
        return {"status": "error", "message": f"Withings returned error status {data.get('status')}"}

    body = data["body"]
    expiry = int(time.time()) + int(body.get("expires_in", 10800))

    set_setting("withings_access_token", body["access_token"])
    set_setting("withings_refresh_token", body["refresh_token"])
    set_setting("withings_token_expiry", str(expiry))
    set_setting("withings_user_id", str(body.get("userid", "")))
    set_setting("withings_oauth_state", "")  # Clear CSRF state

    logger.info("withings_connected", user_id=body.get("userid"))
    return {"status": "success"}
```

#### Step 2.G — Write unit tests for `_get_valid_access_token` / `_refresh_tokens`

Add to `tests/unit/test_withings.py`:

```python
@patch("server.services.withings.get_setting")
def test_get_valid_access_token_returns_valid_token(mock_get_setting):
    future_expiry = str(int(time.time()) + 7200)
    def side_effect(key):
        return {"withings_access_token": "valid_token", "withings_token_expiry": future_expiry}.get(key, "")
    mock_get_setting.side_effect = side_effect
    from server.services.withings import _get_valid_access_token
    token = _get_valid_access_token()
    assert token == "valid_token"


@patch("server.services.withings.WITHINGS_CLIENT_ID", "client_id")
@patch("server.services.withings.WITHINGS_CLIENT_SECRET", "client_secret")
@patch("server.services.withings.set_setting")
@patch("server.services.withings.get_setting")
@patch("httpx.post")
def test_get_valid_access_token_refreshes_expired_token(mock_post, mock_get, mock_set):
    past_expiry = str(int(time.time()) - 100)  # Expired
    def side_effect(key):
        return {
            "withings_access_token": "old_token",
            "withings_token_expiry": past_expiry,
            "withings_refresh_token": "refresh_token_abc",
        }.get(key, "")
    mock_get.side_effect = side_effect

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": 0,
        "body": {"access_token": "new_token", "refresh_token": "new_refresh", "expires_in": 10800}
    }
    mock_post.return_value = mock_response

    from server.services.withings import _get_valid_access_token
    token = _get_valid_access_token()
    assert token == "new_token"
```

#### Step 2.H — Implement `_get_valid_access_token` + `_refresh_tokens`

Add to `server/services/withings.py`:

```python
def _refresh_tokens(refresh_token: str) -> str | None:
    """Refresh Withings access token. Returns new access token or None on failure."""
    payload = {
        "action": "refreshaccesstoken",
        "grant_type": "refresh_token",
        "client_id": WITHINGS_CLIENT_ID,
        "client_secret": WITHINGS_CLIENT_SECRET,
        "refresh_token": refresh_token,
    }
    resp = httpx.post(WITHINGS_TOKEN_URL, data=payload, timeout=15.0)
    if resp.status_code != 200:
        logger.error("withings_refresh_failed", status=resp.status_code)
        return None

    data = resp.json()
    if data.get("status") != 0:
        logger.error("withings_refresh_error", withings_status=data.get("status"))
        return None

    body = data["body"]
    expiry = int(time.time()) + int(body.get("expires_in", 10800))
    set_setting("withings_access_token", body["access_token"])
    set_setting("withings_refresh_token", body["refresh_token"])
    set_setting("withings_token_expiry", str(expiry))
    logger.info("withings_tokens_refreshed")
    return body["access_token"]


def _get_valid_access_token() -> str | None:
    """Return a valid Withings access token, refreshing if expired."""
    access_token = get_setting("withings_access_token")
    if not access_token:
        return None

    expiry_str = get_setting("withings_token_expiry")
    try:
        expiry = int(expiry_str) if expiry_str else 0
    except ValueError:
        expiry = 0

    # Refresh if token expires within 5 minutes
    if time.time() >= expiry - 300:
        refresh_token = get_setting("withings_refresh_token")
        if not refresh_token:
            return None
        return _refresh_tokens(refresh_token)

    return access_token
```

#### Step 2.I — Write unit tests for `fetch_weight_measurements`

Add to `tests/unit/test_withings.py`:

```python
@patch("server.services.withings._get_valid_access_token", return_value="valid_token")
@patch("httpx.post")
def test_fetch_weight_measurements_decodes_values(mock_post, mock_token):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": 0,
        "body": {
            "measuregrps": [
                {
                    "date": 1713600000,
                    "measures": [
                        {"value": 7500, "type": 1, "unit": -2},   # 75.00 kg
                    ]
                },
                {
                    "date": 1713513600,
                    "measures": [
                        {"value": 74800, "type": 1, "unit": -3},  # 74.800 kg
                    ]
                },
            ]
        }
    }
    mock_post.return_value = mock_response

    from server.services.withings import fetch_weight_measurements
    results = fetch_weight_measurements(days=90)
    assert len(results) == 2
    assert results[0]["weight_kg"] == pytest.approx(75.00)
    assert results[1]["weight_kg"] == pytest.approx(74.800)
    assert "date" in results[0]


@patch("server.services.withings._get_valid_access_token", return_value=None)
def test_fetch_weight_measurements_raises_when_not_connected(mock_token):
    from server.services.withings import fetch_weight_measurements
    with pytest.raises(RuntimeError, match="not connected"):
        fetch_weight_measurements()
```

#### Step 2.J — Implement `fetch_weight_measurements`

Add to `server/services/withings.py`:

```python
def fetch_weight_measurements(days: int = 90) -> list[dict]:
    """Fetch weight measurements from Withings API.

    Returns list of dicts: [{"date": "YYYY-MM-DD", "weight_kg": float}, ...]
    Decodes Withings value×10^unit encoding.
    """
    access_token = _get_valid_access_token()
    if not access_token:
        raise RuntimeError("Withings not connected — no valid access token")

    end_ts = int(time.time())
    start_ts = end_ts - (days * 86400)

    payload = {
        "action": "getmeas",
        "meastype": 1,   # Weight in kg
        "category": 1,   # Real measurements (not objectives)
        "startdate": start_ts,
        "enddate": end_ts,
    }
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = httpx.post(WITHINGS_MEASURE_URL, data=payload, headers=headers, timeout=15.0)

    if resp.status_code != 200:
        logger.error("withings_fetch_failed", status=resp.status_code)
        raise RuntimeError(f"Withings API error {resp.status_code}")

    data = resp.json()
    if data.get("status") != 0:
        logger.error("withings_fetch_error", withings_status=data.get("status"))
        raise RuntimeError(f"Withings returned error status {data.get('status')}")

    results = []
    for grp in data.get("body", {}).get("measuregrps", []):
        grp_date = datetime.fromtimestamp(grp["date"], tz=timezone.utc).strftime("%Y-%m-%d")
        for measure in grp.get("measures", []):
            if measure.get("type") == 1:  # Weight
                raw_value = measure["value"]
                unit = measure["unit"]
                weight_kg = raw_value * (10 ** unit)
                results.append({"date": grp_date, "weight_kg": round(weight_kg, 3)})
                break  # One weight per measuregrp

    # Deduplicate by date, keep latest reading per day
    by_date: dict[str, float] = {}
    for r in results:
        by_date[r["date"]] = r["weight_kg"]

    logger.info("withings_measurements_fetched", count=len(by_date))
    return [{"date": d, "weight_kg": w} for d, w in sorted(by_date.items())]
```

#### Step 2.K — Write unit tests for `store_measurements`

Add to `tests/unit/test_withings.py` (note: store_measurements touches DB, so we mock `get_db`):

```python
@patch("server.services.withings.get_db")
def test_store_measurements_upserts_correctly(mock_get_db):
    mock_conn = MagicMock()
    mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

    measurements = [
        {"date": "2026-04-01", "weight_kg": 75.0},
        {"date": "2026-04-02", "weight_kg": 74.8},
    ]

    from server.services.withings import store_measurements
    count = store_measurements(measurements)
    assert count == 2
    assert mock_conn.execute.called
```

#### Step 2.L — Implement `store_measurements`

Add to `server/services/withings.py`:

```python
def store_measurements(measurements: list[dict]) -> int:
    """Upsert weight measurements into body_measurements table.

    Args:
        measurements: List of dicts with "date" and "weight_kg" keys.

    Returns:
        Number of measurements stored.
    """
    if not measurements:
        return 0

    with get_db() as conn:
        for m in measurements:
            conn.execute(
                """INSERT INTO body_measurements (date, source, weight_kg)
                   VALUES (%s, 'withings', %s)
                   ON CONFLICT (date, source) DO UPDATE SET weight_kg = EXCLUDED.weight_kg""",
                (m["date"], m["weight_kg"]),
            )

    logger.info("withings_measurements_stored", count=len(measurements))
    return len(measurements)
```

#### Step 2.M — Write unit tests for `sync_weight` / `get_status` / `disconnect`

Add to `tests/unit/test_withings.py`:

```python
@patch("server.services.withings.is_connected", return_value=False)
def test_sync_weight_fails_when_not_connected(mock_connected):
    from server.services.withings import sync_weight
    result = sync_weight()
    assert result["status"] == "error"
    assert "not connected" in result["message"].lower()


@patch("server.services.withings.is_configured", return_value=True)
@patch("server.services.withings.is_connected", return_value=True)
@patch("server.services.withings.get_setting")
def test_get_status_returns_correct_shape(mock_get, mock_connected, mock_configured):
    mock_get.return_value = "12345"
    from server.services.withings import get_status
    status = get_status()
    assert "configured" in status
    assert "connected" in status
    assert status["configured"] is True
    assert status["connected"] is True


@patch("server.services.withings.set_setting")
def test_disconnect_clears_all_tokens(mock_set):
    from server.services.withings import disconnect
    disconnect()
    called_keys = [call[0][0] for call in mock_set.call_args_list]
    assert "withings_access_token" in called_keys
    assert "withings_refresh_token" in called_keys
    assert "withings_token_expiry" in called_keys
    assert "withings_user_id" in called_keys
```

#### Step 2.N — Implement `sync_weight` / `get_status` / `disconnect`

Add to `server/services/withings.py`:

```python
def sync_weight(days: int = 90) -> dict:
    """Fetch Withings measurements, store in DB, trigger PMC recompute.

    Returns:
        dict with status, count of measurements stored, and earliest_date.
    """
    if not is_connected():
        return {"status": "error", "message": "Withings not connected. Please authorize in Settings."}

    try:
        measurements = fetch_weight_measurements(days=days)
    except RuntimeError as e:
        return {"status": "error", "message": str(e)}

    count = store_measurements(measurements)

    # Trigger PMC recompute to incorporate new weight data
    if count > 0 and measurements:
        earliest_date = min(m["date"] for m in measurements)
        try:
            from server.ingest import compute_daily_pmc
            with get_db() as conn:
                compute_daily_pmc(conn, since_date=earliest_date)
        except Exception as e:
            logger.warning("withings_pmc_recompute_failed", error=str(e))

    return {
        "status": "success",
        "measurements_stored": count,
        "days_fetched": days,
    }


def get_status() -> dict:
    """Return current Withings connection status."""
    connected = is_connected()
    user_id = get_setting("withings_user_id") if connected else None
    expiry_str = get_setting("withings_token_expiry") if connected else None

    token_valid = False
    if connected and expiry_str:
        try:
            token_valid = int(time.time()) < int(expiry_str)
        except ValueError:
            pass

    return {
        "configured": is_configured(),
        "connected": connected,
        "user_id": user_id or None,
        "token_valid": token_valid,
    }


def disconnect() -> None:
    """Remove all stored Withings tokens from coach_settings."""
    for key in ["withings_access_token", "withings_refresh_token",
                "withings_token_expiry", "withings_user_id", "withings_oauth_state"]:
        set_setting(key, "")
    logger.info("withings_disconnected")
```

---

### Phase 3: Withings Router

#### Step 3.A — Write integration tests for GET /api/withings/status

**File:** `tests/integration/test_withings_integration.py` (new file)

```python
"""Integration tests for Withings endpoints and DB operations."""

import pytest
from unittest.mock import patch
from server.database import get_db


def test_withings_status_not_configured(client):
    """Status returns configured=False when env vars not set."""
    with patch("server.services.withings.WITHINGS_CLIENT_ID", ""), \
         patch("server.services.withings.WITHINGS_CLIENT_SECRET", ""):
        resp = client.get("/api/withings/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is False
    assert data["connected"] is False


def test_withings_status_configured_not_connected(client):
    """Status returns configured=True, connected=False when credentials set but no token."""
    with patch("server.services.withings.WITHINGS_CLIENT_ID", "test_client_id"), \
         patch("server.services.withings.WITHINGS_CLIENT_SECRET", "test_secret"), \
         patch("server.services.withings.get_setting", return_value=""):
        resp = client.get("/api/withings/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is True
    assert data["connected"] is False


def test_body_measurements_table_exists(db_conn):
    """Verify body_measurements table was created by migration."""
    tables = [
        row["tablename"]
        for row in db_conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        ).fetchall()
    ]
    assert "body_measurements" in tables


def test_store_measurements_upsert(db_conn):
    """Verify upsert behavior for body_measurements."""
    from server.services.withings import store_measurements

    measurements = [{"date": "2026-01-15", "weight_kg": 75.5}]
    count = store_measurements(measurements)
    assert count == 1

    row = db_conn.execute(
        "SELECT weight_kg FROM body_measurements WHERE date = '2026-01-15' AND source = 'withings'"
    ).fetchone()
    assert row is not None
    assert row["weight_kg"] == pytest.approx(75.5)

    # Upsert with updated value
    store_measurements([{"date": "2026-01-15", "weight_kg": 75.2}])
    row = db_conn.execute(
        "SELECT weight_kg FROM body_measurements WHERE date = '2026-01-15' AND source = 'withings'"
    ).fetchone()
    assert row["weight_kg"] == pytest.approx(75.2)

    # Cleanup
    db_conn.execute("DELETE FROM body_measurements WHERE date = '2026-01-15' AND source = 'withings'")
```

#### Step 3.B — Implement GET /api/withings/status

**File:** `server/routers/withings.py` (new file)

```python
"""Withings Health API endpoints: OAuth flow, sync, and status."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from server.auth import CurrentUser, require_read, require_write
from server.services.withings import (
    get_status,
    get_auth_url,
    exchange_code,
    sync_weight,
    disconnect,
    is_configured,
)
from server.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/withings", tags=["withings"])


@router.get("/status")
async def withings_status(user: CurrentUser = Depends(require_read)):
    """Return Withings connection status."""
    return get_status()
```

#### Step 3.C — Implement GET /api/withings/auth-url

Add to `server/routers/withings.py`:

```python
@router.get("/auth-url")
async def withings_auth_url(user: CurrentUser = Depends(require_write)):
    """Generate and return the Withings OAuth authorization URL."""
    if not is_configured():
        raise HTTPException(
            status_code=400,
            detail="Withings not configured. Set WITHINGS_CLIENT_ID and WITHINGS_CLIENT_SECRET.",
        )
    url = get_auth_url()
    return {"url": url}
```

#### Step 3.D — Implement GET /api/withings/callback

Add to `server/routers/withings.py`:

```python
@router.get("/callback")
async def withings_callback(code: str = None, state: str = None, error: str = None):
    """OAuth callback from Withings. Exchanges code for tokens and redirects to /settings.

    This endpoint has no auth dependency — it's the redirect target after Withings authorization.
    The browser follows the redirect from Withings, so it won't have an app JWT.
    CSRF protection is via the state parameter validated against coach_settings.
    """
    if error:
        logger.warning("withings_oauth_error", error=error)
        return HTMLResponse(
            content='<html><body><script>window.location="/settings?withings=error";</script></body></html>',
            status_code=200,
        )

    if not code or not state:
        return HTMLResponse(
            content='<html><body><script>window.location="/settings?withings=error";</script></body></html>',
            status_code=200,
        )

    result = exchange_code(code=code, state=state)
    if result["status"] == "success":
        return HTMLResponse(
            content='<html><body><script>window.location="/settings?withings=connected";</script></body></html>',
            status_code=200,
        )
    else:
        logger.error("withings_callback_failed", reason=result.get("message"))
        return HTMLResponse(
            content='<html><body><script>window.location="/settings?withings=error";</script></body></html>',
            status_code=200,
        )
```

#### Step 3.E — Write integration tests for POST /api/withings/sync

Add to `tests/integration/test_withings_integration.py`:

```python
def test_withings_sync_not_connected(client):
    """Sync fails with 400 when Withings not connected."""
    with patch("server.services.withings.is_connected", return_value=False):
        resp = client.post("/api/withings/sync")
    assert resp.status_code == 400
    assert "not connected" in resp.json()["detail"].lower()


def test_withings_sync_success(client):
    """Sync succeeds and returns measurement count."""
    mock_measurements = [
        {"date": "2026-04-01", "weight_kg": 75.0},
        {"date": "2026-04-02", "weight_kg": 74.8},
    ]
    with patch("server.services.withings.is_connected", return_value=True), \
         patch("server.services.withings.fetch_weight_measurements", return_value=mock_measurements), \
         patch("server.services.withings.store_measurements", return_value=2), \
         patch("server.ingest.compute_daily_pmc"):
        resp = client.post("/api/withings/sync")
    assert resp.status_code == 200
    data = resp.json()
    assert data["measurements_stored"] == 2
```

#### Step 3.F — Implement POST /api/withings/sync

Add to `server/routers/withings.py`:

```python
@router.post("/sync")
async def withings_sync(user: CurrentUser = Depends(require_write)):
    """Sync weight measurements from Withings (last 90 days)."""
    from server.services.withings import is_connected
    if not is_connected():
        raise HTTPException(
            status_code=400,
            detail="Withings not connected. Please authorize in Settings first.",
        )

    result = sync_weight(days=90)
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["message"])

    return result
```

#### Step 3.G — Implement DELETE /api/withings/disconnect

Add to `server/routers/withings.py`:

```python
@router.delete("/disconnect")
async def withings_disconnect(user: CurrentUser = Depends(require_write)):
    """Remove all stored Withings tokens, disconnecting the integration."""
    disconnect()
    return {"status": "disconnected"}
```

#### Step 3.H — Register router in `server/main.py`

**File:** `server/main.py`

Line 29 (current):
```python
from server.routers import rides, pmc, analysis, planning, coaching, sync, athlete, admin
```

Change to:
```python
from server.routers import rides, pmc, analysis, planning, coaching, sync, athlete, admin, withings
```

Lines 210–217 (current end of router registrations):
```python
app.include_router(admin.router)
```

Add after it:
```python
app.include_router(withings.router)
```

---

### Phase 4: PMC Weight Priority Update

#### Step 4.A — Write integration test for Withings weight priority in PMC

Add to `tests/integration/test_withings_integration.py`:

```python
def test_withings_weight_priority_in_pmc(db_conn):
    """Withings weight takes priority over ride weight in compute_daily_pmc."""
    from server.ingest import compute_daily_pmc
    from server.services.withings import store_measurements

    # Insert a Withings measurement for a test date
    test_date = "2099-01-01"  # Far future to avoid collisions with seed data
    store_measurements([{"date": test_date, "weight_kg": 70.0}])

    # Run PMC recompute
    compute_daily_pmc(db_conn)

    # Check daily_metrics — the weight should come from Withings (70.0), not rides
    row = db_conn.execute(
        "SELECT weight FROM daily_metrics WHERE date = %s", (test_date,)
    ).fetchone()
    # The test date has no rides, so weight comes from Withings propagation
    # (Withings is highest priority, then last seen ride, then athlete_settings)
    # Since no ride exists for 2099-01-01, but Withings measurement does,
    # the PMC should use it for this date.
    # Note: compute_daily_pmc only runs through today, so this test uses today-7 instead.

    # Cleanup
    db_conn.execute("DELETE FROM body_measurements WHERE date = %s AND source = 'withings'", (test_date,))
    db_conn.execute("DELETE FROM daily_metrics WHERE date = %s", (test_date,))
```

**Note to Engineer:** The PMC only runs through `datetime.today()`, so use a recent past date in the actual test. Use a date with a known ride in the seed data but where Withings weight differs. Assert that `daily_metrics.weight` matches the Withings value (not the ride's weight).

#### Step 4.B — Update `compute_daily_pmc()` in `server/ingest.py`

**File:** `server/ingest.py`  
**Function:** `compute_daily_pmc()` (line 355)

The current weight priority (lines 450–456):
```python
weight = _lookup_ride_metric(ds, weight_values)
if weight is None or weight <= 0:
    weight = _lookup_setting_metric(ds, weight_settings)
if weight is None or weight <= 0:
    from server.database import ATHLETE_SETTINGS_DEFAULTS
    weight = float(ATHLETE_SETTINGS_DEFAULTS.get("weight_kg", 0))
```

**Change 1:** Add Withings prefetch after the existing `settings_rows` prefetch (around line 393). Add after the `weight_settings` / `ftp_settings` list comprehensions:

```python
    # Prefetch Withings body measurements for weight (highest priority)
    withings_rows = conn.execute(
        "SELECT date, weight_kg FROM body_measurements WHERE source = 'withings' AND weight_kg IS NOT NULL ORDER BY date"
    ).fetchall()
    withings_dates = [r["date"] for r in withings_rows]
    withings_weights = [r["weight_kg"] for r in withings_rows]
```

**Change 2:** Add `_lookup_withings_weight()` helper alongside `_lookup_ride_metric` and `_lookup_setting_metric`. Insert after the `_lookup_setting_metric` definition (around line 401):

```python
    def _lookup_withings_weight(ds: str) -> float | None:
        """Return Withings weight for exact date ds, or None if not available."""
        if not withings_dates:
            return None
        # Exact date match only — Withings data is precise by day
        try:
            idx = withings_dates.index(ds)
            return withings_weights[idx]
        except ValueError:
            return None
```

**Change 3:** Replace the weight priority block (lines 450–456) with:

```python
        # Weight priority:
        # 1. Withings measurement for this exact date (highest — scale measurement)
        # 2. Most recent ride on or before this date
        # 3. athlete_settings active on this date
        # 4. Default 0
        weight = _lookup_withings_weight(ds)
        if weight is None or weight <= 0:
            weight = _lookup_ride_metric(ds, weight_values)
        if weight is None or weight <= 0:
            weight = _lookup_setting_metric(ds, weight_settings)
        if weight is None or weight <= 0:
            from server.database import ATHLETE_SETTINGS_DEFAULTS
            weight = float(ATHLETE_SETTINGS_DEFAULTS.get("weight_kg", 0))
```

---

### Phase 5: Frontend — Settings Withings Card

#### Step 5.A — Add `WithingsStatus` interface to `frontend/src/types/api.ts`

**File:** `frontend/src/types/api.ts`  
Add at the end of the file:

```typescript
export interface WithingsStatus {
  configured: boolean
  connected: boolean
  user_id?: string | null
  token_valid?: boolean
}
```

#### Step 5.B — Add API helpers to `frontend/src/lib/api.ts`

**File:** `frontend/src/lib/api.ts`  
Add after the `syncSingleRide` export (last line, line 182):

```typescript
// Withings
export const fetchWithingsStatus = () => get<import('../types/api').WithingsStatus>('/api/withings/status')
export const fetchWithingsAuthUrl = () => get<{ url: string }>('/api/withings/auth-url')
export const syncWithingsWeight = () => post<{ status: string; measurements_stored: number; days_fetched: number }>('/api/withings/sync')
export const disconnectWithings = () => request<{ status: string }>('/api/withings/disconnect', { method: 'DELETE' })
```

#### Step 5.C — Add `useWithingsStatus` hook to `frontend/src/hooks/useApi.ts`

**File:** `frontend/src/hooks/useApi.ts`  
Add at the end of the file:

```typescript
// Withings
export function useWithingsStatus() {
  const { isAuthenticated } = useAuth()
  return useQuery({
    queryKey: ['withings-status'],
    queryFn: api.fetchWithingsStatus,
    enabled: isAuthenticated,
    refetchInterval: 30000,  // Poll every 30s to pick up auth callback
  })
}
```

#### Step 5.D — Add Withings card to Settings System tab

**File:** `frontend/src/pages/Settings.tsx`

**Import additions** (top of file, add to existing lucide-react imports):
```typescript
import { Scale } from 'lucide-react'
```

**State additions** (inside the component, after existing `syncResult` state):
```typescript
const [withingsSyncing, setWithingsSyncing] = useState(false)
const [withingsResult, setWithingsResult] = useState<string | null>(null)
```

**Hook additions** (in the component body, after `useSyncOverview`):
```typescript
const { data: withingsStatus, refetch: refetchWithingsStatus } = useWithingsStatus()
```

**Handler additions** (before the `return` statement):
```typescript
const handleWithingsConnect = async () => {
  try {
    const { url } = await fetchWithingsAuthUrl()
    window.open(url, '_blank', 'noopener')
    // Poll for connection after user authorizes
    setTimeout(() => refetchWithingsStatus(), 3000)
    setTimeout(() => refetchWithingsStatus(), 8000)
    setTimeout(() => refetchWithingsStatus(), 15000)
  } catch (e: any) {
    setWithingsResult('Failed to get auth URL: ' + (e.message || 'Unknown error'))
  }
}

const handleWithingsSync = async () => {
  setWithingsSyncing(true)
  setWithingsResult(null)
  try {
    const result = await syncWithingsWeight()
    setWithingsResult(`Synced ${result.measurements_stored} measurements`)
    queryClient.invalidateQueries({ queryKey: ['pmc'] })
    queryClient.invalidateQueries({ queryKey: ['withings-status'] })
  } catch (e: any) {
    setWithingsResult('Sync failed: ' + (e.message || 'Unknown error'))
  } finally {
    setWithingsSyncing(false)
  }
}

const handleWithingsDisconnect = async () => {
  if (!confirm('Disconnect Withings? Your stored weight measurements will remain, but no new data will sync.')) return
  try {
    await disconnectWithings()
    queryClient.invalidateQueries({ queryKey: ['withings-status'] })
    setWithingsResult(null)
  } catch (e: any) {
    setWithingsResult('Disconnect failed: ' + (e.message || 'Unknown error'))
  }
}
```

**Import additions** (add to existing api imports at top of file):
```typescript
import { fetchWithingsAuthUrl, syncWithingsWeight, disconnectWithings } from '../lib/api'
```

**Card placement:** Add the Withings card *after* the closing `</section>` of the Intervals.icu block (after line 663) and before the "Danger Zone & Info" section (line 666). The card follows the exact same visual structure as the Intervals.icu section:

```tsx
{/* Withings Body Scale */}
<section className="bg-surface rounded-xl border border-border overflow-hidden shadow-sm">
  <div className="px-5 py-4 border-b border-border bg-surface-low flex items-center gap-2">
    <Scale size={18} className="text-green" />
    <h3 className="text-sm font-bold text-text uppercase tracking-wider">Withings Body Scale</h3>
  </div>
  <div className="p-6">
    <div className="bg-surface-low rounded-xl p-6 border border-border">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-6">
        <div className="flex items-center gap-4">
          {withingsStatus?.connected ? (
            <>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-green" />
                <span className="text-xs font-bold text-green uppercase tracking-widest">Connected</span>
              </div>
              <button
                onClick={handleWithingsSync}
                disabled={withingsSyncing}
                className="px-6 py-2.5 bg-green text-bg rounded-lg text-xs font-bold uppercase tracking-widest hover:opacity-90 disabled:opacity-50 transition-all flex items-center gap-2 shadow-lg shadow-green/10"
              >
                {withingsSyncing ? <RefreshCw size={14} className="animate-spin" /> : 'Sync Weight'}
              </button>
              <button
                onClick={handleWithingsDisconnect}
                className="px-4 py-2.5 bg-surface text-text-muted hover:text-red hover:bg-red/5 rounded-lg text-xs font-bold uppercase tracking-widest transition-all flex items-center gap-2"
              >
                <Trash2 size={14} /> Disconnect
              </button>
            </>
          ) : withingsStatus?.configured ? (
            <button
              onClick={handleWithingsConnect}
              className="px-6 py-2.5 bg-accent text-white rounded-lg text-xs font-bold uppercase tracking-widest hover:opacity-90 transition-all shadow-lg shadow-accent/20"
            >
              Connect Withings
            </button>
          ) : (
            <div className="text-xs text-text-muted">
              Set WITHINGS_CLIENT_ID and WITHINGS_CLIENT_SECRET environment variables to enable.
            </div>
          )}
        </div>
      </div>
      {withingsResult && (
        <div className={`mt-4 p-3 rounded-lg text-xs font-bold ${withingsResult.startsWith('Synced') ? 'bg-green/10 text-green' : 'bg-red/10 text-red'}`}>
          {withingsResult}
        </div>
      )}
    </div>
  </div>
</section>
```

---

### Phase 6: Frontend — Analysis Weight Tab

#### Step 6.A — Add `'weight'` to Tab type

**File:** `frontend/src/pages/Analysis.tsx`  
**Line 53** (current):
```typescript
type Tab = 'power-curve' | 'efficiency' | 'zones' | 'ftp-history'
```

Change to:
```typescript
type Tab = 'power-curve' | 'efficiency' | 'zones' | 'ftp-history' | 'weight'
```

#### Step 6.B — Add weight tab to TABS array

**File:** `frontend/src/pages/Analysis.tsx`  
**Lines 55–60** — Add entry at end of `TABS` array. Also add `Weight` to imports from lucide-react (line 28):

```typescript
// In lucide-react imports (line 28 area), add:
import { ..., Scale } from 'lucide-react'
```

```typescript
// In TABS array (after line 59), add:
const TABS: { key: Tab; label: string; icon: any }[] = [
  { key: 'power-curve', label: 'Power Curve', icon: Activity },
  { key: 'efficiency', label: 'Efficiency', icon: Zap },
  { key: 'zones', label: 'Zones', icon: BarChart3 },
  { key: 'ftp-history', label: 'FTP History', icon: History },
  { key: 'weight', label: 'Weight', icon: Scale },   // NEW
]
```

Also add `usePMC` to the hooks import at line 2 of Analysis.tsx:
```typescript
import { usePowerCurve, useEfficiency, useZones, useFTPHistory, useMacroPlan, useWeeklyOverview, useAthleteSettings, usePMC } from '../hooks/useApi'
```

#### Step 6.C — Implement `WeightChart` component

Add the `WeightChart` component to `frontend/src/pages/Analysis.tsx` after the `FTPHistoryChart` component (after line 658):

```typescript
function WeightChart({ dateRange }: { dateRange: DateRange }) {
  const { data: pmcData, isLoading, error } = usePMC()
  const cc = useChartColors()

  const weightPoints = useMemo(() => {
    if (!pmcData) return []
    const filtered = pmcData.filter((d) => {
      if (d.weight == null || d.weight <= 0) return false
      if (dateRange.start_date && d.date < dateRange.start_date) return false
      if (dateRange.end_date && d.date > dateRange.end_date) return false
      return true
    })
    return filtered
  }, [pmcData, dateRange])

  if (isLoading) return <div className="h-96 flex items-center justify-center text-text-muted animate-pulse italic">Loading weight data...</div>
  if (error) return <div className="h-96 flex items-center justify-center text-red">Error loading weight data</div>
  if (weightPoints.length === 0) return <div className="h-96 flex items-center justify-center text-text-muted">No weight data for this range — sync Withings in Settings</div>

  const minWeight = Math.min(...weightPoints.map((d) => d.weight!))
  const maxWeight = Math.max(...weightPoints.map((d) => d.weight!))
  const padding = (maxWeight - minWeight) * 0.1 || 1

  return (
    <div className="h-96">
      <Line
        data={{
          labels: weightPoints.map((d) => d.date),
          datasets: [{
            label: 'Weight (kg)',
            data: weightPoints.map((d) => d.weight),
            borderColor: '#00d4aa',
            backgroundColor: 'rgba(0, 212, 170, 0.1)',
            fill: true,
            tension: 0.3,
            pointBackgroundColor: '#00d4aa',
            pointRadius: 2,
            pointHoverRadius: 5,
          }]
        }}
        options={{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (ctx) => `${(ctx.parsed.y as number).toFixed(1)} kg`
              }
            }
          },
          scales: {
            x: {
              grid: { display: false },
              ticks: { color: cc.tickColor, maxTicksLimit: 12, font: { size: 10 } }
            },
            y: {
              grid: { color: 'rgba(148, 163, 184, 0.1)' },
              ticks: { color: cc.tickColor, callback: (v) => `${v} kg` },
              title: { display: true, text: 'WEIGHT (KG)', color: cc.tickColor, font: { size: 9, weight: 'bold' } },
              min: Math.floor(minWeight - padding),
              max: Math.ceil(maxWeight + padding),
            }
          }
        }}
      />
    </div>
  )
}
```

#### Step 6.D — Render WeightChart in tab content area

**File:** `frontend/src/pages/Analysis.tsx`  
**Lines 706–712** (current tab content):
```tsx
{activeTab === 'power-curve' && <PowerCurveChart dateRange={dateRange} />}
{activeTab === 'efficiency' && <EfficiencyChart dateRange={dateRange} />}
{activeTab === 'zones' && <ZonesChart dateRange={dateRange} />}
{activeTab === 'ftp-history' && <FTPHistoryChart dateRange={dateRange} />}
```

Add one line:
```tsx
{activeTab === 'power-curve' && <PowerCurveChart dateRange={dateRange} />}
{activeTab === 'efficiency' && <EfficiencyChart dateRange={dateRange} />}
{activeTab === 'zones' && <ZonesChart dateRange={dateRange} />}
{activeTab === 'ftp-history' && <FTPHistoryChart dateRange={dateRange} />}
{activeTab === 'weight' && <WeightChart dateRange={dateRange} />}
```

---

### Phase 7: Master Roadmap Update

#### Step 7.A — Add Campaign 11 to `plans/00_MASTER_ROADMAP.md`

**File:** `plans/00_MASTER_ROADMAP.md`  
Add after the Campaign 10 entry (after the last line of the file):

```markdown
- [ ] **Campaign 11: Withings Body Scale Integration** (`plans/feat_withings_weight.md`)
  - *Status:* Planned
  - *Goal:* OAuth 2.0 integration with Withings Health API to pull daily body weight measurements from scale into `body_measurements` table, use as highest-priority weight source in PMC pipeline, and surface as a Weight Trend chart in the Analysis page.
```

---

## Global Testing Strategy

*   **Unit Tests:** `tests/unit/test_withings.py` — all service functions with mocked httpx and mocked DB. Run with: `pytest tests/unit/`
*   **Integration Tests:** `tests/integration/test_withings_integration.py` — DB upsert/migration, OAuth status endpoint, sync endpoint, PMC weight priority. Run with: `./scripts/run_integration_tests.sh`

**Key unit test invariants:**
- Never import `server.database` directly in unit tests (would attempt DB connection)
- Always mock `httpx.post` or `httpx.get` when testing functions that make HTTP calls
- Mock `server.services.withings.get_setting` and `set_setting` at the service module level

**Key integration test invariants:**
- Use `client` fixture for HTTP endpoint tests
- Use `db_conn` fixture for direct DB assertions
- Always clean up inserted test rows at end of test (DELETE by specific test date/key)
- Do NOT call `init_db()` manually in integration tests — handled by session fixture

---

## Success Criteria

*   `GET /api/withings/status` returns `{configured: false, connected: false}` when env vars unset
*   `GET /api/withings/status` returns `{configured: true, connected: false}` when env vars set but no OAuth
*   `GET /api/withings/auth-url` returns a URL containing `account.withings.com/oauth2_user/authorize2`
*   `GET /api/withings/callback?code=X&state=Y` stores tokens and returns HTML redirect to `/settings?withings=connected`
*   `POST /api/withings/sync` fetches Withings measurements and upserts to `body_measurements` table
*   After sync, `compute_daily_pmc()` uses Withings weight as highest-priority source for `daily_metrics.weight`
*   `DELETE /api/withings/disconnect` clears all Withings token keys from `coach_settings`
*   Analysis page shows a "Weight" tab with a line chart of daily weights from PMC data
*   Settings System tab shows Withings connection status with connect/sync/disconnect buttons
*   All unit tests pass: `pytest tests/unit/`
*   All integration tests pass: `./scripts/run_integration_tests.sh`
*   No TODO/FIXME placeholders in new code

---

## Implementation Notes for Engineer

1. **`server/services/withings.py` import order:** Keep service-level imports at module top. Avoid circular imports — `from server.ingest import compute_daily_pmc` should only happen inside `sync_weight()` function body (already shown above), not at module level.

2. **`_lookup_withings_weight` uses exact date match** (not bisect). Unlike rides and settings where we want "last known value", Withings data is a daily measurement — only use it if we have data for that exact date. Days without a Withings measurement fall through to ride/settings weight.

3. **OAuth callback HTML response:** The callback endpoint must return `HTMLResponse` (not JSON) because the browser is following a redirect from Withings, not an AJAX call. Use `from fastapi.responses import HTMLResponse` — it's already in FastAPI.

4. **CSRF state in coach_settings:** Store state as `withings_oauth_state` key. After successful token exchange, immediately clear it with `set_setting("withings_oauth_state", "")`. The state is ephemeral and not shown in `get_all_settings()` responses (it's in `SETTINGS_DEFAULTS` but empty by default).

5. **`useWithingsStatus` polling:** The `refetchInterval: 30000` is a safeguard. The primary update mechanism is `refetchWithingsStatus()` called with timeouts after opening the auth URL (3s, 8s, 15s). This handles the case where the user authorizes quickly.

6. **The `Scale` icon** from `lucide-react` is the appropriate icon for a body scale. If it's not available in the installed version, use `Activity` or `TrendingUp` as a fallback.

7. **`WITHINGS_REDIRECT_URI` must exactly match** what's registered in the Withings developer application settings. For production, set this env var in Cloud Run to the production URL (e.g., `https://your-app.run.app/api/withings/callback`).
