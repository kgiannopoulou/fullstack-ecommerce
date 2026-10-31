"""Shared settings for the analytics pipeline."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "analytics" / "data"          # generated CSVs (git-ignored)
SQL_DIR = ROOT / "sql"
REPORTS_DIR = ROOT / "reports"
OUTPUT_DIR = REPORTS_DIR / "output"              # one CSV per SQL question
DOCS_DIR = ROOT / "docs"

# docker compose up -d analytics-db
DATABASE_URL = os.environ.get(
    "ANALYTICS_DATABASE_URL",
    "postgresql://analyst:analyst@localhost:5439/analytics",
)

# Simulation window and the business events the analysis should uncover.
START_DATE = "2024-01-01"
END_DATE = "2025-12-31"
LOYALTY_LAUNCH = "2025-03-01"      # points programme for repeat buyers
COURIER_SWITCH = "2025-05-15"      # faster courier contract for Greece
SEED = 42
