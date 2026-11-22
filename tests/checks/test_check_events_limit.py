from dataclasses import replace
from typing import cast

from fastapi import FastAPI
from fastapi.testclient import TestClient

from meritum_backend.limits import CheckGate, get_check_gate


def limited(client: TestClient, gate: CheckGate, per_minute: int) -> TestClient:
    app = cast("FastAPI", client.app)
    limits = gate.limits.model_copy(
        update={"event_streams_per_ip_per_minute": per_minute}
    )
    app.dependency_overrides[get_check_gate] = lambda: replace(gate, limits=limits)
    return client


def test_too_many_event_streams_from_one_address_get_429(
    client: TestClient, gate: CheckGate
) -> None:
    limited(client, gate, per_minute=2)
    assert [client.get("/api/v1/checks/nope/events").status_code for _ in range(2)] == [
        404,
        404,
    ]
    response = client.get("/api/v1/checks/nope/events")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    assert response.json() == {"message_key": "errors.rate_limited"}


def test_event_streams_do_not_use_up_the_check_budget(
    client: TestClient, gate: CheckGate
) -> None:
    limited(client, gate, per_minute=100)
    for _ in range(gate.limits.checks_per_ip_per_minute + 1):
        client.get("/api/v1/checks/nope/events")
    body = {"channel": "web", "text": "Czy szczepionki powodują autyzm?"}
    headers = {"X-Meritum-Session": "session-0123456789"}
    assert client.post("/api/v1/checks", json=body, headers=headers).status_code == 202
