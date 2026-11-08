"""
Run a .sql file against Tiger Data, one statement at a time.

    python run_sql.py tiger_setup.sql

Needs TIGER_URL set to your connection string (see instructions).
"""
import os
import sys

import psycopg

path = sys.argv[1] if len(sys.argv) > 1 else "tiger_setup.sql"

with open(path) as f:
    # drop full-line comments, then split into individual statements
    lines = [l for l in f.read().splitlines() if not l.strip().startswith("--")]
statements = [s.strip() for s in "\n".join(lines).split(";") if s.strip()]

with psycopg.connect(os.environ["TIGER_URL"], autocommit=True) as conn:
    for i, stmt in enumerate(statements, 1):
        first_line = stmt.splitlines()[0][:70]
        try:
            conn.execute(stmt)
            print(f"[{i}/{len(statements)}] OK    {first_line}")
        except Exception as e:
            print(f"[{i}/{len(statements)}] ERROR {first_line}\n        {e}")

print("Done.")
