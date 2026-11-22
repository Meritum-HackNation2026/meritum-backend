"""Export: JSON, CSV and STIX 2.1 of checks and cases, masked, for analysts."""

import asyncio
import csv
import io
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from meritum_core.checks.contracts import CaseClaim, CheckRecord, ModeratorCase
from tests.staff.test_staff_api import ADMIN, member

from meritum_backend.export import api as export_api
from meritum_backend.main import create_app
from meritum_backend.settings import Settings

NOW = datetime.now(UTC)
HASH = "a" * 64
URL = "/api/v1/export"
STIX_ID = re.compile(
    r"^[a-z][a-z0-9-]+--[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
STIX_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
REQUIRED = {
    "identity": {"name"},
    "report": {"name", "published", "object_refs"},
    "grouping": {"context", "object_refs"},
    "attack-pattern": {"name"},
}


def _record(i: int, received: datetime) -> CheckRecord:
    return CheckRecord(
        check_id=f"c{i}",
        session_id=HASH,
        channel="discord",
        channel_user_hash=HASH,
        received_at=received,
        answered_at=received,
        question_masked=f"pytanie {i}, =HYPERLINK(1)",
        status="done",
        verdicts=["insufficient_evidence"],
        source_ids=[],
        corpus_version="test",
        models=[],
        retention_until=received + timedelta(days=30),
    )


@pytest.fixture
def app() -> FastAPI:
    app = create_app(
        Settings(database_url="postgresql://x:x@127.0.0.1:1/x", admin_emails=ADMIN)
    )
    records = app.state.repositories.records
    for i in range(10):
        asyncio.run(records.save(_record(i, NOW - timedelta(days=i % 5))))
    asyncio.run(records.save(_record(99, NOW - timedelta(days=30))))
    claims = [
        CaseClaim(claim="Paszport zdrożeje.", check_ids=[f"c{i}", "c99"])
        for i in range(9)  # c9 has no moderator case.
    ]
    case = ModeratorCase(
        id="#S-1",
        state="open",
        reasons=["insufficient_evidence"],
        summary="Paszport",
        claims=claims,
        distinct_askers=3,
        first_seen=NOW,
        last_seen=NOW,
    )
    asyncio.run(app.state.cases.save(case))
    return app


def _check_stix(bundle: dict[str, Any]) -> None:
    assert bundle["type"] == "bundle"
    assert STIX_ID.match(bundle["id"])
    ids = set()
    for obj in bundle["objects"]:
        assert obj["spec_version"] == "2.1"
        assert STIX_ID.match(obj["id"])
        assert obj["id"].split("--")[0] == obj["type"]
        assert obj["id"] not in ids
        ids.add(obj["id"])
        assert STIX_TIME.match(obj["created"])
        assert STIX_TIME.match(obj["modified"])
        assert REQUIRED[obj["type"]] <= obj.keys()
    for obj in bundle["objects"]:
        for ref in obj.get("object_refs", []):
            assert ref in ids


@pytest.mark.parametrize("role", ["analyst", "admin"])
def test_stix_bundle_is_valid_and_has_no_identifiers(app: FastAPI, role: str) -> None:
    response = member(app, role).get(URL, params={"format": "stix"})
    assert response.status_code == 200, response.text
    assert "json" in response.headers["content-type"]
    bundle = response.json()
    _check_stix(bundle)
    kinds = [o["type"] for o in bundle["objects"]]
    assert kinds.count("report") == 10  # c99 is older than a week
    assert kinds.count("grouping") == 1
    for forbidden in (HASH, "channel_user_hash", "session_id", "user_id"):
        assert forbidden not in response.text


def test_disarm_techniques_are_flagged_for_analyst_confirmation(app: FastAPI) -> None:
    bundle = member(app, "analyst").get(URL, params={"format": "stix"}).json()
    patterns = [o for o in bundle["objects"] if o["type"] == "attack-pattern"]
    assert patterns
    for pattern in patterns:
        assert "do potwierdzenia przez analityka" in pattern["description"]
    disarm = [
        r
        for p in patterns
        for r in p.get("external_references", [])
        if r["source_name"] == "DISARM"
    ]
    assert disarm
    assert all(re.match(r"^T\d{4}(\.\d{3})?$", r["external_id"]) for r in disarm)


def test_json_and_csv_are_masked(app: FastAPI) -> None:
    analyst = member(app, "analyst")
    body = analyst.get(URL, params={"format": "json"}).json()
    assert len(body["checks"]) == 10
    uncased = next(row for row in body["checks"] if row["check_id"] == "c9")
    assert uncased["case_ids"] == []
    assert body["cases"][0]["id"] == "#S-1"
    text = analyst.get(URL, params={"format": "csv"})
    assert text.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(text.text)))
    assert len(rows) == 10
    assert rows[0]["case_ids"] == "#S-1"
    assert not next(row for row in rows if row["check_id"] == "c9")["case_ids"]
    assert all(not r["question_masked"].startswith("=") for r in rows)
    for forbidden in (HASH, "channel_user_hash", "session_id"):
        assert forbidden not in text.text
        assert forbidden not in str(body)


def test_wider_window_includes_older_checks(app: FastAPI) -> None:
    body = member(app, "analyst").get(URL, params={"days": 60}).json()
    assert len(body["checks"]) == 11


def test_other_roles_and_anonymous_are_refused(app: FastAPI) -> None:
    for role in ("moderator", None):
        assert member(app, role).get(URL).status_code == 403
    assert TestClient(app).get(URL).status_code == 401


def test_unknown_format_is_a_validation_error(app: FastAPI) -> None:
    assert member(app, "analyst").get(URL, params={"format": "xml"}).status_code == 422


def test_export_requires_a_shorter_window_above_the_record_limit(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(export_api, "MAX_EXPORT_CHECKS", 9)

    response = member(app, "analyst").get(URL)

    assert response.status_code == 422
    assert response.json()["detail"] == "too many checks to export; reduce days"
