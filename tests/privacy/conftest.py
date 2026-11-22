"""Fixtures of the privacy tests: four people's checks in the app repositories.

``c_s`` belongs to the browser session, ``c_o`` to another session, ``c_u`` to a
signed-in account and ``c_d`` to a Discord user (salted hash); one moderator
case holds ``c_s``, ``c_o`` and ``c_d``.
"""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from meritum_core.checks import SubjectKind
from meritum_core.checks.contracts import CheckRecord, ModeratorCase, Notification
from meritum_core.observability import AppRepositories, build_app_repositories
from meritum_core.shared.database import DatabaseSettings

T0 = datetime(2026, 11, 21, 12, tzinfo=UTC)
SESSION = "0b6f3c1e-5d2a-4f7b-9c8e-1a2b3c4d5e6f"
OTHER = "9f8e7d6c-5b4a-4321-8fed-cba987654321"
USER = "google:1234567890"
HASH = "b" * 64
ALL = frozenset({"c_s", "c_o", "c_u", "c_d"})

type Seed = Callable[[AppRepositories], None]
type Remaining = Callable[[AppRepositories], set[str]]


def _record(
    check_id: str,
    session_id: str,
    user_id: str | None = None,
    hashed: str | None = None,
) -> CheckRecord:
    return CheckRecord(
        check_id=check_id,
        session_id=session_id,
        user_id=user_id,
        channel="web" if hashed is None else "discord",
        channel_user_hash=hashed,
        received_at=T0,
        answered_at=T0,
        question_masked="Czy we Włoszech był strajk generalny?",
        status="done",
        verdicts=["confirmed"],
        source_ids=[],
        corpus_version="2026-11-21.1",
        models=[],
        retention_until=T0 + timedelta(days=30),
    )


def _note(
    note_id: str, check_id: str, session_id: str | None, user_id: str | None
) -> Notification:
    return Notification(
        id=note_id,
        kind="check_done",
        session_id=session_id,
        user_id=user_id,
        check_id=check_id,
        link=f"/sprawdzenia/{check_id}",
        created_at=T0,
        retention_until=T0 + timedelta(days=30),
    )


async def _seed(repos: AppRepositories) -> None:
    await repos.records.save(_record("c_s", SESSION))
    await repos.records.save(_record("c_o", OTHER))
    await repos.records.save(_record("c_u", OTHER, user_id=USER))
    await repos.records.save(_record("c_d", HASH, hashed=HASH))
    await repos.notifications.save(_note("n_s", "c_s", SESSION, None))
    await repos.notifications.save(_note("n_u", "c_u", None, USER))
    await repos.cases.save(
        ModeratorCase.model_validate(
            {
                "id": "#S-1",
                "state": "open",
                "reasons": ["insufficient_evidence"],
                "summary": "Strajk.",
                "claims": [{"claim": "Strajk.", "check_ids": ["c_s", "c_o", "c_d"]}],
                "first_seen": T0,
                "last_seen": T0,
            }
        )
    )


async def _remaining(repos: AppRepositories) -> set[str]:
    kinds: list[tuple[SubjectKind, str]] = [
        ("session_id", SESSION),
        ("session_id", OTHER),
        ("session_id", HASH),
    ]
    return {r.check_id for k, v in kinds for r in await repos.records.list_for(k, v)}


@pytest.fixture
def seed() -> Seed:
    return lambda repos: asyncio.run(_seed(repos))


@pytest.fixture
def remaining() -> Remaining:
    return lambda repos: asyncio.run(_remaining(repos))


@pytest.fixture
def repos(seed: Seed) -> AppRepositories:
    built = build_app_repositories(DatabaseSettings())
    seed(built)
    return built
