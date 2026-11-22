"""Channels word a result without verdicts from copy, never from its message.

Features:
    US-WTY-06, US-WTY-07, F-21, backend#141
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest
from meritum_core.checks import CheckResult
from meritum_core.checks.contracts import AiMarker

from meritum_backend.channels import non_verdict_text
from meritum_backend.channels.constants import (
    FAILURE_CODES,
    OUT_OF_SCOPE_CODES,
    STATUS_HINTS,
)
from meritum_backend.discord import reply_message
from meritum_backend.sms.replies import reply_texts

COPY = Path(__file__).resolve().parents[2] / "copy" / "pl.json"
INTERNAL = "Claim extraction found no claims."
NO_CLAIMS = "Nie wiemy, które twierdzenie sprawdzić. Napisz je jednym zdaniem."


def _result(status: str = "needs_clarification", **codes: str) -> CheckResult:
    return CheckResult.model_validate(
        {
            "check_id": "c1",
            "status": status,
            "message": INTERNAL,
            "corpus_version": "test",
            "ai_marker": AiMarker(
                provider="stub",
                model="stub",
                generated_at=datetime(2026, 11, 22, tzinfo=UTC),
            ),
            **codes,
        }
    )


def test_no_claims_gets_the_copy_hint_and_the_message_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO):
        assert non_verdict_text(_result()) == NO_CLAIMS
    assert INTERNAL in caplog.text


def test_codes_pick_their_own_copy() -> None:
    failed = non_verdict_text(
        _result("technical_failure", failure_code="url_unavailable")
    )
    assert failed is not None
    assert failed.startswith("Nie udało się otworzyć strony z linku")
    scope = non_verdict_text(
        _result("out_of_scope", out_of_scope_code="not_informational")
    )
    assert scope is not None
    assert scope.startswith("Nie widzimy tu twierdzenia")


def test_discord_never_shows_the_internal_message() -> None:
    message = reply_message(_result(), "https://x/c1", first_contact=False)
    description = message["embeds"][0]["description"]
    assert INTERNAL not in description
    assert NO_CLAIMS in description


def test_sms_says_what_to_do_instead_of_a_failure() -> None:
    assert reply_texts(_result(), first_contact=False, gsm7=False) == [NO_CLAIMS]


def test_texts_match_the_synced_copy() -> None:
    copy = json.loads(COPY.read_text(encoding="utf-8"))
    for section, texts in (
        ("status_hint", STATUS_HINTS),
        ("out_of_scope_code", OUT_OF_SCOPE_CODES),
        ("failure_code", FAILURE_CODES),
    ):
        for key, text in texts.items():
            assert copy[section][key] == text, f"{section}.{key}"
