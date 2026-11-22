import asyncio
from datetime import UTC, date, datetime
from typing import override

from meritum_core.checks import CheckResult
from meritum_core.checks.contracts import AiMarker, ClaimResult
from meritum_core.jobs.contracts import CheckOutput
from meritum_core.jobs.fakes import InMemoryJobQueue
from meritum_core.jobs.ports import JobState

from meritum_backend.sms.constants import AI_NOTICE, FAILURE_TEXT, UCS2_LIMIT
from meritum_backend.sms.delivery import reply_when_done
from meritum_backend.sms.replies import one_sms, reply_texts

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
    corpus_version="test",
    ai_marker=AiMarker(
        provider="stub", model="stub", generated_at=datetime(2026, 11, 21, tzinfo=UTC)
    ),
)


def test_reply_is_the_main_verdict_without_a_link() -> None:
    texts = reply_texts(RESULT, first_contact=False, gsm7=False)

    assert texts == ["Brak wystarczających dowodów"]
    assert all("http" not in text for text in texts)


def test_first_contact_starts_with_the_ai_notice() -> None:
    texts = reply_texts(RESULT, first_contact=True, gsm7=False)

    assert texts[0] == AI_NOTICE
    assert all(len(text) <= UCS2_LIMIT for text in texts)


def test_failed_check_gets_the_failure_text() -> None:
    assert reply_texts(None, first_contact=False, gsm7=False) == [FAILURE_TEXT]


def test_long_text_is_cut_to_one_ucs2_sms() -> None:
    cut = one_sms("ż" * 100, gsm7=False)

    assert len(cut) == UCS2_LIMIT
    assert cut.endswith("…")


def test_gsm7_drops_diacritics_and_allows_160() -> None:
    assert one_sms("Fałszywe źródło", gsm7=True) == "Falszywe zrodlo"
    assert len(one_sms("a" * 200, gsm7=True)) == 160


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
        )
    )

    assert sms.sent == [("+48600700800", "Brak wystarczających dowodów")]
