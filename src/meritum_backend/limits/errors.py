"""Errors of the limits slice.

Features:
    US-BEZ-02, F-20
"""

from meritum_backend.limits.models import Refusal


class CheckRefusedError(Exception):
    """A request over a limit, raised where a route cannot return a response.

    Args:
        refusal: why the request is refused.

    Features:
        US-BEZ-02, F-20
    """

    def __init__(self, refusal: Refusal) -> None:
        super().__init__(refusal.message_key)
        self.refusal = refusal
