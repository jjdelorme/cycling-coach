"""Shared test fixtures."""

import os

# Disable Google auth for tests so endpoints don't require tokens
os.environ["GOOGLE_AUTH_ENABLED"] = "false"
