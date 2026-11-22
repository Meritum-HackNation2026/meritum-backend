"""The demo seed creates its data once and skips it on a second run."""

import importlib.util
import json
from functools import partial
from pathlib import Path
from types import ModuleType

import httpx2
import pytest

SCRIPT = Path(__file__).parents[2] / "scripts" / "seed_demo.py"
CITATION = {"source": {"id": "src-1"}, "fragment": "fragment źródła"}


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("seed_demo", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeApi:
    """Just enough of the API: checks, one case, eval runs."""

    def __init__(self) -> None:
        self.checks: dict[str, str] = {}
        self.case_state: str | None = None
        self.runs: list[str] = []
        self.posts: list[str] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:  # ruff: ignore[complex-structure, too-many-return-statements] # a route table
        path, method = request.url.path, request.method
        if method == "POST":
            self.posts.append(path)
        if path.startswith("/api/v1/auth/demo/"):
            return httpx2.Response(303, headers={"location": "/"})
        if path == "/api/v1/auth/me":
            return httpx2.Response(200, json={"csrf_token": "t"})
        if path == "/api/v1/checks" and method == "GET":
            return httpx2.Response(
                200,
                json=[
                    {"question_masked": q, "check_id": c}
                    for q, c in self.checks.items()
                ],
            )
        if path == "/api/v1/checks":
            body = json.loads(request.content)
            check_id = f"c{len(self.checks)}"
            self.checks[body.get("text") or body["url"]] = check_id
            return httpx2.Response(202, json={"check_id": check_id})
        if path.startswith("/api/v1/checks/") and path.endswith("/escalate"):
            self.case_state = "open"
            return httpx2.Response(200, json={"escalation": {"case_id": "#S-1"}})
        if path.startswith("/api/v1/checks/"):
            return httpx2.Response(
                200, json={"result": {"claims": [{"citations": [CITATION]}]}}
            )
        if path == "/api/v1/moderation/cases":
            cases = (
                []
                if self.case_state is None
                else [
                    {
                        "id": "#S-1",
                        "state": self.case_state,
                        "claims": [{"check_ids": ["c5"]}],
                    }
                ]
            )
            return httpx2.Response(200, json=cases)
        if path == "/api/v1/moderation/cases/#S-1/answer":
            self.case_state = "answered"
            return httpx2.Response(200, json={})
        if path == "/api/v1/eval/runs" and method == "POST":
            self.runs.append("r1")
            return httpx2.Response(202, json={"run_id": "r1"})
        if path == "/api/v1/eval/runs":
            return httpx2.Response(200, json=self.runs)
        return httpx2.Response(200, json=[])


def test_second_run_creates_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    api = FakeApi()
    seed = _load()
    monkeypatch.setattr(
        seed.httpx2,
        "Client",
        partial(httpx2.Client, transport=httpx2.MockTransport(api)),
    )
    monkeypatch.setenv("MERITUM_DEMO_CITIZEN_LINK", "https://x/api/v1/auth/demo/a")
    monkeypatch.setenv("MERITUM_DEMO_ADMIN_LINK", "https://x/api/v1/auth/demo/b")
    monkeypatch.setenv("MERITUM_MODERATOR_SESSION", "cookie")

    assert seed.main([]) == 0
    first = len(api.posts)
    assert len(api.checks) == len(seed.CHECKS)
    assert api.case_state == "answered"
    assert api.runs == ["r1"]

    assert seed.main([]) == 0
    assert len(api.posts) == first


def test_refuses_production() -> None:
    seed = _load()
    with pytest.raises(SystemExit):
        seed.main(["--url", "https://meritum.gburek.app"])
