"""Application configuration."""

import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GCP_PROJECT = os.getenv("GCP_PROJECT", "jasondel-cloudrun10")
GCP_LOCATION = os.getenv("GCP_LOCATION", "us-central1")
DB_PATH = os.getenv("COACH_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "coach.db"))
