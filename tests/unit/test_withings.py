"""Unit tests for server/services/withings.py"""
from unittest.mock import patch, MagicMock
import pytest
import time

# ---------------------------------------------------------------------------
# is_configured / is_connected
# ---------------------------------------------------------------------------

def test_is_configured_false_when_no_env():
    with patch("server.services.withings.WITHINGS_CLIENT_ID", ""), \
         patch("server.services.withings.WITHINGS_CLIENT_SECRET", ""):
        from server.services.withings import is_configured
        assert is_configured() is False

def test_is_configured_true_when_env_set():
    with patch("server.services.withings.WITHINGS_CLIENT_ID", "cid"), \
         patch("server.services.withings.WITHINGS_CLIENT_SECRET", "csec"):
        from server.services.withings import is_configured
        assert is_configured() is True

def test_is_connected_false_when_no_token():
    with patch("server.services.withings.get_setting", return_value=""):
        from server.services.withings import is_connected
        assert is_connected() is False

def test_is_connected_true_when_token_present():
    with patch("server.services.withings.get_setting", return_value="tok123"):
        from server.services.withings import is_connected
        assert is_connected() is True

# ---------------------------------------------------------------------------
# get_auth_url
# ---------------------------------------------------------------------------

def test_get_auth_url_contains_required_params():
    with patch("server.services.withings.WITHINGS_CLIENT_ID", "cid"), \
         patch("server.services.withings.set_setting"):
        from server.services.withings import get_auth_url
        url = get_auth_url("http://localhost:8000/api/withings/callback")
        assert "account.withings.com" in url
        assert "cid" in url
        assert "user.metrics" in url
        assert "response_type=code" in url

# ---------------------------------------------------------------------------
# _decode_weight
# ---------------------------------------------------------------------------

def test_decode_weight():
    from server.services.withings import _decode_weight
    assert abs(_decode_weight(7500, -2) - 75.0) < 0.001
    assert abs(_decode_weight(7650, -2) - 76.5) < 0.001

# ---------------------------------------------------------------------------
# fetch_weight_measurements
# ---------------------------------------------------------------------------

def test_fetch_weight_measurements_decodes_correctly():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "status": 0,
        "body": {
            "measuregrps": [
                {"date": 1700000000, "measures": [{"value": 7500, "unit": -2, "type": 1}]},
                {"date": 1700086400, "measures": [{"value": 7520, "unit": -2, "type": 1}]},
            ]
        }
    }
    mock_response.status_code = 200

    with patch("server.services.withings.get_setting", return_value="tok"), \
         patch("server.services.withings._get_valid_access_token", return_value="tok"), \
         patch("httpx.post", return_value=mock_response):
        from server.services.withings import fetch_weight_measurements
        results = fetch_weight_measurements("2023-11-14", "2023-11-15")
        assert len(results) == 2
        assert abs(results[0]["weight_kg"] - 75.0) < 0.001
        # UTC timestamp preserved from Withings Unix timestamp
        assert results[0]["measured_at"] == "2023-11-14T22:13:20Z"
        assert results[0]["date"] == "2023-11-14"

