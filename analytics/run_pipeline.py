"""Run the whole analysis end to end.

    docker compose up -d analytics-db
    pip install -r analytics/requirements.txt
    python analytics/run_pipeline.py              # full data set (~340k records)
    python analytics/run_pipeline.py --scale 0.1  # quick run (CI)

generate -> load raw -> clean (+ data-quality report) -> 66 SQL questions ->
statistical tests -> Excel report. Every artefact in reports/ is rebuilt.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def step(name: str, *args: str):
    t0 = time.perf_counter()
    print(f"\n=== {name} " + "=" * (60 - len(name)))
    subprocess.run([sys.executable, str(HERE / args[0]), *args[1:]], check=True, cwd=HERE)
    print(f"--- {name} done in {time.perf_counter() - t0:.0f}s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", default="1.0")
    ap.add_argument("--skip-generate", action="store_true", help="reuse analytics/data/*.csv")
    args = ap.parse_args()
    if not args.skip_generate:
        step("generate messy source data", "generate_data.py", "--scale", args.scale)
    step("load raw export", "load_raw.py")
    step("clean + data-quality log", "clean.py")
    step("SQL analysis", "run_sql.py")
    step("statistical tests", "stats_analysis.py")
    step("Excel report", "build_excel_report.py")


if __name__ == "__main__":
    main()
