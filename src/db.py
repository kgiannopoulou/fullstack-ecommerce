"""Small helpers around psycopg for running SQL files and loading frames."""
from __future__ import annotations

import io
import re
from pathlib import Path

import pandas as pd
import psycopg

import config


def connect() -> psycopg.Connection:
    return psycopg.connect(config.DATABASE_URL, autocommit=True)


def run_file(conn: psycopg.Connection, path: Path) -> None:
    """Execute a whole .sql file (DDL / views) in one go."""
    conn.execute(path.read_text(encoding="utf-8"))


def copy_csv(conn: psycopg.Connection, table: str, csv_path: Path) -> int:
    with open(csv_path, encoding="utf-8") as f:
        header = f.readline().strip()
        with conn.cursor() as cur:
            with cur.copy(f"COPY {table} ({header}) FROM STDIN WITH (FORMAT csv)") as cp:
                while chunk := f.read(1 << 20):
                    cp.write(chunk)
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def copy_frame(conn: psycopg.Connection, table: str, df: pd.DataFrame) -> None:
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False, na_rep="")
    buf.seek(0)
    cols = ", ".join(df.columns)
    with conn.cursor() as cur:
        with cur.copy(f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv, NULL '')") as cp:
            cp.write(buf.read())


def query(conn: psycopg.Connection, sql: str) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql)
        cols = [d.name for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


# Analysis files mark each business question with a header comment:
#   -- Q03.2 | Are we growing month over month?
# followed by exactly one SELECT statement ending in ';'.
QUESTION = re.compile(r"^--\s*(Q\d+\.\d+)\s*\|\s*(.+)$", re.M)


def questions(path: Path) -> list[tuple[str, str, str]]:
    """Split an analysis file into (id, question, sql) triples."""
    text = path.read_text(encoding="utf-8")
    marks = list(QUESTION.finditer(text))
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[m.end():end]
        stmt = body[: body.rfind(";") + 1].strip() if ";" in body else body.strip()
        out.append((m.group(1), m.group(2).strip(), stmt))
    return out
