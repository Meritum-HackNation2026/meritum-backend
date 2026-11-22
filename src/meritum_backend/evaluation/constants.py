"""Constants of the evaluation slice.

Features:
    US-OBS-06, US-OBS-05, F-28
"""

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
