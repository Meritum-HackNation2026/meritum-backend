"""422 answers of the checks API: a copy key, never the sent input.

Features:
    US-SPR-01, US-SPR-07, US-BEZ-04, F-01, F-20
"""

from collections.abc import Callable, Coroutine
from typing import Any, cast, override

from fastapi import Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel
from pydantic_core import ErrorDetails

from meritum_backend.checks.intake import message_key


class InvalidCheck(BaseModel):
    """422 answer: what the person must fix, as a key of copy/pl.json.

    Attributes:
        message_key: errors.empty, errors.too_long or errors.invalid_url.

    Features:
        US-SPR-01, US-SPR-07, F-01
    """

    message_key: str


def invalid(key: str) -> JSONResponse:
    """Answer 422 with a copy key.

    Args:
        key: a key of copy/pl.json.

    Returns:
        The 422 response with InvalidCheck.

    Features:
        US-SPR-01, US-SPR-07, F-01
    """
    body = InvalidCheck(message_key=key).model_dump()
    return JSONResponse(body, status_code=status.HTTP_422_UNPROCESSABLE_CONTENT)


class KeyedErrorsRoute(APIRoute):
    """Route that answers a bad body with a copy key, never echoing the input.

    FastAPI's default 422 repeats the sent text, which may hold personal data.

    Features:
        US-SPR-01, US-BEZ-04, F-01, F-20
    """

    @override
    # Any: the exact signature of APIRoute.get_route_handler (Starlette types).
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        """Wrap the default handler.

        Returns:
            The handler that maps validation errors to InvalidCheck.
        """
        handler = super().get_route_handler()

        async def keyed(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError as exc:
                return invalid(message_key(cast("list[ErrorDetails]", exc.errors())))

        return keyed
