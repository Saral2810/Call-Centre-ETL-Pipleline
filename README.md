# Data Pipeline 

A complete, reproducible data engineering pipeline built in **pure Python (standard library only — no external packages required)**.

It simulates a real-world collections / tele-calling scenario:

> Raw, messy call logs come in → they are validated → cleaned & enriched → loaded into a SQLite database → analyzed with SQL to answer business questions.

---

## 1. Project Overview

```
Task 1                Task 2                  Task 3               Task 4              Task 5
--------              --------                --------             --------            --------
generate_call_logs.py ingest_call_logs.py     clean_records.py     load_to_db.py       query_db.py
        │                     │                     │                    │                  │
        ▼                     ▼                     ▼                    ▼                  ▼
call_logs.json   ──►  valid_records.json  ──►  clean_records.json ──► call_center.db ──► reports/*.csv
(500 raw records)     invalid_records.json                            (2 tables)          + console output
                      ingestion_log.json
```

| Stage | Script | What it does |
|---|---|---|
| **1. Generate** | `generate_call_logs.py` | Creates 500 intentionally messy raw call records |
| **2. Ingest / Validate** | `ingest_call_logs.py` | Validates every record; splits valid vs invalid |
| **3. Clean / Transform** | `clean_records.py` | Dedupes, normalizes timestamps to IST, derives new columns |
| **4. Load** | `load_to_db.py` | Loads clean data into SQLite (idempotent) |
| **5. Analyze** | `query_db.py` | Answers business questions with SQL; exports CSVs |

---

## 2. Requirements

- **Python 3.7+** (tested on Python 3.x, Windows)
- **No external libraries needed** — everything uses the standard library:
  `json`, `random`, `copy`, `datetime`, `os`, `sqlite3`, `csv`

Check your Python version:

```bash
python --version
```

---

## 3. How to Run (End to End)

From the project folder, run the five scripts **in order**:

```bash
python generate_call_logs.py    # Task 1: create raw data
python ingest_call_logs.py      # Task 2: validate & split
python clean_records.py         # Task 3: clean & enrich
python load_to_db.py            # Task 4: load into SQLite
python query_db.py              # Task 5: run SQL analysis
```

Each script prints a summary to the console when it finishes.
Total runtime: a few seconds.

> **Note:** All scripts anchor their file paths to the script's own folder
> (`os.path.dirname(os.path.abspath(__file__))`), so they work correctly no matter
> which directory your terminal is in when you run them.

---

## 4. Stage Details

### Task 1 — Generate Raw Data (`generate_call_logs.py`)

Produces **`call_logs.json`** — exactly **500 records** (475 unique + 25 duplicates).

**Each record contains:**

| Field | Type | Example |
|---|---|---|
| `call_id` | string | `"CALL_00042"` |
| `agent_id` | string | `"AGT_017"` |
| `customer_phone` | string | `"+919876543210"` |
| `start_time` | ISO timestamp | `"2026-07-01T14:23:05"` |
| `end_time` | ISO timestamp | `"2026-07-01T14:29:41"` |
| `call_outcome` | enum | `connected` / `no_answer` / `dropped` / `callback_requested` |
| `language` | enum | `Hindi` / `English` / `Marathi` |
| `disposition_code` | enum | `PTP`, `RTP`, `WN`, `NI`, `DNC`, `BUSY`, `SWITCHED_OFF` |
| `amount_promised` | number or null | `12500` |
| `retry_flag` | boolean | `true` |

**Intentional data-quality problems injected** (to simulate real messy data):

- **~15% missing fields** — a random field is set to `null`
- **~5% duplicates** — 25 exact copies of existing records (part of the 500, not extra)
- **~3% malformed timestamps** — e.g. `"2026-13-01T25:61:00"`, `"not_a_timestamp"`, `""`

**Reproducibility:** a fixed random seed (`RANDOM_SEED = 42`) means every run
produces byte-for-byte identical output.

Key config at the top of the file:

```python
TOTAL_RECORDS  = 500
DUPLICATE_RATE = 0.05
NUM_DUPLICATES = int(TOTAL_RECORDS * DUPLICATE_RATE)   # 25
UNIQUE_RECORDS = TOTAL_RECORDS - NUM_DUPLICATES        # 475
```

---

### Task 2 — Ingest & Validate (`ingest_call_logs.py`)

Reads `call_logs.json`, validates **every record**, and splits them into:

| Output file | Contents |
|---|---|
| `valid_records.json` | Records that passed every check |
| `invalid_records.json` | Failed records, each with a `validation_errors` list explaining **why** |
| `ingestion_log.json` | Run summary: totals, valid/invalid counts, failure breakdown |

**Validation checks (small single-purpose functions):**

| Function | Checks |
|
| `validate_missing_fields()` | All required fields present and non-empty |
| `validate_data_types()` | Correct types + categorical values are in the allowed sets |
| `validate_timestamp()` | A timestamp string parses as a real ISO datetime |
| `validate_record_timestamps()` | Both timestamps valid AND `end_time` > `start_time` |
| `is_duplicate()` | `call_id` already seen earlier in the file |
| `validate_record()` | Orchestrator — runs all checks, collects all failure reasons |

**Duplicate rule:** the *first* occurrence of a `call_id` is kept as valid;
later copies are marked invalid with reason `duplicate call_id`.

**Typical result:** 500 in → ~395 valid, ~105 invalid
(≈78 missing-field failures, ≈15 malformed timestamps, ≈19 duplicates —
some duplicates also carry other injected errors, so they're counted under
their first failure reason).

---

### Task 3 — Clean & Transform (`clean_records.py`)

