"""STIX 2.1 bundle of checks (reports) and cases (groupings) for OpenCTI.

Reports carry the masked question only; the DISARM catalogue is attached as
attack patterns, each flagged for the analyst to confirm.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid5

from meritum_core.checks.contracts import CheckRecord, ModeratorCase

from meritum_backend.export.constants import (
    DISARM_SOURCE,
    DISARM_TECHNIQUES,
    IDENTITY_NAME,
    STIX_NAMESPACE,
    TO_CONFIRM,
)


def _id(kind: str, key: str) -> str:
    return f"{kind}--{uuid5(STIX_NAMESPACE, f'{kind}:{key}')}"


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _base(kind: str, key: str, moment: datetime, creator: str | None) -> dict[str, Any]:
    stamp = _stamp(moment)
    base: dict[str, Any] = {
        "type": kind,
        "spec_version": "2.1",
        "id": _id(kind, key),
        "created": stamp,
        "modified": stamp,
    }
    if creator is not None:
        base["created_by_ref"] = creator
    return base


def _attack_patterns(identity: str, now: datetime) -> list[dict[str, Any]]:
    patterns = []
    for code, mapped in DISARM_TECHNIQUES.items():
        pattern = _base("attack-pattern", code, now, identity)
        pattern["name"] = code
        pattern["labels"] = ["meritum-technique"]
        if mapped is None:
            pattern["description"] = f"Brak odpowiednika w DISARM ({TO_CONFIRM})."
        else:
            disarm_id, name = mapped
            pattern["description"] = f"DISARM {disarm_id} {name} ({TO_CONFIRM})."
            pattern["external_references"] = [
                {"source_name": DISARM_SOURCE, "external_id": disarm_id}
            ]
        patterns.append(pattern)
    return patterns


def build_bundle(
    records: Sequence[CheckRecord], cases: Sequence[ModeratorCase], now: datetime
) -> dict[str, Any]:
    """Build the bundle.

    Args:
        records: the checks in the window.
        cases: the cases.
        now: the export time (creation time of the identity and patterns).

    Returns:
        A STIX 2.1 bundle as JSON-ready data; no object names a person.

    Features:
        US-OBS-03, F-36
    """
    identity = _base("identity", IDENTITY_NAME, now, None)
    identity.update(name=IDENTITY_NAME, identity_class="system")
    objects = [identity, *_attack_patterns(identity["id"], now)]
    report_ids: dict[str, str] = {}
    for record in records:
        report = _base("report", record.check_id, record.received_at, identity["id"])
        report.update(
            name=f"Sprawdzenie {record.check_id}",
            description=record.question_masked,
            published=report["created"],
            report_types=["observed-data"],
            object_refs=[identity["id"]],
            labels=[f"channel:{record.channel}", *map(str, record.verdicts)],
        )
        report_ids[record.check_id] = report["id"]
        objects.append(report)
    for case in cases:
        refs = [report_ids[i] for i in case.check_ids if i in report_ids]
        grouping = _base("grouping", case.id, case.first_seen, identity["id"])
        grouping.update(
            name=f"Sprawa {case.id}",
            description=case.summary,
            context="suspicious-activity",
            object_refs=refs or [identity["id"]],
            labels=list(case.reasons),
        )
        objects.append(grouping)
    return {"type": "bundle", "id": _id("bundle", _stamp(now)), "objects": objects}
