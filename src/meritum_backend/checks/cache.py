"""Result cache rules: the input key, what is cached and the one hit assembly.

Features:
    US-WTY-03, US-MOD-03, F-05, ADR-19, ADR-22
"""

from datetime import UTC, datetime

from meritum_core.checks import CheckRequest, CheckResult, Escalation, normalize_input
from meritum_core.checks.contracts import CachedResult, CheckRecord
from meritum_core.jobs.contracts import CheckInput

from meritum_backend.checks.constants import (
    CACHE_HIT_RETENTION,
    RESULT_CACHE_TTL,
    SUBSTANTIVE_FIELDS,
    UNANSWERED_VERDICT,
)


def input_key(request: CheckRequest) -> str | None:
    """Key a masked request the same way on every channel (core normalisation).

    Args:
        request: the masked request.

    Returns:
        The cache key; None for a recording, whose text only the worker knows.

    Features:
        US-WTY-03, F-05, ADR-19
    """
    url = None if request.url is None else str(request.url)
    text = request.text or ""
    if request.audio_id is not None or not (text or url is not None):
        return None
    return normalize_input(text, url).cache_key


def cache_entry(result: CheckResult, now: datetime) -> CachedResult | None:
    """Cut the substantive part out of a finished check's result.

    Args:
        result: the result the worker produced.
        now: when it is stored.

    Returns:
        The entry, living RESULT_CACHE_TTL; None for a technical failure.

    Features:
        US-WTY-03, F-05, ADR-22
    """
    if result.status == "technical_failure":
        return None
    cited = {c.source.id for claim in result.claims for c in claim.citations}
    fields = {name: getattr(result, name) for name in SUBSTANTIVE_FIELDS}
    extra = {"source_ids": sorted(cited), "cached_at": now}
    expires = {"expires_at": now + RESULT_CACHE_TTL}
    return CachedResult.model_validate({**fields, **extra, **expires})


def served_result(
    check_id: str, entry: CachedResult, escalation: Escalation | None
) -> CheckResult:
    """Assemble the CheckResult of a cache hit; the only place that does.

    Args:
        check_id: the new check's own id.
        entry: the cached substantive part.
        escalation: computed for this check; never the cached check's.

    Returns:
        The result the channel renders.

    Features:
        US-WTY-03, US-MOD-03, F-05, ADR-19
    """
    fields = {name: getattr(entry, name) for name in SUBSTANTIVE_FIELDS}
    own = {"check_id": check_id, "escalation": escalation}
    return CheckResult.model_validate({**fields, **own})


def unanswered(entry: CachedResult) -> list[int]:
    """List the claims with no answer; each goes to moderators on every hit.

    Args:
        entry: the cached substantive part.

    Returns:
        The claim indexes with the insufficient_evidence verdict.

    Features:
        US-MOD-03
    """
    claims = enumerate(entry.claims)
    return [i for i, claim in claims if claim.verdict == UNANSWERED_VERDICT]


def hit_record(
    check_id: str, session: str, entry: CachedResult, payload: CheckInput
) -> CheckRecord:
    """Build the audit record of a check served from the cache.

    Args:
        check_id: the new check's id.
        session: the browser session or the hashed channel user id.
        entry: the cached substantive part.
        payload: the masked request.

    Returns:
        The record with ``cache_hit`` true, no model calls.

    Features:
        US-WTY-03, US-MOD-03, F-05
    """
    request = payload.request
    question = request.text or str(request.url)
    return CheckRecord(
        check_id=check_id,
        session_id=session,
        channel=request.channel,
        channel_user_hash=payload.channel_user_hash,
        received_at=payload.received_at,
        answered_at=datetime.now(UTC),
        question_masked=question,
        status=entry.status,
        verdicts=[claim.verdict for claim in entry.claims],
        source_ids=entry.source_ids,
        corpus_version=entry.corpus_version,
        models=[],
        cache_hit=True,
        retention_until=payload.received_at + CACHE_HIT_RETENTION,
    )
