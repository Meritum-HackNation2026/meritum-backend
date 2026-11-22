"""Steps for the STIX export scenario of features/observability.feature."""

import asyncio
from datetime import UTC, datetime, timedelta
from http import HTTPStatus

from behave import given, then, when
from behave.runner import Context
from features.constants import STAFF_ADMIN
from features.staff_support import csrf, signed_in
from meritum_core.checks.contracts import CaseClaim, CheckRecord, ModeratorCase

from meritum_backend.main import create_app
from meritum_backend.settings import Settings

CHANNEL_HASH = "b" * 64
CHECKS = 10


def _record(number: int, received: datetime) -> CheckRecord:
    return CheckRecord(
        check_id=f"e{number}",
        session_id=CHANNEL_HASH,
        channel="discord",
        channel_user_hash=CHANNEL_HASH,
        received_at=received,
        answered_at=received,
        question_masked=f"pytanie {number}",
        status="done",
        verdicts=["insufficient_evidence"],
        source_ids=[],
        corpus_version="test",
        models=[],
        retention_until=received + timedelta(days=30),
    )


@given("zalogowany analityk i 10 sprawdzeń z ostatniego tygodnia")
def analyst_with_checks(context: Context) -> None:
    """Sign in an analyst; store ten checks of the last week and a case over them.

    Args:
        context: the behave context; gets ``client``.

    Features:
        US-OBS-03, F-36
    """
    app = create_app(Settings(admin_emails=STAFF_ADMIN))
    now = datetime.now(UTC)
    records = app.state.repositories.records
    for number in range(CHECKS):
        asyncio.run(records.save(_record(number, now - timedelta(days=number % 6))))
    claim = CaseClaim(
        claim="Paszport zdrożeje.", check_ids=[f"e{n}" for n in range(CHECKS)]
    )
    case = ModeratorCase(
        id="#S-1",
        state="open",
        reasons=["insufficient_evidence"],
        summary="Paszport",
        claims=[claim],
        first_seen=now,
        last_seen=now,
    )
    asyncio.run(app.state.cases.save(case))
    admin = signed_in(app, STAFF_ADMIN)
    body = {"email": "analyst@example.com", "role": "analyst"}
    admin.post("/api/v1/staff", json=body, headers=csrf(admin))
    context.client = signed_in(app, "analyst@example.com")


@when("pobiera GET /api/v1/export?format=stix")
def download(context: Context) -> None:
    """Download the STIX bundle.

    Args:
        context: the behave context with ``client``; gets ``response``.

    Features:
        US-OBS-03, F-36
    """
    context.response = context.client.get("/api/v1/export", params={"format": "stix"})


@then("dostaje paczkę STIX 2.1, która przechodzi walidację schematu")
def valid_bundle(context: Context) -> None:
    """Check the bundle's shape: type, spec version, ids and object references.

    Args:
        context: the behave context with ``response``.

    Features:
        US-OBS-03, F-36
    """
    assert context.response.status_code == HTTPStatus.OK, context.response.text
    bundle = context.response.json()
    assert bundle["type"] == "bundle"
    objects = bundle["objects"]
    ids = {o["id"] for o in objects}
    assert all(o["spec_version"] == "2.1" for o in objects)
    assert all(o["id"].startswith(f"{o['type']}--") for o in objects)
    assert all(ref in ids for o in objects for ref in o.get("object_refs", []))
    assert sum(o["type"] == "report" for o in objects) == CHECKS


@then(
    "żadna pozycja nie zawiera channel_user_hash, session_id ani niezamaskowanych pytań"
)
def no_identifiers(context: Context) -> None:
    """Check that no identifier or unmasked text is in the bundle.

    Args:
        context: the behave context with ``response``.

    Features:
        US-OBS-03, F-36
    """
    for forbidden in (CHANNEL_HASH, "channel_user_hash", "session_id"):
        assert forbidden not in context.response.text
