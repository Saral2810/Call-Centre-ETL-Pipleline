import csv
import os
import sqlite3

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
DB_FILE     = os.path.join(SCRIPT_DIR, "call_center.db")
REPORTS_DIR = os.path.join(SCRIPT_DIR, "reports")


def run_query(conn, sql):
    cursor = conn.execute(sql)
    columns = [d[0] for d in cursor.description]
    return columns, cursor.fetchall()


def print_table(title, columns, rows):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)
    print(" | ".join(columns))
    print("-" * 60)
    for row in rows:
        print(" | ".join(str(v) for v in row))


def save_csv(filename, columns, rows):
    os.makedirs(REPORTS_DIR, exist_ok=True)
    path = os.path.join(REPORTS_DIR, filename)
    try:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows(rows)
        print(f"  -> saved: reports/{filename}")
    except PermissionError:
        # Usually means the CSV is open in Excel; skip it rather than
        # failing the whole report run.
        print(f"  !! could not write reports/{filename} (file in use -- close it and re-run)")


def report(conn, title, sql, csv_name):
    """Run a query, print it, save it as CSV."""
    columns, rows = run_query(conn, sql)
    print_table(title, columns, rows)
    save_csv(csv_name, columns, rows)
    return rows


def connect_rate_by_language(conn):
    sql = """
        SELECT
            language,
            COUNT(*) AS total_calls,
            SUM(CASE WHEN call_outcome = 'connected' THEN 1 ELSE 0 END) AS connected_calls,
            ROUND(
                100.0 * SUM(CASE WHEN call_outcome = 'connected' THEN 1 ELSE 0 END) / COUNT(*),
                2
            ) AS connect_rate_pct
        FROM calls
        GROUP BY language
        ORDER BY connect_rate_pct DESC
    """
    report(conn, "Connect rate by language", sql, "connect_rate_by_language.csv")


def best_callback_hour(conn):
    sql = """
        SELECT
            call_hour,
            COUNT(*) AS total_calls,
            SUM(CASE WHEN call_outcome = 'callback_requested' THEN 1 ELSE 0 END) AS callback_calls,
            ROUND(
                100.0 * SUM(CASE WHEN call_outcome = 'callback_requested' THEN 1 ELSE 0 END) / COUNT(*),
                2
            ) AS callback_rate_pct
        FROM calls
        GROUP BY call_hour
        ORDER BY callback_rate_pct DESC
    """
    rows = report(conn, "Callback rate by hour (highest first)", sql,
                  "callback_rate_by_hour.csv")
    if rows:
        top = rows[0]
        print(f"Highest callback hour: {top[0]}:00 ({top[3]}% callbacks)")


def long_calls_stats(conn):
    sql = """
        SELECT
            ROUND(
                100.0 * SUM(CASE WHEN duration_bucket = 'long' THEN 1 ELSE 0 END) / COUNT(*),
                2
            ) AS long_call_pct,
            ROUND(
                AVG(CASE WHEN duration_bucket = 'long' THEN amount_promised END),
                2
            ) AS avg_amount_promised_long
        FROM calls
    """
    report(conn, "long calls and their average amount_promised", sql,
           "long_calls_stats.csv")


def top3_agents_outcomes(conn):
    sql = """
        SELECT
            agent_id,
            call_outcome,
            COUNT(*) AS calls
        FROM calls
        WHERE agent_id IN (
            SELECT agent_id
            FROM calls
            GROUP BY agent_id
            ORDER BY COUNT(*) DESC
            LIMIT 3
        )
        GROUP BY agent_id, call_outcome
        ORDER BY agent_id, calls DESC
    """
    report(conn, "Top 3 agents - outcome distribution", sql,
           "top3_agents_outcomes.csv")

    sql_totals = """
        SELECT agent_id, COUNT(*) AS total_calls
        FROM calls
        GROUP BY agent_id
        ORDER BY total_calls DESC
        LIMIT 3
    """
    report(conn, "Top 3 agents - total calls", sql_totals,
           "top3_agents_totals.csv")


def call_volume_trend(conn):
    sql = """
        SELECT call_date, COUNT(*) AS calls
        FROM calls
        GROUP BY call_date
        ORDER BY call_date
    """
    report(conn, "Call volume trend by date", sql, "call_volume_by_date.csv")


def main():
    if not os.path.exists(DB_FILE):
        raise FileNotFoundError(f"Database not found: {DB_FILE}\nRun load_to_db.py first.")

    conn = sqlite3.connect(DB_FILE)
    try:
        connect_rate_by_language(conn)
        best_callback_hour(conn)
        long_calls_stats(conn)
        top3_agents_outcomes(conn)
        call_volume_trend(conn)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
