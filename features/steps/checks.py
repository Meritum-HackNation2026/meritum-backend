"""Steps for features/checks.feature: they call the app's public HTTP API."""

import json

from behave import given, then, when
from behave.runner import Context
from fastapi.testclient import TestClient

from meritum_backend.main import create_app
from meritum_backend.settings import Settings


@given("aplikacja zbudowana przez create_app")
def app_built(context: Context) -> None:
    """Build the app without a database; the lifespan does not run.

    Args:
        context: the behave context; gets ``client``.

    Features:
        none (infrastructure)
    """
    settings = Settings(database_url="postgresql://x:x@127.0.0.1:1/x")
    context.client = TestClient(create_app(settings))


@when("klient pyta o {path}")
def client_gets(context: Context, path: str) -> None:
    """Send a GET request.

    Args:
        context: the behave context; gets ``response``.
        path: the request path.

    Features:
        none (infrastructure)
    """
    context.response = context.client.get(path)


@then("odpowiedź ma status {status:d} i treść {body}")
def response_is(context: Context, status: int, body: str) -> None:
    """Compare the status code and the JSON body.

    Args:
        context: the behave context with ``response``.
        status: the expected status code.
        body: the expected JSON body.

    Features:
        none (infrastructure)
    """
    assert context.response.status_code == status
    assert context.response.json() == json.loads(body)
