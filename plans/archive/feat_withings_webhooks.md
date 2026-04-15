# Feature Plan: Withings Push Notification Webhooks

## Status: Implemented — Needs Audit & Test Coverage

## Context

The core Withings OAuth integration (Campaign 11) was implemented first. During that work, push notification webhook support was added beyond the original plan's scope. This plan documents that work, defines its success criteria, and closes any remaining gaps so the auditor can verify it independently.

## What Withings Webhooks Do

Instead of the app polling Withings for new weight data, Withings calls our server when a new measurement is available. Withings POSTs form data to a registered callback URL containing:

- `userid` — the Withings user ID
- `appli` — measurement type (1 = body measurements / weight)
- `startdate` / `enddate` — Unix timestamps of the window containing new data
- `date` — ISO date string (informational)

The app must respond with HTTP 200 quickly. Any slow work (DB writes, PMC recompute) should complete within the response but not block indefinitely.

## Implementation (Already Merged to Branch)

### 1. Service Layer — `server/services/withings.py`

| Function | Purpose |
|---|---|
| `subscribe_notifications(webhook_url)` | POSTs `action=subscribe, appli=1` to `/notify`; stores URL in `withings_webhook_url` setting; returns `bool` (non-fatal on failure) |
| `unsubscribe_notifications()` | POSTs `action=revoke` to `/notify`; skips if no URL stored; called on disconnect |
| `handle_webhook_notification(userid, startdate, enddate)` | Validates `userid` matches stored user; converts timestamps to dates; calls `fetch_weight_measurements` + `store_measurements`; triggers `compute_daily_pmc` if rows were inserted |

### 2. Router — `server/routers/withings.py`

| Endpoint | Details |
|---|---|
| `POST /api/withings/webhook` | No auth (Withings calls this); accepts form fields `userid`, `appli`, `startdate`, `enddate`, `date`; ignores `appli != 1`; delegates to `handle_webhook_notification` |
| `GET /api/withings/callback` | After successful exchange, calls `subscribe_notifications(webhook_url)` |
| `DELETE /api/withings/disconnect` | Calls `unsubscribe_notifications()` before `disconnect()` |

### 3. Webhook URL Derivation — `_webhook_url_from_request()`

Derives the public webhook URL from `WITHINGS_REDIRECT_URI` by replacing `/callback` with `/webhook`. Works automatically for both local dev and production (Cloud Run URL is already the public URL).

### 4. Settings Storage

`withings_webhook_url` key added to `SETTINGS_DEFAULTS` in `server/database.py`.

## Success Criteria

- [ ] `subscribe_notifications` POSTs correct params (`action=subscribe`, `appli=1`, `callbackurl`) with Bearer token
- [ ] `subscribe_notifications` returns `False` (non-fatal) when Withings rejects the subscription
- [ ] `unsubscribe_notifications` POSTs `action=revoke` with `appli=1`
- [ ] `unsubscribe_notifications` is a no-op when no webhook URL is stored
- [ ] `POST /api/withings/webhook` requires no auth and accepts Withings form POST
- [ ] Webhook ignores `appli != 1` notifications (sleep, activity, etc.)
- [ ] `handle_webhook_notification` validates `userid` and returns `{"status": "ignored"}` on mismatch
- [ ] `handle_webhook_notification` fetches only the notified window (`startdate`→`enddate`) and stores measurements
- [ ] PMC recomputed after successful webhook sync (only if rows were stored)
- [ ] Subscribe called automatically after OAuth callback
- [ ] Unsubscribe called automatically on disconnect
- [ ] `withings_webhook_url` persisted in `coach_settings` after successful subscription

## Test Coverage (Already Written)

All 6 webhook unit tests are in `tests/unit/test_withings.py`:

| Test | Covers |
|---|---|
| `test_subscribe_notifications_posts_correct_params` | Correct action, appli, callbackurl, Bearer header; URL persisted |
| `test_subscribe_notifications_returns_false_on_api_error` | Non-fatal on Withings error status |
| `test_unsubscribe_notifications_posts_revoke` | action=revoke, appli=1 |
| `test_unsubscribe_notifications_skips_when_no_url` | No HTTP call when no URL stored |
| `test_handle_webhook_notification_syncs_correct_window` | Correct date window passed to fetch; synced count returned |
| `test_handle_webhook_notification_ignores_userid_mismatch` | Returns ignored on wrong userid |

## Gaps / Open Items

### Integration Test Coverage
The integration tests in `tests/integration/test_withings_integration.py` cover the OAuth flow but not the webhook endpoint end-to-end. An integration test that POSTs form data to `POST /api/withings/webhook` (via FastAPI `TestClient`) and verifies a measurement is written to `body_measurements` would close this gap.

### Webhook Validation (Future)
Withings does not sign webhook requests (no HMAC). The only validation is the `userid` check. For production hardening, rate limiting on the webhook endpoint could be considered but is not required for MVP.

### Local Dev Limitation
The registered `callbackurl` in local dev (`http://localhost:8000/api/withings/webhook`) is not reachable by Withings servers. The subscription will fail silently (returns `False`, logs a warning). The app falls back to manual sync via the Settings UI. This is by design and acceptable for local development.

## Deployment Notes

No additional Cloud Run environment variables are required. The webhook URL is derived automatically from `WITHINGS_REDIRECT_URI` which is already configured.

After deploying to Cloud Run, the first user OAuth connection will automatically register the public webhook URL with Withings. Existing connected users will need to disconnect and reconnect to register the webhook.
