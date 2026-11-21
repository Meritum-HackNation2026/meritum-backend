"""Steps for the counter-key scenario of features/security.feature (backend#66).

The app runs on an in-memory counter that, like the PostgreSQL table, drops the
keys of a finished window; the table itself is checked by the integration test.
"""

import hashlib
import hmac

from behave import given, then, when
from behave.runner import Context
from fastapi.testclient import TestClient
from meritum_core.jobs.fakes import InMemoryJobQueue
from pydantic import SecretStr

from meritum_backend.checks.constants import SESSION_HEADER
from meritum_backend.jobs.api import get_jobs
from meritum_backend.limits import CheckGate, LimitSettings, get_check_gate
from meritum_backend.limits.adapters import FixedPendingChecks, MemoryRateCounter
from meritum_backend.main import create_app
from meritum_backend.settings import Settings

_SECRET = "sekret-tylko-do-testu"  # ruff: ignore[hardcoded-password-string] -- test value, not a deploy secret
_IP = "203.0.113.7"
_LATER_IP = "198.51.100.1"
_WINDOW = 60.0


@given("żądanie z adresu IP")
def request_from_ip(context: Context) -> None:
    """An app whose counter key secret comes from the settings (the deploy secret).

    Args:
        context: the behave context; gets ``app``, ``client``, ``counter``, ``now``.

    Features:
        US-BEZ-02, F-20
    """
    context.now = [0.0]
    context.counter = MemoryRateCounter(clock=lambda: context.now[0])
    limits = LimitSettings(channel_hash_salt=SecretStr(_SECRET))
    gate = CheckGate(context.counter, FixedPendingChecks(), limits)
    app = create_app(Settings(database_url="postgresql://x:x@127.0.0.1:1/x"))
    jobs = InMemoryJobQueue()
    app.dependency_overrides[get_jobs] = lambda: jobs
    app.dependency_overrides[get_check_gate] = lambda: gate
    context.app = app
    context.client = TestClient(app, client=(_IP, 50000))


@when("licznik limitu zapisuje klucz")
def counter_writes_key(context: Context) -> None:
    """Send one check through POST /api/v1/checks.

    Args:
        context: the behave context with ``client``.

    Features:
        US-BEZ-02, F-20
    """
    body = {"channel": "web", "text": "Czy szczepionki powodują autyzm?"}
    headers = {SESSION_HEADER: "session-0123456789"}
    response = context.client.post("/api/v1/checks", json=body, headers=headers)
    assert response.is_success


@then(
    "klucz to HMAC-SHA256 adresu z tajnym kluczem z sekretów,"
    " a wiersze znikają po zakończeniu okna limitu"
)
def hmac_key_until_window_ends(context: Context) -> None:
    """The stored address key is the HMAC; the next window holds none of it.

    Args:
        context: the behave context with ``counter`` and ``now``.

    Features:
        US-BEZ-02, F-20
    """
    message = f"ip:{_IP}".encode()
    digest = hmac.new(_SECRET.encode(), message, hashlib.sha256).hexdigest()
    assert f"ip:{digest}" in context.counter.keys
    assert hashlib.sha256(_IP.encode()).hexdigest() not in str(context.counter.keys)
    context.now[0] += _WINDOW
    context.client = TestClient(context.app, client=(_LATER_IP, 50000))
    counter_writes_key(context)
    assert f"ip:{digest}" not in context.counter.keys