def test_fetch_weight_measurements_sends_category_1():
    """getmeas must include category=1 to exclude Withings goal/objective entries."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"status": 0, "body": {"measuregrps": []}}
    captured = {}

    def capture_post(url, data=None, **kwargs):
        captured.update(data or {})
        return mock_response

    with patch("server.services.withings._get_valid_access_token", return_value="tok"), \
         patch("httpx.post", side_effect=capture_post):
        from server.services.withings import fetch_weight_measurements
        fetch_weight_measurements("2023-11-14", "2023-11-15")

    assert captured.get("category") == 1, (
        f"Expected category=1 in getmeas request, got {captured.get('category')!r}"
    )

def test_fetch_weight_measurements_skips_non_weight_types():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "status": 0,
        "body": {
            "measuregrps": [
                {"date": 1700000000, "measures": [
                    {"value": 7500, "unit": -2, "type": 1},   # weight - keep
                    {"value": 200,  "unit": -1, "type": 6},   # fat% - skip
                ]}
            ]
        }
    }
    mock_response.status_code = 200
    with patch("server.services.withings._get_valid_access_token", return_value="tok"), \
         patch("httpx.post", return_value=mock_response):
        from server.services.withings import fetch_weight_measurements
        results = fetch_weight_measurements("2023-11-14", "2023-11-14")
        assert len(results) == 1

# ---------------------------------------------------------------------------
# exchange_code
# ---------------------------------------------------------------------------

def test_exchange_code_stores_tokens():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": 0,
        "body": {
            "access_token": "acc123",
            "refresh_token": "ref456",
            "expires_in": 10800,
            "userid": "u789",
        }
    }
    stored = {}
    def fake_set(k, v): stored[k] = v

    with patch("server.services.withings.WITHINGS_CLIENT_ID", "cid"), \
         patch("server.services.withings.WITHINGS_CLIENT_SECRET", "csec"), \
         patch("server.services.withings.get_setting", return_value="state123"), \
         patch("server.services.withings.set_setting", side_effect=fake_set), \
         patch("httpx.post", return_value=mock_response):
        from server.services.withings import exchange_code
        result = exchange_code("code123", "state123", "http://redirect")
        assert stored.get("withings_access_token") == "acc123"
        assert stored.get("withings_refresh_token") == "ref456"
        assert result["status"] == "success"

def test_exchange_code_rejects_bad_state():
    with patch("server.services.withings.get_setting", return_value="correct_state"):
        from server.services.withings import exchange_code
        result = exchange_code("code123", "WRONG_STATE", "http://redirect")
        assert result["status"] == "error"
        assert "state" in result["message"].lower()

# ---------------------------------------------------------------------------
# _get_valid_access_token
# ---------------------------------------------------------------------------

def test_get_valid_access_token_returns_valid_token():
    future_expiry = str(int(time.time()) + 7200)
    def side_effect(key):
        return {"withings_access_token": "valid_token", "withings_token_expiry": future_expiry}.get(key, "")
    with patch("server.services.withings.get_setting", side_effect=side_effect):
        from server.services.withings import _get_valid_access_token
        token = _get_valid_access_token()
        assert token == "valid_token"

def test_get_valid_access_token_refreshes_expired_token():
    past_expiry = str(int(time.time()) - 100)
    def side_effect(key):
        return {
            "withings_access_token": "old_token",
            "withings_token_expiry": past_expiry,
            "withings_refresh_token": "refresh_token_abc",
        }.get(key, "")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": 0,
        "body": {"access_token": "new_token", "refresh_token": "new_refresh", "expires_in": 10800}
    }
    with patch("server.services.withings.WITHINGS_CLIENT_ID", "client_id"), \
         patch("server.services.withings.WITHINGS_CLIENT_SECRET", "client_secret"), \
         patch("server.services.withings.set_setting"), \
         patch("server.services.withings.get_setting", side_effect=side_effect), \
         patch("httpx.post", return_value=mock_response):
        from server.services.withings import _get_valid_access_token
        token = _get_valid_access_token()
        assert token == "new_token"

# ---------------------------------------------------------------------------
# store_measurements
# ---------------------------------------------------------------------------

def test_store_measurements_upserts_correctly():
    mock_conn = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_conn)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    measurements = [
        {"date": "2026-04-01", "weight_kg": 75.0},
        {"date": "2026-04-02", "weight_kg": 74.8},
    ]
    with patch("server.services.withings.get_db", return_value=mock_ctx):
        from server.services.withings import store_measurements
        count = store_measurements(measurements)
    assert count == 2

# ---------------------------------------------------------------------------
# sync_weight / get_status / disconnect
# ---------------------------------------------------------------------------

def test_sync_weight_fails_when_not_connected():
    with patch("server.services.withings.is_connected", return_value=False):
        from server.services.withings import sync_weight
        result = sync_weight()
        assert result["status"] == "error"
        assert "not connected" in result["message"].lower()

def test_get_status_returns_correct_shape():
    with patch("server.services.withings.is_configured", return_value=True), \
         patch("server.services.withings.is_connected", return_value=True), \
         patch("server.services.withings.get_setting", return_value="12345"):
        from server.services.withings import get_status
        status = get_status()
        assert "configured" in status
        assert "connected" in status
        assert status["configured"] is True
        assert status["connected"] is True

def test_disconnect_clears_all_tokens():
    stored = {}
    def fake_set(k, v): stored[k] = v
    with patch("server.services.withings.set_setting", side_effect=fake_set):
        from server.services.withings import disconnect
        disconnect()
    assert "withings_access_token" in stored
    assert "withings_refresh_token" in stored
    assert "withings_token_expiry" in stored
    assert "withings_user_id" in stored

# ---------------------------------------------------------------------------
# Fix 1: _refresh_tokens uses correct Withings action
# ---------------------------------------------------------------------------

def test_refresh_tokens_uses_correct_action_and_grant_type():
    """Withings token refresh must use action=requesttoken + grant_type=refresh_token.

    The Withings API uses the same action=requesttoken for both initial exchange
    and refresh — the distinction is made via grant_type.
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": 0,
        "body": {"access_token": "new_tok", "refresh_token": "new_ref", "expires_in": 10800},
    }
    captured = {}
    def capture_post(url, data=None, **kwargs):
        captured.update(data or {})
        return mock_response

    with patch("server.services.withings.WITHINGS_CLIENT_ID", "cid"), \
         patch("server.services.withings.WITHINGS_CLIENT_SECRET", "csec"), \
         patch("server.services.withings.get_setting", return_value="old_refresh"), \
         patch("server.services.withings.set_setting"), \
         patch("httpx.post", side_effect=capture_post):
        from server.services.withings import _refresh_tokens
        _refresh_tokens()

    assert captured.get("action") == "requesttoken", (
        f"Expected action='requesttoken', got {captured.get('action')!r}"
    )
    assert captured.get("grant_type") == "refresh_token", (
        f"Expected grant_type='refresh_token', got {captured.get('grant_type')!r}"
    )

# ---------------------------------------------------------------------------
# Fix 3: _get_valid_access_token raises when not connected
# ---------------------------------------------------------------------------

