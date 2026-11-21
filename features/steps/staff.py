"""Steps for the staff scenarios of features/moderation.feature.

Roles and the high-risk topic list through the public HTTP API; the fake login
provider stands in for Google and Microsoft, the repositories are in memory.
"""

import asyncio
from datetime import UTC, datetime
from http import HTTPStatus

from behave import given, then, when
from behave.runner import Context
from fastapi import FastAPI
from features.constants import STAFF_ADMIN, STAFF_MODERATOR
from features.staff_support import csrf, grant_moderator, signed_in
from meritum_core.checks.contracts import CaseClaim, ModeratorCase
from meritum_core.moderation import HighRiskTopic

from meritum_backend.main import create_app
from meritum_backend.settings import Settings

STRANGER = "stranger@example.com"
TOPIC = HighRiskTopic(name="wybory", keywords=["wybory", "lokal wyborczy"])
CLAIM = "Lokal wyborczy w Gdańsku będzie zamknięty w niedzielę."
NOW = datetime(2026, 11, 21, tzinfo=UTC)
CASE = ModeratorCase(
    id="#S-1",
    state="open",
    reasons=["insufficient_evidence"],
    summary="Twierdzenie bez dowodów",
    claims=[CaseClaim(claim=CLAIM, check_ids=["c_1"])],
    first_seen=NOW,
    last_seen=NOW,
)


def _app() -> FastAPI:
    """Build the app with one configured administrator and one open case.

    Returns:
        The app; its repositories live as long as it does.
    """
    app = create_app(
        Settings(
            database_url="postgresql://x:x@127.0.0.1:1/x", admin_emails=STAFF_ADMIN
        )
    )
    asyncio.run(app.state.cases.save(CASE))
    return app


@given("zalogowany administrator")
def admin_signed_in(context: Context) -> None:
    """Sign in the administrator named in the settings.

    Args:
        context: the behave context; gets ``app`` and ``admin``.

    Features:
        US-MOD-05, F-25
    """
    context.app = _app()
    context.admin = signed_in(context.app, STAFF_ADMIN)


@when('wysyła POST /api/v1/staff z adresem e-mail i rolą "moderator"')
def admin_grants_moderator(context: Context) -> None:
    """Grant the moderator role.

    Args:
        context: the behave context with ``admin``.

    Features:
        US-MOD-05, F-25
    """
    grant_moderator(context.admin)


@then("osoba może się zalogować do panelu i widzi sprawy, ale nie listę kont")
def moderator_sees_cases_only(context: Context) -> None:
    """Sign the moderator in and check what the panel shows them.

    Args:
        context: the behave context with ``app``.

    Features:
        US-MOD-05, F-25
    """
    moderator = signed_in(context.app, STAFF_MODERATOR)
    assert moderator.get("/api/v1/staff/me").json()["role"] == "moderator"
    cases = moderator.get("/api/v1/moderation/cases").json()
    assert [case["id"] for case in cases] == [CASE.id]
    assert moderator.get("/api/v1/staff").status_code == HTTPStatus.FORBIDDEN


@given("ktoś bez konta nadanego przez administratora")
def stranger(context: Context) -> None:
    """An app where the person has no staff account.

    Args:
        context: the behave context; gets ``app``.

    Features:
        US-MOD-05, F-25
    """
    context.app = _app()


@when("próbuje się zalogować do panelu")
def stranger_signs_in(context: Context) -> None:
    """Sign in with the shared OIDC login.

    Args:
        context: the behave context with ``app``; gets ``client``.

    Features:
        US-MOD-05, F-25
    """
    context.client = signed_in(context.app, STRANGER)


@then("dostaje odmowę i nie widzi żadnej sprawy")
def stranger_refused(context: Context) -> None:
    """Check that the panel refuses the person.

    Args:
        context: the behave context with ``client``.

    Features:
        US-MOD-05, F-25
    """
    client = context.client
    assert client.get("/api/v1/staff/me").status_code == HTTPStatus.FORBIDDEN
    cases = client.get("/api/v1/moderation/cases")
    assert cases.status_code == HTTPStatus.FORBIDDEN
    assert CASE.id not in cases.text


@given('administrator dodaje temat "wybory" ze słowami kluczowymi')
def admin_adds_topic(context: Context) -> None:
    """Add the topic through the admin API.

    Args:
        context: the behave context; gets ``app``.

    Features:
        US-MOD-05, F-20, F-25
    """
    context.app = _app()
    admin = signed_in(context.app, STAFF_ADMIN)
    response = admin.post(
        "/api/v1/moderation/topics", json=TOPIC.model_dump(), headers=csrf(admin)
    )
    assert response.status_code == HTTPStatus.CREATED


@when("kolejne twierdzenie bez odpowiedzi dotyczy wyborów")
def claim_about_elections(context: Context) -> None:
    """Read the list the worker's topic step reads, as it does for each claim.

    Args:
        context: the behave context with ``app``; gets ``topics``.

    Features:
        US-MOD-05, F-20
    """
    context.topics = asyncio.run(context.app.state.topics.list_topics())


@then("rozpoznawanie tematów używa nowej listy bez restartu usługi")
def topic_list_is_live(context: Context) -> None:
    """The running app's repository has the topic, and its keywords match the claim.

    Args:
        context: the behave context with ``topics``.

    Features:
        US-MOD-05, F-20
    """
    assert context.topics == [TOPIC]
    assert any(word in CLAIM.lower() for word in TOPIC.keywords)
