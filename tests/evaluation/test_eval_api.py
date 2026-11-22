"""Evaluation API: who gets in, starting, uploading, listing, comparing."""

from typing import Any
from urllib.parse import urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from meritum_core.jobs.contracts import EVAL_RUN
from tests.evaluation.fakes import Queue, csv_file, finished, member

CALLS: dict[str, tuple[str, str, dict[str, Any]]] = {
    "start": ("POST", "/api/v1/eval/runs", {"json": {"dataset": "golden"}}),
    "list": ("GET", "/api/v1/eval/runs", {}),
    "cases": ("GET", "/api/v1/eval/runs/x/cases", {}),
    "compare": ("GET", "/api/v1/eval/runs/compare?a=x&b=y", {}),
    "upload": (
        "POST",
        "/api/v1/eval/datasets",
        {"files": {"file": ("cases.csv", csv_file())}},
    ),
}


@pytest.mark.parametrize("role", [None, "moderator"])
@pytest.mark.parametrize("call", sorted(CALLS))
def test_other_roles_are_refused(app: FastAPI, role: str | None, call: str) -> None:
    method, path, kwargs = CALLS[call]
    assert member(app, role).request(method, path, **kwargs).status_code == 403


def test_anonymous_is_refused(app: FastAPI) -> None:
    client = TestClient(app, base_url="https://testserver")
    assert client.get("/api/v1/eval/runs").status_code == 401


@pytest.mark.parametrize("role", ["analyst", "admin"])
def test_start_enqueues_eval_run_for_the_starter(
    app: FastAPI, queue: Queue, role: str
) -> None:
    response = member(app, role).post("/api/v1/eval/runs", json={"dataset": "golden"})
    assert response.status_code == 202
    job = queue.enqueued[0]
    assert job.spec == EVAL_RUN
    assert job.workflow_id == response.json()["id"]
    assert job.payload.case_set == "golden"  # ty: ignore[missing-attribute]
    assert job.payload.user_id.startswith("staff:")  # ty: ignore[missing-attribute]


def test_start_needs_a_csrf_token(app: FastAPI) -> None:
    client = member(app, "analyst")
    del client.headers["X-CSRF-Token"]
    assert (
        client.post("/api/v1/eval/runs", json={"dataset": "golden"}).status_code == 403
    )


def test_unknown_dataset_is_refused(app: FastAPI) -> None:
    response = member(app, "analyst").post("/api/v1/eval/runs", json={"dataset": "zz"})
    assert response.status_code == 422


def test_list_shows_queued_then_finished_with_measured_metrics(
    app: FastAPI, queue: Queue
) -> None:
    client = member(app, "analyst")
    run_id = client.post("/api/v1/eval/runs", json={"dataset": "golden"}).json()["id"]
    assert client.get("/api/v1/eval/runs").json()[0]["status"] == "queued"
    queue.done[run_id] = finished(run_id, 0.8, "false")
    listed = client.get("/api/v1/eval/runs").json()[0]
    assert (listed["status"], listed["dataset"]) == ("done", "golden")
    assert listed["metrics"]["macro_f1"] == pytest.approx(0.8)
    assert "citation_coverage" not in listed["metrics"]
    cases = client.get(f"/api/v1/eval/runs/{run_id}/cases").json()
    assert cases == [{"case_id": "c1", "verdict": "false"}]


def test_compare_gives_metric_pairs_and_changed_cases(
    app: FastAPI, queue: Queue
) -> None:
    client = member(app, "analyst")
    ids = [
        client.post("/api/v1/eval/runs", json={"dataset": "golden"}).json()["id"]
        for _ in range(2)
    ]
    queue.done[ids[0]] = finished(ids[0], 0.5, "confirmed")
    queue.done[ids[1]] = finished(ids[1], 0.9, "false")
    body = client.get(f"/api/v1/eval/runs/compare?a={ids[0]}&b={ids[1]}").json()
    assert body["metrics"]["macro_f1"] == {"a": 0.5, "b": 0.9}
    assert "citation_coverage" not in body["metrics"]
    assert body["changed_cases"] == [{"case_id": "c1", "a": "confirmed", "b": "false"}]


def test_unknown_run_is_404(app: FastAPI) -> None:
    assert member(app, "analyst").get("/api/v1/eval/runs/nope/cases").status_code == 404


def test_latest_is_public_and_404_until_a_golden_run_finishes(
    app: FastAPI, queue: Queue
) -> None:
    anonymous = TestClient(app, base_url="https://testserver")
    assert anonymous.get("/api/v1/eval/runs/latest").status_code == 404
    client = member(app, "analyst")
    run_id = client.post("/api/v1/eval/runs", json={"dataset": "golden"}).json()["id"]
    assert anonymous.get("/api/v1/eval/runs/latest").status_code == 404
    queue.done[run_id] = finished(run_id, 0.8, "false")
    body = anonymous.get("/api/v1/eval/runs/latest").json()
    assert body["bundle_url"].startswith("https://")
    assert body["metrics"]["macro_f1"] == pytest.approx(0.8)
    assert set(body) == {"finished_at", "bundle_url", "metrics"}


def test_jury_reads_runs_but_cannot_start_or_upload(app: FastAPI) -> None:
    url = member(app, "admin").post("/api/v1/staff/jury-links").json()["url"]
    juror = TestClient(app, base_url="https://testserver", follow_redirects=False)
    juror.post("/api/v1/auth/jury-links/redeem", json={"token": urlparse(url).fragment})
    juror.headers["X-CSRF-Token"] = juror.get("/api/v1/auth/me").json()["csrf_token"]
    assert juror.get("/api/v1/eval/runs").status_code == 200
    start = juror.post("/api/v1/eval/runs", json={"dataset": "golden"})
    upload = juror.post("/api/v1/eval/datasets", files={"file": ("c.csv", csv_file())})
    assert (start.status_code, upload.status_code) == (403, 403)
