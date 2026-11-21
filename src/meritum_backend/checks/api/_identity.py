"""Identity of a check: the browser session, or the salted channel user hash.

Features:
    US-BEZ-06, US-WTY-08, F-20
"""

from fastapi import HTTPException, status
from meritum_core.checks import SESSIONLESS_CHANNELS, CheckRequest
from pydantic import SecretStr

from meritum_backend.channels import channel_user_hash
from meritum_backend.checks.constants import NO_CHANNEL_USER_DETAIL, NO_SALT_DETAIL


def identity(
    request: CheckRequest, session: str | None, salt: SecretStr | None
) -> tuple[CheckRequest, str | None, str | None]:
    """Resolve who sends a check; Discord, SMS and MCP get their user id hashed.

    Web and extension keep their browser session. Discord, SMS and MCP have
    none: their ``channel_user_id`` is hashed and the hash is both the session id
    and ``channel_user_hash``; the raw id is cleared from the request, since
    CheckInput rejects it.

    Args:
        request: the validated request.
        session: the X-Meritum-Session header, if sent.
        salt: MERITUM_CHANNEL_HASH_SALT, if configured.

    Returns:
        The request to enqueue, the session id and the channel user hash.

    Raises:
        HTTPException: 400 for Discord, SMS or MCP without ``channel_user_id``,
            503 when they come and no salt is configured.

    Features:
        US-BEZ-06, US-WTY-08, F-20
    """
    if request.channel not in SESSIONLESS_CHANNELS:
        return request, session, None
    if request.channel_user_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, NO_CHANNEL_USER_DETAIL)
    if salt is None:  # the settings already turn an empty salt into None
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, NO_SALT_DETAIL)
    hashed = channel_user_hash(request.channel, request.channel_user_id, salt)
    return request.model_copy(update={"channel_user_id": None}), hashed, hashed
