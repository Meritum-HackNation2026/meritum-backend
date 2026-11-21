"""Check results of the Discord scenarios: claims with one cited source."""

from datetime import UTC, date, datetime

from meritum_core.checks import CheckResult
from meritum_core.checks.contracts import (
    AiMarker,
    Citation,
    ClaimResult,
    EvidenceStrength,
    Premises,
    Source,
)

_SOURCE = Source(
    id="s1",
    title="Uchwała w sprawie bezpłatnych przejazdów",
    publisher="Urząd Miasta",
    publisher_id="um",
    url="https://example.pl/uchwala",
    domain="example.pl",
    kind="akt_prawny",
    tier="primary",
    fetched_at=datetime(2026, 11, 1, tzinfo=UTC),
)
_PREMISES = Premises(
    independent_sources=1,
    primary_sources=1,
    newest_source_published_at=datetime(2025, 3, 1, tzinfo=UTC),
    newest_source_age_hours=10,
    max_age_hours=100,
    agreement="consistent",
)


def claim_result(claim: str, fragment: str) -> ClaimResult:
    """A false claim refuted by one fragment of the city's resolution.

    Args:
        claim: the claim (cut to 500 characters).
        fragment: the cited fragment.

    Returns:
        The claim result with a moderate strength.
    """
    return ClaimResult(
        claim=claim[:500],
        claim_date=date(2026, 11, 21),
        claim_date_source="today",
        verdict="false",
        strength=EvidenceStrength(level="moderate", premises=_PREMISES),
        citations=[Citation(source=_SOURCE, fragment=fragment, stance="refutes")],
        explanation="Inne miasta też mają darmowe przejazdy.",
    )


def check_result(check_id: str, claims: list[ClaimResult]) -> CheckResult:
    """A finished check with ``claims``.

    Args:
        check_id: the check id.
        claims: its claims.

    Returns:
        The result.
    """
    return CheckResult(
        check_id=check_id,
        status="done",
        claims=claims,
        limitations=["Korpus obejmuje tylko źródła polskie."],
        corpus_version="test",
        ai_marker=AiMarker(
            provider="stub",
            model="stub",
            generated_at=datetime(2026, 11, 21, tzinfo=UTC),
        ),
    )
