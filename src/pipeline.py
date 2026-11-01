"""Run the whole analysis end to end.

    docker compose up -d analytics-db
    pip install -r requirements.txt
    python src/pipeline.py              # full data set (~340k records), ~4 minutes
    python src/pipeline.py --scale 0.1  # quick run (CI)

 0. simulate   the source system's messy export (data/raw/)
 1. extract    land it in PostgreSQL untouched (raw.*); later steps read it via extract.py
 2. clean      apply a documented decision per defect -> clean.*
 3. validate   score raw and clean data against the rules in code; a critical
               failure on clean data stops the run before anything is reported
 4. transform  every SQL question -> reports/output/, star schema -> data/cleaned/
 5. anomalies  daily / weekly z-scores against expected values
 6. forecast   30-day demand per SKU vs stock -> reorder list
 7. statistics significance tests, incl. the discount investigation
 8. report     management alerts, charts, reports/Executive_Analysis_Report.pdf
 9. power bi   regenerate the PBIP project (TMDL model + report pages) in powerbi/
10. excel      excel/Monthly_Business_Performance.xlsx (Windows + Excel only; skipped elsewhere)
11. notebooks  re-execute notebooks/*.ipynb (only with --notebooks)

Every artefact in reports/, docs/data_quality*.md and data/cleaned/ is rebuilt.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def step(n: int, name: str, script: str, *args: str):
    t0 = time.perf_counter()
    print(f"\n=== {n:>2}. {name} " + "=" * max(0, 56 - len(name)), flush=True)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    subprocess.run([sys.executable, str(HERE / script), *args], check=True, cwd=HERE, env=env)
    print(f"--- {name} done in {time.perf_counter() - t0:.0f}s", flush=True)


def excel_available() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import win32com.client  # noqa: F401
    except ImportError:
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", default="1.0", help="size of the simulated source data (1.0 = ~340k records)")
    ap.add_argument("--skip-generate", action="store_true", help="reuse data/raw/*.csv")
    ap.add_argument("--no-excel", action="store_true", help="do not rebuild the Excel workbook")
    ap.add_argument("--notebooks", action="store_true", help="also re-execute the analysis notebooks")
    args = ap.parse_args()
    t0 = time.perf_counter()

    if not args.skip_generate:
        step(0, "simulate the source system export", "generate_data.py", "--scale", args.scale)
    step(1, "extract: land raw export in PostgreSQL", "load_raw.py")
    step(2, "clean + data-quality decision log", "clean.py")
    step(3, "validate: data-quality rules (gate)", "validate.py")
    step(4, "transform: SQL analysis + star schema", "transform.py")
    step(5, "anomaly detection", "anomaly_detection.py")
    step(6, "30-day stockout forecast", "forecast.py")
    step(7, "statistical tests", "stats_analysis.py")
    step(8, "management alerts, charts, executive PDF", "generate_report.py")
    step(9, "Power BI project (PBIP)", "build_powerbi.py")
    if args.no_excel:
        print("\n(skipping Excel workbook: --no-excel)")
    elif excel_available():
        step(10, "Excel workbook (Power Query, Power Pivot)", "build_excel.py")
    else:
        print("\n(skipping Excel workbook: needs Windows with Microsoft Excel and pywin32)")
    if args.notebooks:
        step(11, "execute notebooks", "build_notebooks.py")
    print(f"\nPipeline finished in {time.perf_counter() - t0:.0f}s")


if __name__ == "__main__":
    main()
