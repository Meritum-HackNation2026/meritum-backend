"""The app's own wiring: the lifespan builds the probe and logs the report.

Both URLs point at a closed local port, so every probe fails at once; no database.
"""

import logging
import time

import pytest
from fastapi.testclient import TestClient

from meritum_backend.main import create_app
from meritum_backend.settings import Settings

CLOSED = "postgresql://x:x@127.0.0.1:1/x"


def test_startup_logs_the_report_and_health_serves_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = create_app(Settings(database_url=CLOSED, dbos_url=CLOSED))
    with (
        caplog.at_level(logging.INFO, logger="meritum_backend"),
        TestClient(app) as client,
    ):
        body = client.get("/api/v1/health").json()
        deadline = time.monotonic() + 5
        while "not ready" not in caplog.text and time.monotonic() < deadline:
            time.sleep(0.05)
    assert (body["database"], body["worker"]) == ("unavailable", "not_reported")
    assert "MERITUM_CHANNEL_HASH_SALT" in body["missing_env"]
    assert "not ready" in caplog.text
    assert "MERITUM_CHANNEL_HASH_SALT" in caplog.text
