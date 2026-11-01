"""Shared settings for the analytics pipeline."""
import os
import sys
from pathlib import Path

# Windows consoles default to cp1252; alerts and reports print symbols such as the warning sign.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "raw"                 # source-system export (generated, git-ignored)
CLEAN_DIR = ROOT / "data" / "cleaned"            # reporting tables for Power BI / Excel (git-ignored)
SAMPLE_DIR = ROOT / "data" / "sample"            # small committed samples of every table
SQL_DIR = ROOT / "sql"
REPORTS_DIR = ROOT / "reports"
OUTPUT_DIR = REPORTS_DIR / "output"              # one CSV per SQL question
FIGURES_DIR = REPORTS_DIR / "figures"
DOCS_DIR = ROOT / "docs"
EXCEL_DIR = ROOT / "excel"
POWERBI_DIR = ROOT / "powerbi"

# docker compose up -d analytics-db
DATABASE_URL = os.environ.get(
    "ANALYTICS_DATABASE_URL",
    "postgresql://analyst:analyst@localhost:5439/analytics",
)

# Simulation window and the business events the analysis should uncover.
START_DATE = "2024-01-01"
END_DATE = "2025-12-31"
AS_OF = "2025-12-31"               # "today" for recency, stock position and forecasts
LOYALTY_LAUNCH = "2025-03-01"      # points programme for repeat buyers
COURIER_SWITCH = "2025-05-15"      # faster courier contract for Greece
SEED = 42
