"""Unit tests for ``scripts/backfill_ride_start_geo.py``.

These exercise the localhost guard and the ICU id extraction helper without
touching a database. The integration test in
``tests/integration/test_backfill_ride_start_geo.py`` covers the full
end-to-end flow against a seeded DB.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Load the script as a module without invoking its CLI entry point.
_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "backfill_ride_start_geo.py"
_spec = importlib.util.spec_from_file_location("backfill_ride_start_geo", _SCRIPT_PATH)
backfill_module = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("backfill_ride_start_geo", backfill_module)
_spec.loader.exec_module(backfill_module)


# ---------------------------------------------------------------------------
# _is_localhost_database_url
# ---------------------------------------------------------------------------


def test_localhost_url_is_accepted():
    assert backfill_module._is_localhost_database_url("postgresql://u:p@localhost:5432/db")


def test_127_0_0_1_url_is_accepted():
    assert backfill_module._is_localhost_database_url("postgresql://u:p@127.0.0.1:5432/db")


def test_ipv6_loopback_url_is_accepted():
    assert backfill_module._is_localhost_database_url("postgresql://u:p@[::1]:5432/db")


def test_remote_host_is_rejected():
    assert not backfill_module._is_localhost_database_url(
        "postgresql://u:p@db.neon.tech:5432/coach"
    )


def test_localhost_substring_in_remote_host_is_not_a_false_positive():
    """``localhost.example.com`` is NOT loopback — must be rejected."""
    assert not backfill_module._is_localhost_database_url(
        "postgresql://u:p@localhost.example.com:5432/db"
    )


def test_empty_url_is_rejected():
    assert not backfill_module._is_localhost_database_url("")


def test_garbage_url_is_rejected():
    assert not backfill_module._is_localhost_database_url("not-a-url")


# ---------------------------------------------------------------------------
# _icu_id_from_filename
# ---------------------------------------------------------------------------


def test_icu_id_strips_only_the_icu_underscore_prefix():
    # Real ICU filenames in the wild keep the leading 'i' that belongs to the
    # ICU activity id itself.
    assert backfill_module._icu_id_from_filename("icu_i137210941") == "i137210941"


def test_icu_id_passes_through_unfamiliar_filename():
    assert backfill_module._icu_id_from_filename("garmin_12345.fit") == "garmin_12345.fit"


# ---------------------------------------------------------------------------
# main() guard behaviour
# ---------------------------------------------------------------------------


def test_main_refuses_remote_without_allow_remote(monkeypatch, caplog):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.neon.tech:5432/coach")
    rc = backfill_module.main([])
    assert rc == 2


def test_main_refuses_when_database_url_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    rc = backfill_module.main([])
    assert rc == 2
