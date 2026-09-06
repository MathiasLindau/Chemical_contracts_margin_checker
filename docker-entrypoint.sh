#!/bin/bash
set -euo pipefail

python - <<'PY'
import os
import time

import psycopg

from src.margin_checker.db import init_monitoring_table

db_conn = os.environ["DB_CONN"]

for attempt in range(30):
    try:
        with psycopg.connect(db_conn) as conn:
            conn.execute("SELECT 1")
        break
    except Exception as exc:
        print(f"Waiting for PostgreSQL... ({exc})")
        time.sleep(2)
else:
    raise SystemExit("PostgreSQL did not become ready")

init_monitoring_table()

with psycopg.connect(db_conn) as conn:
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    exists = conn.execute(
        """
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'contract_chunks'
        )
        """
    ).fetchone()[0]
    count = 0
    n_contracts = 0
    if exists:
        count = conn.execute("SELECT COUNT(*) FROM contract_chunks").fetchone()[0]
        n_contracts = conn.execute(
            "SELECT COUNT(DISTINCT contract_id) FROM contract_chunks"
        ).fetchone()[0]

if count == 0 or n_contracts < 100:
    from src.margin_checker.ingest import main as ingest_contracts

    print("Ingesting contract chunks...")
    ingest_contracts()
else:
    print(f"Skipping ingest; {count} chunks from {n_contracts} contracts already present.")
PY

exec streamlit run app.py --server.address=0.0.0.0
