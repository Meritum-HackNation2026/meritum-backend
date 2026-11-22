import asyncio
from datetime import UTC, date, datetime
from typing import override

from meritum_core.checks import CheckResult
from meritum_core.checks.contracts import AiMarker, ClaimResult
from meritum_core.jobs.contracts import CheckOutput
from meritum_core.jobs.fakes import InMemoryJobQueue
from meritum_core.jobs.ports import JobState

from meritum_backend.sms.constants import (
    AI_NOTICE,
    FAILURE_TEXT,
    GSM7_PART,
    MAX_PARTS,
    UCS2_PART,
)
from meritum_backend.sms.delivery import reply_when_done
from meritum_backend.sms.replies import fit, reply_texts

from .conftest import FakeSms

RESULT = CheckResult(
    check_id="sms-dev1-e1",
    status="done",
    claims=[
        ClaimResult(
            claim="Wczoraj w Gdańsku wyłączono wszystkie bankomaty.",
            claim_date=date(2026, 11, 21),
            claim_date_source="today",
            verdict="insufficient_evidence",
            explanation="Źródła w korpusie nie opisują takiego zdarzenia.",
            unresolved="Czy bankomaty działały.",
        )
    ],
    limitations=["Korpus obejmuje tylko źródła polskie."],
    limitation_codes=["corpus_scope"],
    corpus_version="test",
    ai_marker=AiMarker(
        provider="stub", model="stub", generated_at=datetime(2026, 11, 21, tzinfo=UTC)
    ),
)


LINK = "https://meritum.example/sprawdzenie/sms-dev1-e1"


def test_reply_is_the_main_verdict_then_the_link() -> None:
    texts = reply_texts(RESULT, first_contact=False, gsm7=False, link=LINK)

    assert texts == [f"Brak wystarczających dowodów {LINK}"]


def test_first_contact_starts_with_the_ai_notice_and_the_last_text_has_the_link() -> (
    None
):
    texts = reply_texts(RESULT, first_contact=True, gsm7=False, link=LINK)

    assert texts[0] == AI_NOTICE
    assert texts[-1].endswith(LINK)


def test_failed_check_gets_the_failure_text_and_the_link() -> None:
    assert reply_texts(None, first_contact=False, gsm7=False, link=LINK) == [
        f"{FAILURE_TEXT} {LINK}"
    ]


def test_long_text_is_shortened_to_whole_sentences_within_the_parts() -> None:
    text = (
        "Pierwsze zdanie jest tu. "
        + "Drugie zdanie ma sporo słów żeby było długie. " * 6
    )

    fitted = fit(text, gsm7=False, link=LINK)

    assert fitted.endswith(LINK)
    assert len(fitted) <= UCS2_PART * MAX_PARTS
    body = fitted.removesuffix(LINK).rstrip()
    assert body.endswith(".")
    assert "Drugie zdanie ma sporo słów żeby było długie." in body


def test_one_overlong_sentence_is_cut_at_a_word_with_an_ellipsis() -> None:
    fitted = fit("słowo " * 100, gsm7=False, link=LINK)

    assert len(fitted) <= UCS2_PART * MAX_PARTS
    assert fitted.endswith(f"słowo… {LINK}")


def test_short_text_without_link_is_left_alone() -> None:
    assert fit("Fałszywe", gsm7=False) == "Fałszywe"


def test_gsm7_drops_diacritics_and_allows_three_153_parts() -> None:
    assert fit("Fałszywe źródło", gsm7=True) == "Falszywe zrodlo"
    assert len(fit("a " * 400, gsm7=True, link=LINK)) <= GSM7_PART * MAX_PARTS


class _DoneQueue(InMemoryJobQueue):
    @override
    async def state(self, workflow_id: str) -> JobState | None:
        output = CheckOutput(result=RESULT).model_dump(mode="json")
        return JobState(workflow_id=workflow_id, status="SUCCESS", output=output)


def test_reply_is_sent_once_the_check_finished() -> None:
    sms = FakeSms()

    asyncio.run(
        reply_when_done(
            _DoneQueue(),
            sms,
            "sms-dev1-e1",
            "+48600700800",
            first_contact=False,
            gsm7=False,
            link=LINK,
        )
    )

    assert sms.sent == [("+48600700800", f"Brak wystarczających dowodów {LINK}")]
