"""Application configuration."""

import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GCP_PROJECT = os.getenv("GCP_PROJECT", "jasondel-cloudrun10")
GCP_LOCATION = os.getenv("GCP_LOCATION", "us-central1")
DATABASE_URL = os.getenv("CYCLING_COACH_DATABASE_URL", "postgresql://postgres:dev@localhost:5432/coach")

# Google Auth
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_AUTH_ENABLED = os.getenv("GOOGLE_AUTH_ENABLED", "true").lower() == "true"

# intervals.icu integration
INTERVALS_ICU_API_KEY = os.getenv("INTERVALS_ICU_API_KEY", "")
INTERVALS_ICU_ATHLETE_ID = os.getenv("INTERVALS_ICU_ATHLETE_ID", "")
