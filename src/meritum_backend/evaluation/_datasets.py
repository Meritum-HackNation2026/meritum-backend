"""Reading and validating an uploaded case file (CSV or JSON)."""

import csv
import io
import json

from pydantic import TypeAdapter, ValidationError

from meritum_backend.evaluation.constants import CASE_COLUMNS, MAX_CASES, MIN_CASES
from meritum_backend.evaluation.models import EvalCaseInput


def parse_cases(filename: str, data: bytes) -> list[EvalCaseInput]:
    """Read the cases of an uploaded file and check the set as a whole.

    Args:
        filename: the uploaded name; ``.json`` is read as JSON, anything else as CSV.
        data: the file's bytes (UTF-8).

    Returns:
        The validated cases.

    Raises:
        ValueError: not UTF-8, bad JSON, a missing column, an invalid case, fewer
            than the minimum or more than the maximum cases, or a repeated id.

    Features:
        US-OBS-05, F-26
    """
    try:
        text = data.decode("utf-8-sig")
        rows = (
            _json_rows(text) if filename.lower().endswith(".json") else _csv_rows(text)
        )
        cases = TypeAdapter(list[EvalCaseInput]).validate_python(rows)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        msg = f"invalid case file: {exc}"
        raise ValueError(msg) from exc
    if not MIN_CASES <= len(cases) <= MAX_CASES:
        msg = f"a case file has {MIN_CASES} to {MAX_CASES} cases, this one {len(cases)}"
        raise ValueError(msg)
    if len({case.case_id for case in cases}) != len(cases):
        msg = "case_id repeats in the file"
        raise ValueError(msg)
    return cases


def _json_rows(text: str) -> object:
    return json.loads(text)


def _csv_rows(text: str) -> object:
    reader = csv.DictReader(io.StringIO(text))
    if tuple(reader.fieldnames or ()) != CASE_COLUMNS:
        msg = f"a CSV case file starts with the header {','.join(CASE_COLUMNS)}"
        raise ValueError(msg)
    return list(reader)
