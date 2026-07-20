import json
import os
import sqlite3

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CLEAN_FILE = os.path.join(SCRIPT_DIR, "clean_records.json")
LOG_FILE   = os.path.join(SCRIPT_DIR, "ingestion_log.json")
DB_FILE    = os.path.join(SCRIPT_DIR, "call_center.db")

CALL_COLUMNS = [
    "call_id", "agent_id", "customer_phone", "start_time", "end_time",
    "call_outcome", "language", "disposition_code", "amount_promised",
    "retry_flag", "call_duration_seconds", "call_hour", "call_date",
    "is_weekend", "duration_bucket", "is_amount_imputed",
]


def load_json(filename):
    if not os.path.exists(filename):
        raise FileNotFoundError(f"Input file not found: {filename}")
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


def create_tables(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS calls (
            call_id                TEXT PRIMARY KEY,
            agent_id               TEXT,
            customer_phone         TEXT,
            start_time             TEXT,
            end_time               TEXT,
            call_outcome           TEXT,
            language               TEXT,
            disposition_code       TEXT,
            amount_promised        REAL,
            retry_flag             INTEGER,
            call_duration_seconds  INTEGER,
            call_hour              INTEGER,
            call_date              TEXT,
            is_weekend             INTEGER,
            duration_bucket        TEXT,
            is_amount_imputed      INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ingestion_log (
            run_timestamp      TEXT PRIMARY KEY,
            input_file         TEXT,
            records_processed  INTEGER,
            valid_count        INTEGER,
            rejected_count     INTEGER
        )
    """)
    conn.commit()


def insert_calls(conn, records):
    placeholders = ", ".join("?" for _ in CALL_COLUMNS)
    sql = f"INSERT OR REPLACE INTO calls ({', '.join(CALL_COLUMNS)}) VALUES ({placeholders})"

    rows = [tuple(r.get(col) for col in CALL_COLUMNS) for r in records]
    conn.executemany(sql, rows)
    conn.commit()
    return len(rows)


def insert_ingestion_log(conn, log):
    conn.execute(
        """
        INSERT OR REPLACE INTO ingestion_log (
            run_timestamp, input_file, records_processed,
            valid_count, rejected_count
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            log.get("run_timestamp"),
            log.get("input_file"),
            log.get("total_records"),
            log.get("valid_count"),
            log.get("invalid_count"),
        ),
    )
    conn.commit()


def print_summary(conn, inserted_calls):
    call_count = conn.execute("SELECT COUNT(*) FROM calls").fetchone()[0]
    log_count  = conn.execute("SELECT COUNT(*) FROM ingestion_log").fetchone()[0]

    print("=" * 40)
    print("DATABASE LOAD SUMMARY")
    print("=" * 40)
    print(f"Cleaned records processed:   {inserted_calls}")
    print(f"Rows now in 'calls':         {call_count}")
    print(f"Rows now in 'ingestion_log': {log_count}")
    print("-" * 40)
    print(f"Database file: {DB_FILE}")


def main():
    records = load_json(CLEAN_FILE)
    log     = load_json(LOG_FILE)

    conn = sqlite3.connect(DB_FILE)
    try:
        create_tables(conn)
        inserted = insert_calls(conn, records)
        insert_ingestion_log(conn, log)
        print_summary(conn, inserted)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
