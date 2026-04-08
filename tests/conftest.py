"""Shared test fixtures."""

import os

# Disable Google auth for tests so endpoints don't require tokens
os.environ["GOOGLE_AUTH_ENABLED"] = "false"

# Use InMemorySpanExporter for all tests — no GCP network calls
os.environ["TESTING"] = "true"
