from datetime import UTC, date, datetime
from typing import Any

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
from tests.discord.fakes import flat

from meritum_backend.channels.constants import STATUS_HINTS
from meritum_backend.discord import reply_message

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


def _size(message: dict[str, Any]) -> int:
    (embed,) = message["embeds"]
    fields = sum(len(f["name"]) + len(f["value"]) for f in embed["fields"])
    return len(embed["title"]) + len(embed.get("description", "")) + fields


def test_one_message_with_a_field_per_claim_and_a_card_button() -> None:
    message = reply_message(_result(_claim(), _claim()), CARD, first_contact=False)
    (embed,) = message["embeds"]
    assert embed["title"] == "Wynik sprawdzenia: 2 twierdzenia"
    assert embed["color"] == 0xC8213A  # false: design-system --scam
    assert embed["fields"][0] == {
        "name": f"Fałszywe: {CLAIM}",
        "value": "„Bezpłatne przejazdy przysługują osobom od 65 lat.”"
        " (Urząd Miasta Wrocławia, 01.03.2025)\nSiła podstawy: Umiarkowana",
    }
    assert len(embed["fields"]) == 2
    assert "content" not in message
    assert message["components"] == [
        {
            "type": 1,
            "components": [
                {"type": 2, "style": 5, "label": "Pełna karta", "url": CARD}
            ],
        }
    ]
    assert CARD not in flat(message)


def test_first_contact_puts_the_ai_notice_in_the_content() -> None:
    message = reply_message(_result(_claim()), CARD, first_contact=True)
    assert message["content"].startswith("Jestem botem Meritum, systemem AI.")
    assert message["embeds"][0]["title"] == "Wynik sprawdzenia: 1 twierdzenie"


def test_case_number_only_for_created_or_updated_escalation() -> None:
    created = Escalation(state="created", case_id="#S-7")
    recommended = Escalation(state="recommended")
    with_case = reply_message(
        _result(_claim(), escalation=created), CARD, first_contact=False
    )
    without = reply_message(
        _result(_claim(), escalation=recommended), CARD, first_contact=False
    )
    assert "#S-7" in flat(with_case)
    assert "#S-" not in flat(without)


def test_no_result_gives_failure_text_without_a_card() -> None:
    assert reply_message(None, CARD, first_contact=False) == {
        "content": "Nie udało się sprawdzić. To nie jest ocena. Spróbuj później."
    }


def test_long_result_shortens_quotes_and_keeps_every_claim() -> None:
    fragment = "x" * 600
    claims = [_claim(fragment) for _ in range(12)]
    message = reply_message(_result(*claims), CARD, first_contact=True)
    (embed,) = message["embeds"]
    assert _size(message) <= 6000
    assert len(embed["fields"]) == 12
    assert all(f["name"].startswith("Fałszywe: ") for f in embed["fields"])
    assert all(len(f["value"]) <= 1024 for f in embed["fields"])
    assert "…" in embed["fields"][0]["value"]
    assert "Urząd Miasta Wrocławia" in embed["fields"][0]["value"]


def test_no_more_than_25_fields() -> None:
    message = reply_message(
        _result(*[_claim() for _ in range(30)]), CARD, first_contact=False
    )
    assert len(message["embeds"][0]["fields"]) == 25


def test_result_without_claims_still_has_the_card_button() -> None:
    empty = CheckResult(
        check_id="c1",
        status="out_of_scope",
        message="To nie jest twierdzenie o faktach.",
        corpus_version="test",
    )
    message = reply_message(empty, CARD, first_contact=False)
    (embed,) = message["embeds"]
    assert embed["title"] == "Wynik sprawdzenia: 0 twierdzeń"
    assert embed["description"] == STATUS_HINTS["out_of_scope"]
    assert embed["fields"] == []
    assert message["components"][0]["components"][0]["url"] == CARD
