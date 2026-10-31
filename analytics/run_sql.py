"""Run every business question in sql/ and save each answer as a CSV.

    python analytics/run_sql.py            # all files
    python analytics/run_sql.py 04 07      # only files starting with these prefixes

reports/output/<question id>.csv holds each result; reports/output/index.md
lists every question with its row count, so the answers can be browsed on
GitHub without a database.
"""
from __future__ import annotations

import sys
import time

import config
import db

DDL_FILES = {"11_reporting_views.sql"}   # create views; their questions run after


def main(prefixes: list[str]):
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in config.SQL_DIR.glob("[0-9][0-9]_*.sql") if not p.name.startswith("00_"))
    if prefixes:
        files = [p for p in files if any(p.name.startswith(x) for x in prefixes)]
    index = []
    with db.connect() as conn:
        for path in files:
            if path.name in DDL_FILES:
                db.run_file(conn, path)
            print(path.name)
            for qid, question, sql in db.questions(path):
                t0 = time.perf_counter()
                df = db.query(conn, sql)
                df.to_csv(config.OUTPUT_DIR / f"{qid}.csv", index=False)
                ms = (time.perf_counter() - t0) * 1000
                print(f"  {qid:7s} {len(df):>5} rows {ms:7.0f} ms  {question}")
                index.append((path.name, qid, question, len(df)))
    if not prefixes:
        write_index(index)


def write_index(index):
    lines = ["# Query results", "",
             "Every business question in `sql/`, with its answer saved as CSV in this folder.",
             "Regenerate with `python analytics/run_sql.py`.", ""]
    current = None
    for file, qid, question, rows in index:
        if file != current:
            lines += ["", f"## [{file}](../../sql/{file})", "", "| ID | Question | Rows |", "|---|---|---:|"]
            current = file
        lines.append(f"| [{qid}]({qid}.csv) | {question} | {rows} |")
    (config.OUTPUT_DIR / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
