from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from meritum_core.jobs.fakes import InMemoryJobQueue
from tests.conftest import MakeProbe, worker_report

from meritum_backend.health.adapters import BlobStoreConfig
from meritum_backend.health.api import get_readiness
from meritum_backend.main import create_app
from meritum_backend.settings import Settings

BLOB_VARIABLES = (
    "MERITUM_BLOB_PROVIDER",
    "MERITUM_BLOB_DIRECTORY",
    "MERITUM_BLOB_BUCKET",
)


@pytest.mark.parametrize(
    ("settings", "env", "missing"),
    [
        (Settings(env="dev"), {}, ["MERITUM_BLOB_PROVIDER"]),
        (
            Settings(env="dev"),
            {"MERITUM_BLOB_PROVIDER": "filesystem"},
            ["MERITUM_BLOB_DIRECTORY"],
        ),
        (
            Settings(env="dev"),
            {"MERITUM_BLOB_PROVIDER": "gcs"},
            ["MERITUM_BLOB_BUCKET"],
        ),
        (Settings(env="dev"), {"MERITUM_BLOB_PROVIDER": "memory"}, []),
        (Settings(env="dev", files_dir=Path("/srv/files")), {}, []),  # the volume
        (Settings(env="local"), {}, []),  # in-memory store, as the API itself uses
    ],
)
def test_health_names_the_missing_blob_store_variable(
    monkeypatch: pytest.MonkeyPatch,
    make_probe: MakeProbe,
    settings: Settings,
    env: dict[str, str],
    missing: list[str],
) -> None:
    for name in BLOB_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    probe = make_probe(
        InMemoryJobQueue(), report=worker_report(), blob=BlobStoreConfig(settings)
    )
    app = create_app(Settings())
    app.dependency_overrides[get_readiness] = lambda: probe
    assert TestClient(app).get("/api/v1/health").json()["missing_env"] == missing
