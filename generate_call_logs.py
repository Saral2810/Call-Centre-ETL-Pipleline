import json
import os
import random
import copy
from datetime import datetime, timedelta

RANDOM_SEED    = 42
TOTAL_RECORDS  = 500
MISSING_RATE   = 0.15
DUPLICATE_RATE = 0.05
MALFORMED_RATE = 0.03

# Duplicates count toward the total: 475 unique + 25 duplicates = 500.
NUM_DUPLICATES = int(TOTAL_RECORDS * DUPLICATE_RATE)
UNIQUE_RECORDS = TOTAL_RECORDS - NUM_DUPLICATES

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "call_logs.json")

CALL_OUTCOMES     = ["connected", "no_answer", "dropped", "callback_requested"]
LANGUAGES         = ["Hindi", "English", "Marathi"]
DISPOSITION_CODES = ["PTP", "RTP", "WN", "NI", "DNC", "BUSY", "SWITCHED_OFF"]

# Fields eligible for null injection (call_id stays intact so records
# remain identifiable).
NULLABLE_FIELDS = [
    "agent_id", "customer_phone", "start_time", "end_time",
    "call_outcome", "language", "disposition_code", "amount_promised",
    "retry_flag",
]


def generate_agent_id():
    return f"AGT_{random.randint(1, 100):03d}"


def generate_customer_phone():
    """Fake Indian 10-digit mobile number starting 6-9."""
    first = random.choice("6789")
    rest = "".join(random.choices("0123456789", k=9))
    return f"+91{first}{rest}"


def generate_call_times():
    """Random start within the last 30 days, plus a 10s-15min duration."""
    base_now = datetime(2026, 7, 18, 10, 0, 0)  # fixed so output is reproducible
    start = base_now - timedelta(seconds=random.randint(0, 30 * 24 * 3600))
    end = start + timedelta(seconds=random.randint(10, 15 * 60))
    return start.isoformat(), end.isoformat()


def generate_amount_promised(call_outcome):
    """Nullable: only ~60% of connected/callback calls carry a promise."""
    if call_outcome in ("connected", "callback_requested"):
        if random.random() < 0.60:
            return round(random.randint(500, 50000), -2)
    return None


def make_record(index):
    """Build one clean, fully-populated record. Dirtiness is applied later."""
    call_outcome = random.choice(CALL_OUTCOMES)
    start_time, end_time = generate_call_times()

    return {
        "call_id":          f"CALL_{index:05d}",
        "agent_id":         generate_agent_id(),
        "customer_phone":   generate_customer_phone(),
        "start_time":       start_time,
        "end_time":         end_time,
        "call_outcome":     call_outcome,
        "language":         random.choice(LANGUAGES),
        "disposition_code": random.choice(DISPOSITION_CODES),
        "amount_promised":  generate_amount_promised(call_outcome),
        "retry_flag":       random.choice([True, False]),
    }


def inject_missing_field(record):
    """Null out one random field, keeping the schema intact."""
    record[random.choice(NULLABLE_FIELDS)] = None


def make_malformed_timestamp():
    """Several flavours of broken so a cleaning pipeline has variety to handle."""
    return random.choice([
        "2026-13-01T25:61:00",     # impossible month/hour/minute
        "18-07-2026 10:00:00",     # wrong order + space
        "2026/07/18 10:00",        # slashes
        "not_a_timestamp",
        "",
        "2026-07-18T10:00:00+ZZ",  # bad timezone suffix
    ])


def inject_malformed_timestamp(record):
    field = random.choice(["start_time", "end_time"])
    record[field] = make_malformed_timestamp()


def generate_call_log():
    """Build 475 unique records, corrupt some, then add 25 duplicates."""
    records = [make_record(i) for i in range(1, UNIQUE_RECORDS + 1)]

    for rec in random.sample(records, int(TOTAL_RECORDS * MALFORMED_RATE)):
        inject_malformed_timestamp(rec)

    for rec in random.sample(records, int(TOTAL_RECORDS * MISSING_RATE)):
        inject_missing_field(rec)

    # Deep-copied so duplicates carry the same call_id -- a true duplicate
    # that a dedup step should catch.
    duplicates = [copy.deepcopy(rec) for rec in random.sample(records, NUM_DUPLICATES)]
    records.extend(duplicates)

    random.shuffle(records)
    return records


def write_json(records, filename=OUTPUT_FILE):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(records)} records to '{filename}'")


def main():
    random.seed(RANDOM_SEED)  # seed first so everything below is reproducible

    records = generate_call_log()
    write_json(records)

    unique_ids = len({r["call_id"] for r in records})
    print(f"Total records:   {len(records)}")
    print(f"Unique call_ids: {unique_ids}")
    print(f"Duplicate rows:  {len(records) - unique_ids}")


if __name__ == "__main__":
    main()
