"""Operational/admin scripts.

The package marker exists so integration tests can import individual
scripts (e.g. ``from scripts.backfill_corrupt_gps import run_backfill``)
in-process for fast TDD without forking the script. Existing scripts can
still be invoked directly via ``python scripts/<name>.py`` because each
script does its own ``sys.path`` setup.
"""
