"""Discord reply to a check: one embed with a field per claim and a card button.

Shared by the interactions endpoint and the Gateway process (backend#28). The
embed stays within Discord's limits (6000 characters, 25 fields): when it would
not fit, quotes are shortened, never claims. The link to the full card is a
link button, so no raw URL sits in the text.

Features:
    US-WTY-06, US-BEZ-07, F-03, F-21
"""

from typing import Any

from meritum_core.checks import CheckResult
from meritum_core.checks.contracts import ClaimResult

from meritum_backend.discord.constants import (
    AI_NOTICE,
    CARD_BUTTON,
    CLAIM_REVIEW,
    CLAIMS_PLURAL,
    DATE_FORMAT,
    ESCALATION,
    FAILURE_TEXT,
    QUOTE,
    RESULT_TITLE,
    STRENGTH,
    STRENGTH_LINE,
    SUMMARY_LINE,
    TRANSCRIPT,
    TRANSCRIPT_HINT,
    UNDATED,
    VERDICTS,
)
from meritum_backend.discord.messages.constants import (
    BUTTON_LINK,
    COLOR_MUTED,
    DESCRIPTION_MAX_CHARS,
    EMBED_MAX_CHARS,
    EMPTY_FIELD,
    FIELD_NAME_MAX_CHARS,
    FIELD_VALUE_MAX_CHARS,
    FIELDS_MAX,
    FRAGMENT_LIMITS,
    VERDICT_COLORS,
)

Message = dict[str, Any]
"""A Discord message body: ``content``, ``embeds`` and ``components`` (JSON)."""


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: max(limit - 1, 0)] + "…"


def _plural(count: int) -> str:
    if count == 1:
        form = "one"
    elif count % 10 in {2, 3, 4} and count % 100 not in {12, 13, 14}:
        form = "few"
    else:
        form = "many"
    return CLAIMS_PLURAL[form].format(count=count)


def _evidence(claim: ClaimResult, fragment_limit: int) -> str | None:
    if claim.citations:
        cited = claim.citations[0]
        published = cited.source.published_at
        when = published.strftime(DATE_FORMAT) if published else UNDATED
        return QUOTE.format(
            fragment=_cut(cited.fragment, fragment_limit),
            publisher=cited.source.publisher,
            date=when,
        )
    if claim.claim_review_premises:
        review = claim.claim_review_premises[0]
        return CLAIM_REVIEW.format(
            publisher=review.publisher, rating=review.rating, url=review.url
        )
    return claim.unresolved


def _field(claim: ClaimResult, fragment_limit: int) -> dict[str, str]:
    lines = []
    if (evidence := _evidence(claim, fragment_limit)) is not None:
        lines.append(evidence)
    if claim.strength is not None:
        lines.append(STRENGTH_LINE.format(strength=STRENGTH[claim.strength.level]))
    name = SUMMARY_LINE.format(verdict=VERDICTS[claim.verdict], claim=claim.claim)
    return {
        "name": _cut(name, FIELD_NAME_MAX_CHARS),
        "value": _cut("\n".join(lines) or EMPTY_FIELD, FIELD_VALUE_MAX_CHARS),
    }


def _description(result: CheckResult) -> str:
    lines = []
    if result.transcript is not None and result.transcript.strip():
        lines.extend([TRANSCRIPT.format(text=result.transcript), TRANSCRIPT_HINT])
    if result.message is not None:
        lines.append(result.message)
    escalation = result.escalation
    if escalation is not None and escalation.case_id is not None:
        text = ESCALATION.get(escalation.state)
        if text is not None:
            lines.append(text.format(case=escalation.case_id))
    return _cut("\n".join(lines), DESCRIPTION_MAX_CHARS)


def _size(embed: dict[str, Any]) -> int:
    fields = sum(len(f["name"]) + len(f["value"]) for f in embed["fields"])
    return len(embed["title"]) + len(embed.get("description", "")) + fields


def _color(result: CheckResult) -> int:
    verdicts = {claim.verdict for claim in result.claims}
    return next((c for v, c in VERDICT_COLORS.items() if v in verdicts), COLOR_MUTED)


def _embed(result: CheckResult) -> dict[str, Any]:
    claims = result.claims[:FIELDS_MAX]
    embed: dict[str, Any] = {
        "title": RESULT_TITLE.format(claims=_plural(len(result.claims))),
        "color": _color(result),
    }
    if description := _description(result):
        embed["description"] = description
    for limit in FRAGMENT_LIMITS:
        embed["fields"] = [_field(claim, limit) for claim in claims]
        if _size(embed) <= EMBED_MAX_CHARS:
            break
    return embed


def reply_message(
    result: CheckResult | None, card_url: str, *, first_contact: bool
) -> Message:
    """The one Discord message answering a check.

    Args:
        result: the finished check's result; None when it did not finish in time.
        card_url: the full result card in the web app.
        first_contact: the user hash has no earlier checks: the AI notice goes first.

    Returns:
        An embed with a field per claim (verdict, claim, quote, strength) and a
        link button to the card; a plain failure text when there is no result.

    Features:
        US-WTY-06, US-BEZ-07, F-03, F-21
    """
    content = [AI_NOTICE] if first_contact else []
    if result is None:
        return {"content": "\n".join([*content, FAILURE_TEXT])}
    button = {"type": 2, "style": BUTTON_LINK, "label": CARD_BUTTON, "url": card_url}
    message: Message = {
        "embeds": [_embed(result)],
        "components": [{"type": 1, "components": [button]}],
    }
    if content:
        message["content"] = content[0]
    return message
