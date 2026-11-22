"""JSON and CSV rows of checks and cases; none carries a person's identifier."""

import csv
import io
from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from meritum_core.checks.contracts import CheckRecord, ModeratorCase

from meritum_backend.export.constants import CSV_COLUMNS, CSV_FORMULA_PREFIXES


def case_ids_by_check(cases: Sequence[ModeratorCase]) -> dict[str, list[str]]:
    """Group case ids under each check they cover.

    Args:
        cases: the cases.

    Returns:
        Check id to the ids of its cases.

    Features:
        US-OBS-03, F-36
    """
    found: dict[str, list[str]] = defaultdict(list)
    for case in cases:
        for check_id in case.check_ids:
            found[check_id].append(case.id)
    return found


def check_row(record: CheckRecord, case_ids: Sequence[str]) -> dict[str, object]:
    """One check without session, user and channel hash; the question stays masked.

    Args:
        record: the stored record.
        case_ids: the cases that cover the check.

    Returns:
        The exported fields.

    Features:
        US-OBS-03, F-36
    """
    return {
        "check_id": record.check_id,
        "channel": record.channel,
        "received_at": record.received_at.isoformat(),
        "answered_at": record.answered_at.isoformat(),
        "status": record.status,
        "verdicts": list(record.verdicts),
        "source_ids": record.source_ids,
        "corpus_version": record.corpus_version,
        "cache_hit": record.cache_hit,
        "case_ids": list(case_ids),
        "question_masked": record.question_masked,
    }


def case_row(case: ModeratorCase) -> dict[str, Any]:
    """One case; core's model has no asker identifiers.

    Args:
        case: the case.

    Returns:
        The case as JSON-ready data.

    Features:
        US-OBS-03, F-36
    """
    return case.model_dump(mode="json")


def _safe(value: object) -> str:
    text = ";".join(map(str, value)) if isinstance(value, list) else str(value)
    return f"'{text}" if text.startswith(CSV_FORMULA_PREFIXES) else text


def to_csv(rows: Sequence[dict[str, object]]) -> str:
    """Render check rows as CSV, defusing cells a spreadsheet would run as formulas.

    Args:
        rows: the output of ``check_row``.

    Returns:
        The CSV text with a header line.

    Features:
        US-OBS-03, F-36
    """
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    writer.writerows([_safe(row[c]) for c in CSV_COLUMNS] for row in rows)
    return out.getvalue()
