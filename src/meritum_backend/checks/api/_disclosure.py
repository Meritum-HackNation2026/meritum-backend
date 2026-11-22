"""The AI-Disclosure header of a result, built from its AI marker.

Features:
    US-BEZ-07
"""

from meritum_core.checks import CheckResult

from meritum_backend.checks.constants import AI_DISCLOSURE_VALUE


def _sf_string(value: str) -> str:
    # shortcut: an sf-string holds printable ASCII only, so anything else is dropped;
    # model ids are ASCII today, use an RFC 9651 Display String if one is not.
    printable = "".join(c for c in value if " " <= c <= "~")
    escaped = printable.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def ai_disclosure(result: CheckResult) -> str:
    """Build the AI-Disclosure value (draft-abaris-aicdh) for ``result``.

    Args:
        result: the result the response carries.

    Returns:
        ``mode=ai-originated``, plus the model, provider and date of the result's
        AI marker when a model wrote the answer.

    Features:
        US-BEZ-07
    """
    marker = result.ai_marker
    if marker is None:
        return AI_DISCLOSURE_VALUE
    named = f"model={_sf_string(marker.model)}; provider={_sf_string(marker.provider)}"
    return (
        f"{AI_DISCLOSURE_VALUE}; {named}; date=@{int(marker.generated_at.timestamp())}"
    )
