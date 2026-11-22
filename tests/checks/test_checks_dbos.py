"""API → DBOS: a check lands in the worker's queue (local only, -m integration).

Needs ``docker compose up -d --wait db`` and the worker started once (it creates
the DBOS system tables in ``worker_local``); with the worker running, the check
also gets steps and a result.
"""

import pytest
from fastapi.testclient import TestClient

from meritum_backend.checks.constants import SESSION_HEADER
from meritum_backend.main import create_app


@pytest.mark.integration
def test_check_is_enqueued_in_dbos() -> None:
    with TestClient(create_app()) as client:
        body = {"channel": "web", "text": "Czy we Włoszech był strajk generalny?"}
        headers = {SESSION_HEADER: "session-integration-1"}
        response = client.post("/api/v1/checks", json=body, headers=headers)
        assert response.status_code == 202
        status = client.get(f"/api/v1/checks/{response.json()['check_id']}")
        assert status.status_code == 200
        assert status.json()["steps"]