def test_get_valid_access_token_raises_when_not_connected():
    """Must raise RuntimeError immediately if no access token is stored."""
    with patch("server.services.withings.is_connected", return_value=False):
        from server.services.withings import _get_valid_access_token
        with pytest.raises(RuntimeError, match="not connected"):
            _get_valid_access_token()

# ---------------------------------------------------------------------------
# Fix 5: exchange_code guards against HTTP error responses
# ---------------------------------------------------------------------------

def test_exchange_code_returns_error_on_http_failure():
    mock_response = MagicMock()
    mock_response.status_code = 503

    with patch("server.services.withings.WITHINGS_CLIENT_ID", "cid"), \
         patch("server.services.withings.WITHINGS_CLIENT_SECRET", "csec"), \
         patch("server.services.withings.get_setting", return_value="state123"), \
         patch("server.services.withings.set_setting"), \
         patch("httpx.post", return_value=mock_response):
        from server.services.withings import exchange_code
        result = exchange_code("code123", "state123", "http://redirect")
    assert result["status"] == "error"
    assert "503" in result["message"]

# ---------------------------------------------------------------------------
# Webhook: subscribe_notifications, unsubscribe_notifications, handle_webhook
# ---------------------------------------------------------------------------

def test_subscribe_notifications_posts_correct_params():
    """subscribe_notifications must POST action=subscribe with correct appli."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"status": 0, "body": {}}
    captured = {}

    def capture_post(url, data=None, headers=None, **kwargs):
        captured["url"] = url
        captured["data"] = data or {}
        captured["headers"] = headers or {}
        return mock_response

    with patch("server.services.withings._get_valid_access_token", return_value="tok"), \
         patch("server.services.withings.set_setting") as mock_set, \
         patch("httpx.post", side_effect=capture_post):
        from server.services.withings import subscribe_notifications
        result = subscribe_notifications("https://example.com/api/withings/webhook")

    assert result is True
    assert captured["data"]["action"] == "subscribe"
    assert captured["data"]["appli"] == 1
    assert captured["data"]["callbackurl"] == "https://example.com/api/withings/webhook"
    assert "Bearer tok" in captured["headers"]["Authorization"]
    mock_set.assert_called_once_with("withings_webhook_url", "https://example.com/api/withings/webhook")


def test_subscribe_notifications_returns_false_on_api_error():
    """subscribe_notifications returns False (non-fatal) when Withings rejects it."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"status": 293, "error": "Invalid callbackurl"}

    with patch("server.services.withings._get_valid_access_token", return_value="tok"), \
         patch("httpx.post", return_value=mock_response):
        from server.services.withings import subscribe_notifications
        result = subscribe_notifications("http://localhost/api/withings/webhook")

    assert result is False


def test_unsubscribe_notifications_posts_revoke():
    """unsubscribe_notifications must POST action=revoke."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"status": 0, "body": {}}
    captured = {}

    def capture_post(url, data=None, **kwargs):
        captured["data"] = data or {}
        return mock_response

    with patch("server.services.withings._get_valid_access_token", return_value="tok"), \
         patch("server.services.withings.get_setting", return_value="https://example.com/api/withings/webhook"), \
         patch("httpx.post", side_effect=capture_post):
        from server.services.withings import unsubscribe_notifications
        unsubscribe_notifications()

    assert captured["data"]["action"] == "revoke"
    assert captured["data"]["appli"] == 1


def test_unsubscribe_notifications_skips_when_no_url():
    """unsubscribe_notifications does nothing if no webhook URL is stored."""
    with patch("server.services.withings.get_setting", return_value=""), \
         patch("httpx.post") as mock_post:
        from server.services.withings import unsubscribe_notifications
        unsubscribe_notifications()
    mock_post.assert_not_called()


def test_handle_webhook_notification_syncs_correct_window():
    """handle_webhook_notification fetches measurements for the notified window."""
    import time
    start_ts = int(time.mktime((2026, 4, 1, 0, 0, 0, 0, 0, 0)))
    end_ts   = int(time.mktime((2026, 4, 2, 0, 0, 0, 0, 0, 0)))

    with patch("server.services.withings.get_setting", return_value="123"), \
         patch("server.services.withings.fetch_weight_measurements", return_value=[{"date": "2026-04-01", "weight_kg": 74.0}]) as mock_fetch, \
         patch("server.services.withings.store_measurements", return_value=1), \
         patch("server.database.get_db"), \
         patch("server.ingest.compute_daily_pmc"):
        from server.services.withings import handle_webhook_notification
        result = handle_webhook_notification("123", start_ts, end_ts)

    assert result["status"] == "success"
    assert result["synced"] == 1
    assert mock_fetch.call_args[0][0] == "2026-04-01"


def test_handle_webhook_notification_ignores_userid_mismatch():
    """handle_webhook_notification ignores notifications for a different user."""
    with patch("server.services.withings.get_setting", return_value="expected_user"):
        from server.services.withings import handle_webhook_notification
        result = handle_webhook_notification("different_user", 0, 1)

    assert result["status"] == "ignored"
