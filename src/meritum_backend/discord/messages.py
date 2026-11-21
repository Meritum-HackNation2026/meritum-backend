"""Discord replies to a check: a summary with the card link, then one per claim.

Shared by the interactions endpoint and the Gateway process (backend#28). Every
text stays within MESSAGE_MAX_CHARS and is split only between lines, so a quote
(one line, at most 600 characters) is never cut. Replies carry no embeds, so the
6000-character embed limit is never reached.

Features:
    US-WTY-06, US-BEZ-07, F-03, F-21
"""

from meritum_core.checks import CheckResult
from meritum_core.checks.contracts import ClaimResult

from meritum_backend.discord.constants import (
    AI_NOTICE,
    CLAIM_REVIEW,
    CLAIMS_PLURAL,
    DATE_FORMAT,
    ESCALATION,
    FAILURE_TEXT,
    MESSAGE_MAX_CHARS,
    QUOTE,
    STRENGTH,
    STRENGTH_LINE,
    SUMMARY,
    SUMMARY_LINE,
    UNDATED,
    VERDICTS,
)


def _plural(count: int) -> str:
    if count == 1:
        form = "one"
    elif count % 10 in {2, 3, 4} and count % 100 not in {12, 13, 14}:
        form = "few"
    else:
        form = "many"
    return CLAIMS_PLURAL[form].format(count=count)


def _evidence(claim: ClaimResult) -> str | None:
    if claim.citations:
        cited = claim.citations[0]
        published = cited.source.published_at
        when = published.strftime(DATE_FORMAT) if published else UNDATED
        return QUOTE.format(
            fragment=cited.fragment, publisher=cited.source.publisher, date=when
        )
    if claim.claim_review_premises:
        review = claim.claim_review_premises[0]
        return CLAIM_REVIEW.format(
            publisher=review.publisher, rating=review.rating, url=review.url
        )
    return claim.unresolved


def _claim_text(claim: ClaimResult) -> str:
    lines = [SUMMARY_LINE.format(verdict=VERDICTS[claim.verdict], claim=claim.claim)]
    if (evidence := _evidence(claim)) is not None:
        lines.append(evidence)
    if claim.strength is not None:
        lines.append(STRENGTH_LINE.format(strength=STRENGTH[claim.strength.level]))
    return "\n".join(lines)


def _summary(result: CheckResult, card_url: str, *, first_contact: bool) -> str:
    lines = [AI_NOTICE] if first_contact else []
    lines.append(SUMMARY.format(claims=_plural(len(result.claims)), link=card_url))
    lines.extend(
        SUMMARY_LINE.format(verdict=VERDICTS[c.verdict], claim=c.claim)
        for c in result.claims
    )
    if result.message is not None:
        lines.append(result.message)
    escalation = result.escalation
    if escalation is not None and escalation.case_id is not None:
        text = ESCALATION.get(escalation.state)
        if text is not None:
            lines.append(text.format(case=escalation.case_id))
    return "\n".join(lines)


def split_text(text: str) -> list[str]:
    """Split a reply into Discord messages, only between lines where possible.

    Args:
        text: the reply.

    Returns:
        Messages of at most MESSAGE_MAX_CHARS each; a single line longer than
        that is cut into pieces; no reply line is that long (a quote line
            holds at most 600 + 120 characters of fragment and publisher).

    Features:
        US-WTY-06, F-03
    """
    parts: list[str] = []
    current = ""
    for line in text.split("\n"):
        pieces = [
            line[i : i + MESSAGE_MAX_CHARS]
            for i in range(0, max(len(line), 1), MESSAGE_MAX_CHARS)
        ]
        for piece in pieces:
            joined = f"{current}\n{piece}" if current else piece
            if len(joined) <= MESSAGE_MAX_CHARS:
                current = joined
                continue
            parts.append(current)
            current = piece
    parts.append(current)
    return parts


def reply_messages(
    result: CheckResult | None, card_url: str, *, first_contact: bool
) -> list[str]:
    """The Discord messages answering one check, in sending order.

    Args:
        result: the finished check's result; None when it did not finish in time.
        card_url: the full result card in the web app.
        first_contact: the user hash has no earlier checks: the AI notice goes first.

    Returns:
        The summary (with the case number only for a created or updated
        escalation), then one message per claim, each within MESSAGE_MAX_CHARS.

    Features:
        US-WTY-06, US-BEZ-07, F-03, F-21
    """
    if result is None:
        return [AI_NOTICE + "\n" + FAILURE_TEXT if first_contact else FAILURE_TEXT]
    texts = [_summary(result, card_url, first_contact=first_contact)]
    texts.extend(_claim_text(claim) for claim in result.claims)
    return [part for text in texts for part in split_text(text)]
