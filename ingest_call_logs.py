import json
import os
from datetime import datetime

SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE    = os.path.join(SCRIPT_DIR, "call_logs.json")
VALID_FILE    = os.path.join(SCRIPT_DIR, "valid_records.json")
INVALID_FILE  = os.path.join(SCRIPT_DIR, "invalid_records.json")
INGESTION_LOG = os.path.join(SCRIPT_DIR, "ingestion_log.json")

# amount_promised is intentionally absent -- it's allowed to be null.
REQUIRED_FIELDS = [
    "call_id", "agent_id", "customer_phone",
    "start_time", "end_time", "call_outcome",
    "language", "disposition_code", "retry_flag",
]

VALID_CALL_OUTCOMES     = {"connected", "no_answer", "dropped", "callback_requested"}
VALID_LANGUAGES         = {"Hindi", "English", "Marathi"}
VALID_DISPOSITION_CODES = {"PTP", "RTP", "WN", "NI", "DNC", "BUSY", "SWITCHED_OFF"}


def load_json(filename):
    if not os.path.exists(filename):
        raise FileNotFoundError(
            f"Input file not found: {filename}\n"
            f"Run generate_call_logs.py first."
        )
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


# Each check returns a list of problem strings; empty list means it passed.

def validate_missing_fields(record):
    reasons = []
    for field in REQUIRED_FIELDS:
        value = record.get(field)
        if value is None or value == "":
            reasons.append(f"missing field: {field}")
    return reasons


def validate_data_types(record):
    """Type checks plus allowed-value checks for the categorical fields.

    Missing (None) values are skipped here -- validate_missing_fields
    already reports those.
    """
    reasons = []

    retry = record.get("retry_flag")
    if retry is not None and not isinstance(retry, bool):
        reasons.append("retry_flag is not a boolean")

    amount = record.get("amount_promised")
    if amount is not None and not isinstance(amount, (int, float)):
        reasons.append("amount_promised is not a number")

    outcome = record.get("call_outcome")
    if outcome is not None and outcome not in VALID_CALL_OUTCOMES:
        reasons.append(f"invalid call_outcome: {outcome}")

    language = record.get("language")
    if language is not None and language not in VALID_LANGUAGES:
        reasons.append(f"invalid language: {language}")

    disposition = record.get("disposition_code")
    if disposition is not None and disposition not in VALID_DISPOSITION_CODES:
        reasons.append(f"invalid disposition_code: {disposition}")

    return reasons


def validate_timestamp(value):
    """True if value parses as an ISO-8601 datetime."""
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value)
        return True
    except ValueError:
        return False


def validate_record_timestamps(record):
    """Both timestamps must parse, and end_time must be after start_time."""
    reasons = []
    start = record.get("start_time")
    end   = record.get("end_time")

    start_ok = start is not None and validate_timestamp(start)
    end_ok   = end   is not None and validate_timestamp(end)

    if start is not None and not start_ok:
        reasons.append(f"malformed start_time: {start}")
    if end is not None and not end_ok:
        reasons.append(f"malformed end_time: {end}")

    if start_ok and end_ok:
        if datetime.fromisoformat(end) <= datetime.fromisoformat(start):
            reasons.append("end_time is not after start_time")

    return reasons


def is_duplicate(record, seen_ids):
    return record.get("call_id") in seen_ids


def validate_record(record, seen_ids):
    """Run every check; an empty result means the record is valid."""
    reasons = []
    reasons += validate_missing_fields(record)
    reasons += validate_data_types(record)
    reasons += validate_record_timestamps(record)

    if is_duplicate(record, seen_ids):
        reasons.append(f"duplicate call_id: {record.get('call_id')}")

    return reasons


def ingest(records):
    """Validate all records and sort them into valid / invalid piles."""
    valid_records   = []
    invalid_records = []
    reason_counts   = {}
    seen_ids        = set()

    for record in records:
        reasons = validate_record(record, seen_ids)

        if not reasons:
            valid_records.append(record)
            seen_ids.add(record.get("call_id"))
        else:
            bad = dict(record)
            bad["validation_errors"] = reasons
            invalid_records.append(bad)

            for reason in reasons:
                category = reason.split(":")[0].strip()
                reason_counts[category] = reason_counts.get(category, 0) + 1

    return valid_records, invalid_records, reason_counts


def write_json(data, filename):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def build_ingestion_log(total, valid_records, invalid_records, reason_counts):
    return {
        "run_timestamp":     datetime.now().isoformat(),
        "input_file":        os.path.basename(INPUT_FILE),
        "total_records":     total,
        "valid_count":       len(valid_records),
        "invalid_count":     len(invalid_records),
        "failure_breakdown": reason_counts,
    }


def print_summary(log):
    print("=" * 40)
    print("INGESTION SUMMARY")
    print("=" * 40)
    print(f"Loaded records: {log['total_records']}")
    print(f"Valid:          {log['valid_count']}")
    print(f"Invalid:        {log['invalid_count']}")
    if log["failure_breakdown"]:
        print("Failure breakdown:")
        for reason, count in sorted(log["failure_breakdown"].items()):
            print(f"  - {reason:<22} {count}")
    print("-" * 40)
    print("Wrote: valid_records.json, invalid_records.json, ingestion_log.json")


def main():
    records = load_json(INPUT_FILE)
    valid_records, invalid_records, reason_counts = ingest(records)

    write_json(valid_records, VALID_FILE)
    write_json(invalid_records, INVALID_FILE)

    log = build_ingestion_log(len(records), valid_records, invalid_records, reason_counts)
    write_json(log, INGESTION_LOG)

    print_summary(log)


if __name__ == "__main__":
    main()