Reads `valid_records.json` and produces **`clean_records.json`** — the analytics-ready dataset.

**Transformations (in order):**

1. **Deduplicate on `call_id`** — keep the **latest** record by `start_time`
   (a safety net; Task 2 already removed exact duplicates).
2. **Normalize timestamps to IST** (UTC+05:30) — raw naive timestamps are
   treated as UTC and converted; output looks like `2026-07-04T19:54:25+05:30`.
   Also computes **`call_duration_seconds`** = `end_time − start_time`.
3. **Derive new columns:**
   - `call_hour` (0–23, from IST start time)
   - `call_date` (`YYYY-MM-DD`)
   - `is_weekend` (`true` for Saturday/Sunday)
4. **Bucket duration** into `duration_bucket`:
   - `short` = under 60s
   - `medium` = 60–300s
   - `long` = over 300s
5. **Impute `amount_promised` nulls with `0`** and flag them with
   **`is_amount_imputed = true`** — so a real ₹0 promise is never confused
   with a filled-in missing value.

---

### Task 4 — Load into SQLite (`load_to_db.py`)

Loads the clean data into a local SQLite database file: **`call_center.db`**.

**Two tables:**

| Table | Primary key | Contents |
|---|---|---|
| `calls` | `call_id` | One row per cleaned call (all 16 columns) |
| `ingestion_log` | `run_timestamp` | One row per pipeline run: input file, records processed, valid count, rejected count |

**Idempotency (safe to re-run):**
- Tables are created with `CREATE TABLE IF NOT EXISTS`.
- Rows are inserted with `INSERT OR REPLACE` keyed on the primary key —
  an existing row is overwritten, never duplicated.
- **Proof:** run `python load_to_db.py` twice; the row counts stay identical
  (395 calls, 1 log row) instead of doubling.

---

### Task 5 — SQL Analysis (`query_db.py`)

Answers 5 business questions against `call_center.db`. Each answer is
**printed to the console** AND **saved as a CSV** in the `reports/` folder.

| # | Question | CSV output |
|---|---|---|
| Q1 | Connect rate by language | `connect_rate_by_language.csv` |
| Q2 | Which hour has the highest `callback_requested` rate? | `callback_rate_by_hour.csv` |
| Q3 | % of calls that are `long` + their average `amount_promised` | `long_calls_stats.csv` |
| Q4 | Top 3 agents by total calls, with outcome distribution | `top3_agents_outcomes.csv`, `top3_agents_totals.csv` |
| Q5 | Call volume trend across dates | `call_volume_by_date.csv` |

**Sample findings (from the seeded data):**

- Marathi has the highest connect rate (~31.6%), then Hindi, then English.
- 15:00 (3 PM) has the highest callback rate (50%).
- ~65% of calls are `long`; their average promised amount ≈ ₹9,123
  (note: this average includes imputed 0s — filter `is_amount_imputed = 0` to average only real promises).
- Top agents: AGT_058 (11 calls), AGT_085 (9), AGT_089 (7).

**Core SQL pattern used for all "rate" questions** (conditional aggregation):

```sql
100.0 * SUM(CASE WHEN call_outcome = 'connected' THEN 1 ELSE 0 END) / COUNT(*)
```

---

## 5. Files in This Project

```
├── generate_call_logs.py     # Task 1 — raw data generator (seeded)
├── ingest_call_logs.py       # Task 2 — validation & splitting
├── clean_records.py          # Task 3 — cleaning & enrichment
├── load_to_db.py             # Task 4 — SQLite loader (idempotent)
├── query_db.py               # Task 5 — SQL analysis + CSV reports
├── README.md                 # this file
│
│   Generated at runtime:
├── call_logs.json            # 500 raw messy records
├── valid_records.json        # records that passed validation
├── invalid_records.json      # failed records + reasons
├── ingestion_log.json        # run summary (also loaded into the DB)
├── clean_records.json        # analytics-ready dataset
├── call_center.db            # SQLite database (tables: calls, ingestion_log)
└── reports/                  # one CSV per business question
    ├── connect_rate_by_language.csv
    ├── callback_rate_by_hour.csv
    ├── long_calls_stats.csv
    ├── top3_agents_outcomes.csv
    ├── top3_agents_totals.csv
    └── call_volume_by_date.csv
```

---

## 6. Design Decisions Worth Noting

- **Reproducible by design** — fixed random seed (42) makes every stage's
  output deterministic; anyone running this project gets identical results.
- **Idempotent load** — the DB loader can be re-run any number of times
  without duplicating data (primary keys + `INSERT OR REPLACE`).
- **Every rejection is explained** — invalid records carry a
  `validation_errors` list, and `ingestion_log.json` aggregates the failure
  breakdown, so data loss is never silent.
- **Imputation is flagged, never hidden** — `is_amount_imputed` preserves the
  distinction between a real 0 and a filled-in missing value.
- **Path-safe scripts** — all file paths are anchored to the script's own
  directory, so behavior doesn't depend on the terminal's working directory.
- **Small single-purpose functions** — each validation/transformation is its
  own testable function with a docstring explaining it.
- **Zero dependencies** — standard library only; nothing to `pip install`.

---

## 7. Inspecting the Database 

The `.db` file is not a human-readable in a text editor. Options:

- **VS Code:** install the free *SQLite Viewer* extension, then click `call_center.db`.
- **Python one-liner:**

```bash
python -c "import sqlite3; conn = sqlite3.connect('call_center.db'); [print(r) for r in conn.execute('SELECT call_id, call_outcome, duration_bucket FROM calls LIMIT 5')]"
```

---
END