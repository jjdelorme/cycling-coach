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

# App session JWT
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "24"))

# intervals.icu integration
INTERVALS_ICU_API_KEY = os.getenv("INTERVALS_ICU_API_KEY", "")
INTERVALS_ICU_ATHLETE_ID = os.getenv("INTERVALS_ICU_ATHLETE_ID", "")
INTERVALS_ICU_DISABLED = os.getenv("INTERVALS_ICU_DISABLE", "0").lower() in ("1", "true", "yes")

# Withings integration
WITHINGS_CLIENT_ID = os.getenv("WITHINGS_CLIENT_ID", "")
WITHINGS_CLIENT_SECRET = os.getenv("WITHINGS_CLIENT_SECRET") or os.getenv("WITHINGS_SECRET", "")
WITHINGS_REDIRECT_URI = os.getenv("WITHINGS_REDIRECT_URI", "http://localhost:8000/api/withings/callback")
