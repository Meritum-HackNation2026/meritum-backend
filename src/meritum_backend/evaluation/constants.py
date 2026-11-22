"""Constants of the evaluation slice.

Features:
    US-OBS-06, US-OBS-05, F-28
"""

from datetime import timedelta
from typing import Final

from meritum_core.checks.contracts import StaffRole

GOLDEN_DATASET: Final = "golden"
"""The dataset id of the golden set; any other id names an uploaded file."""

MIN_CASES: Final = 30
"""Fewest cases an uploaded set may have (US-OBS-05)."""

MAX_CASES: Final = 1000
"""Most cases an uploaded set may have."""

MAX_UPLOAD_BYTES: Final = 2_000_000
"""Largest uploaded case file."""

RUN_LIST_LIMIT: Final = 50
"""Runs the list endpoint returns, newest first."""

CASE_COLUMNS: Final = ("case_id", "scenario", "text", "expected")
"""Header of a CSV case file; a JSON file is a list of objects with these keys."""

PANEL_PATH: Final = "/panel/eval"
"""Panel page that lists the runs."""

NO_RUN_DETAIL: Final = "run not found"
"""404 detail: no run with that id."""

NO_DATASET_DETAIL: Final = "dataset not found"
"""422 detail: the run names a dataset that was not uploaded."""

NO_FINISHED_RUN_DETAIL: Final = "no finished run on the golden set"
"""404 detail of the public summary."""

QUEUE_DOWN_DETAIL: Final = "job queue unavailable"
"""503 detail: the worker's database is unreachable."""

RUN_ROLES: Final[frozenset[StaffRole]] = frozenset({"analyst", "admin"})
"""Staff roles that may see and start runs (US-OBS-06)."""

RUN_FAILED_STATES: Final = frozenset(
    {"ERROR", "CANCELLED", "MAX_RECOVERY_ATTEMPTS_EXCEEDED"}
)
"""Workflow statuses of a run that did not finish."""

RUN_RUNNING_STATES: Final = frozenset({"PENDING"})
"""Workflow statuses of a run the worker is executing."""

CONNECT_TIMEOUT: Final = 3
"""Maximum seconds spent establishing a database connection."""

INSERT_EVAL_RUN: Final = (
    "INSERT INTO eval_runs (id, user_id, started_at, run) VALUES (%s, %s, %s, %s)"
)
"""SQL: store a run."""
LIST_EVAL_RUNS: Final = (
    "SELECT id, user_id, started_at, run FROM eval_runs ORDER BY started_at DESC"
)
"""SQL: runs, newest first."""
GET_EVAL_RUN: Final = "SELECT id, user_id, started_at, run FROM eval_runs WHERE id = %s"
"""SQL: one run by id."""

INSERT_EVAL_DATASET: Final = (
    "INSERT INTO eval_datasets (id, name, blob_id, cases) VALUES (%s, %s, %s, %s)"
)
"""SQL: store a dataset."""
GET_EVAL_DATASET: Final = (
    "SELECT id, name, blob_id, cases FROM eval_datasets WHERE id = %s"
)
"""SQL: one dataset by id."""

DATASET_CSV_TYPE: Final = "text/csv; charset=utf-8"
"""Content type stored for an uploaded CSV case file."""
DATASET_JSON_TYPE: Final = "application/json; charset=utf-8"
"""Content type stored for an uploaded JSON case file."""

DATASET_RETENTION: Final = timedelta(days=365)
"""How long an uploaded case file stays in the blob store."""
