import json
import os
from datetime import datetime, timezone, timedelta

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE  = os.path.join(SCRIPT_DIR, "valid_records.json")
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "clean_records.json")

IST = timezone(timedelta(hours=5, minutes=30))

# Raw timestamps are naive; we assume they were recorded in UTC (the usual
# convention for system logs) and convert to IST for local reporting.
SOURCE_TZ = timezone.utc


def load_json(filename):
    if not os.path.exists(filename):
        raise FileNotFoundError(
            f"Input file not found: {filename}\n"
            f"Run ingest_call_logs.py first."
        )
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_to_ist(ts_string):
    """Parse a naive ISO timestamp, treat it as UTC, convert to IST."""
    naive = datetime.fromisoformat(ts_string)
    return naive.replace(tzinfo=SOURCE_TZ).astimezone(IST)


def deduplicate_latest(records):
    """Keep only the newest record (by start_time) for each call_id."""
    best_by_id = {}

    for rec in records:
        call_id = rec["call_id"]
        current_start = parse_to_ist(rec["start_time"])

        if call_id not in best_by_id:
            best_by_id[call_id] = rec
        elif current_start > parse_to_ist(best_by_id[call_id]["start_time"]):
            best_by_id[call_id] = rec

    return list(best_by_id.values())


def bucket_duration(seconds):
    if seconds < 60:
        return "short"
    elif seconds <= 300:
        return "medium"
    return "long"


def clean_record(rec):
    """Return a new, enriched copy of the record (input is not modified)."""
    cleaned = dict(rec)

    start_ist = parse_to_ist(rec["start_time"])
    end_ist   = parse_to_ist(rec["end_time"])

    cleaned["start_time"] = start_ist.isoformat()
    cleaned["end_time"]   = end_ist.isoformat()

    duration = (end_ist - start_ist).total_seconds()
    cleaned["call_duration_seconds"] = int(duration)

    cleaned["call_hour"]  = start_ist.hour
    cleaned["call_date"]  = start_ist.date().isoformat()
    cleaned["is_weekend"] = start_ist.weekday() >= 5  # Sat=5, Sun=6

    cleaned["duration_bucket"] = bucket_duration(duration)

    # Flag imputed amounts so a real 0 is never confused with a filled-in null.
    if rec.get("amount_promised") is None:
        cleaned["amount_promised"]   = 0
        cleaned["is_amount_imputed"] = True
    else:
        cleaned["is_amount_imputed"] = False

    return cleaned


def clean_all(records):
    deduped = deduplicate_latest(records)
    return [clean_record(rec) for rec in deduped]


def write_json(data, filename):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def print_summary(input_count, cleaned):
    imputed = sum(1 for r in cleaned if r["is_amount_imputed"])
    buckets = {}
    for r in cleaned:
        buckets[r["duration_bucket"]] = buckets.get(r["duration_bucket"], 0) + 1

    print("=" * 40)
    print("CLEANING SUMMARY")
    print("=" * 40)
    print(f"Records in (valid):      {input_count}")
    print(f"Records out (cleaned):   {len(cleaned)}")
    print(f"Removed as duplicates:   {input_count - len(cleaned)}")
    print(f"amount_promised imputed: {imputed}")
    print("Duration buckets:")
    for name in ("short", "medium", "long"):
        print(f"  - {name:<7} {buckets.get(name, 0)}")
    print("-" * 40)
    print(f"Wrote {len(cleaned)} records to clean_records.json")


def main():
    records = load_json(INPUT_FILE)
    cleaned = clean_all(records)
    write_json(cleaned, OUTPUT_FILE)
    print_summary(len(records), cleaned)


if __name__ == "__main__":
    main()
