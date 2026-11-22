from datetime import UTC, date, datetime

from meritum_core.checks import CheckResult
from meritum_core.checks.contracts import (
    AiMarker,
    Citation,
    ClaimResult,
    Escalation,
    EvidenceStrength,
    Premises,
    Source,
)

from meritum_backend.discord import MESSAGE_MAX_CHARS, reply_messages, split_text

CARD = "https://meritum.example/sprawdzenie/c1"
CLAIM = "Wrocław był jedynym miastem z darmową komunikacją dla 65-latków."


_PREMISES = Premises(
    independent_sources=1,
    primary_sources=1,
    newest_source_published_at=datetime(2025, 3, 1, tzinfo=UTC),
    newest_source_age_hours=10,
    max_age_hours=100,
    agreement="consistent",
)


def _claim(
    fragment: str = "Bezpłatne przejazdy przysługują osobom od 65 lat.",
) -> ClaimResult:
    source = Source(
        id="s1",
        title="Uchwała rady miasta",
        publisher="Urząd Miasta Wrocławia",
        publisher_id="umw",
        url="https://wroclaw.pl/uchwala",
        domain="wroclaw.pl",
        kind="akt_prawny",
        tier="primary",
        published_at=datetime(2025, 3, 1, tzinfo=UTC),
        fetched_at=datetime(2026, 11, 1, tzinfo=UTC),
    )
    return ClaimResult(
        claim=CLAIM,
        claim_date=date(2026, 11, 21),
        claim_date_source="today",
        verdict="false",
        strength=EvidenceStrength(level="moderate", premises=_PREMISES),
        citations=[Citation(source=source, fragment=fragment, stance="refutes")],
        explanation="Inne miasta też mają darmowe przejazdy.",
    )


def _result(*claims: ClaimResult, escalation: Escalation | None = None) -> CheckResult:
    return CheckResult(
        check_id="c1",
        status="done",
        claims=list(claims),
        limitations=["Korpus obejmuje tylko źródła polskie."],
        limitation_codes=["corpus_scope"],
        corpus_version="test",
        ai_marker=AiMarker(
            provider="stub",
            model="stub",
            generated_at=datetime(2026, 11, 21, tzinfo=UTC),
        ),
        escalation=escalation,
    )


def test_summary_then_one_message_per_claim() -> None:
    texts = reply_messages(_result(_claim(), _claim()), CARD, first_contact=False)
    assert texts[0].startswith("Wynik sprawdzenia: 2 twierdzenia. Pełna karta: " + CARD)
    assert f"Fałszywe: {CLAIM}" in texts[0]
    assert len(texts) == 3
    assert texts[1] == (
        f"Fałszywe: {CLAIM}\n„Bezpłatne przejazdy przysługują osobom od 65 lat.”"
        " (Urząd Miasta Wrocławia, 01.03.2025)\nSiła podstawy: Umiarkowana"
    )


def test_first_contact_starts_with_ai_notice() -> None:
    texts = reply_messages(_result(_claim()), CARD, first_contact=True)
    assert texts[0].startswith("Jestem botem Meritum, systemem AI.")
    assert "1 twierdzenie." in texts[0]


def test_case_number_only_for_created_or_updated_escalation() -> None:
    created = Escalation(state="created", case_id="#S-7")
    recommended = Escalation(state="recommended")
    with_case = reply_messages(
        _result(_claim(), escalation=created), CARD, first_contact=False
    )
    without = reply_messages(
        _result(_claim(), escalation=recommended), CARD, first_contact=False
    )
    assert "#S-7" in with_case[0]
    assert "#S-" not in "".join(without)


def test_no_result_gives_failure_text() -> None:
    assert reply_messages(None, CARD, first_contact=False) == [
        "Nie udało się sprawdzić. To nie jest ocena. Spróbuj później."
    ]


def test_split_keeps_lines_whole_and_under_limit() -> None:
    quote = "„" + "a" * 590 + "”"
    text = "\n".join([quote] * 10)
    parts = split_text(text)
    assert all(len(part) <= MESSAGE_MAX_CHARS for part in parts)
    assert all(line == quote for part in parts for line in part.split("\n"))


def test_split_cuts_a_line_longer_than_a_message() -> None:
    parts = split_text("x" * 4500)
    assert [len(p) for p in parts] == [2000, 2000, 500]


def test_result_without_claims_still_links_the_card() -> None:
    empty = CheckResult(
        check_id="c1",
        status="out_of_scope",
        message="To nie jest twierdzenie o faktach.",
        corpus_version="test",
    )
    texts = reply_messages(empty, CARD, first_contact=False)
    summary = f"Wynik sprawdzenia: 0 twierdzeń. Pełna karta: {CARD}"
    assert texts == [summary + "\nTo nie jest twierdzenie o faktach."]
