"""Export API: checks and cases for the analyst's tools (JSON, CSV, STIX 2.1)."""

import asyncio
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from meritum_core.checks import CheckRecordRepository
from meritum_core.checks.contracts import CheckRecord
from meritum_core.moderation import ModeratorCaseRepository

from meritum_backend.export._stix import build_bundle
from meritum_backend.export._tabular import (
    case_ids_by_check,
    case_row,
    check_row,
    to_csv,
)
from meritum_backend.export.constants import (
    CSV_MEDIA_TYPE,
    DEFAULT_DAYS,
    EXPORT_ROLES,
    MAX_DAYS,
    STIX_MEDIA_TYPE,
)
from meritum_backend.staff import StaffMember
from meritum_backend.staff.api import StaffGate

router = APIRouter(prefix="/api/v1/export", tags=["export"])
Exporter = Annotated[StaffMember, Depends(StaffGate(EXPORT_ROLES))]


class ExportFormat(StrEnum):
    """Formats of the export.

    Features:
        US-OBS-03, F-36
    """

    JSON = "json"
    CSV = "csv"
    STIX = "stix"


def get_records(request: Request) -> CheckRecordRepository:
    """The check record store the app built (overridden in tests).

    Args:
        request: the current request (holds the app state).

    Returns:
        The app's check record store.

    Features:
        US-OBS-03, F-36
    """
    return request.app.state.repositories.records


def get_cases(request: Request) -> ModeratorCaseRepository:
    """The case store the app built (overridden in tests).

    Args:
        request: the current request (holds the app state).

    Returns:
        The app's case store.

    Features:
        US-OBS-03, F-36
    """
    return request.app.state.cases


@router.get("")
async def export(
    _member: Exporter,
    records: Annotated[CheckRecordRepository, Depends(get_records)],
    cases: Annotated[ModeratorCaseRepository, Depends(get_cases)],
    export_format: Annotated[ExportFormat, Query(alias="format")] = ExportFormat.JSON,
    days: Annotated[int, Query(ge=1, le=MAX_DAYS)] = DEFAULT_DAYS,
) -> Response:
    """Export the checks of the last ``days`` days and the cases, masked.

    shortcut: the record port has no "list all", so the checks are the ones the
    cases cover; switch to a port query when core adds one.

    Args:
        _member: a signed-in analyst or administrator.
        records: the check record store.
        cases: the case store.
        export_format: ``json``, ``csv`` or ``stix``.
        days: how far back to take checks.

    Returns:
        The export in the chosen format.

    Features:
        US-OBS-03, F-36
    """
    now = datetime.now(UTC)
    all_cases = await cases.list_cases()
    ids = dict.fromkeys(i for case in all_cases for i in case.check_ids)
    found = await asyncio.gather(*(records.get(i) for i in ids))
    since = now - timedelta(days=days)
    window: list[CheckRecord] = sorted(
        (r for r in found if r is not None and r.received_at >= since),
        key=lambda r: r.received_at,
        reverse=True,
    )
    if export_format is ExportFormat.STIX:
        return JSONResponse(
            build_bundle(window, all_cases, now), media_type=STIX_MEDIA_TYPE
        )
    by_check = case_ids_by_check(all_cases)
    rows = [check_row(r, by_check.get(r.check_id, ())) for r in window]
    if export_format is ExportFormat.CSV:
        return Response(to_csv(rows), media_type=CSV_MEDIA_TYPE)
    return JSONResponse({"checks": rows, "cases": [case_row(c) for c in all_cases]})
