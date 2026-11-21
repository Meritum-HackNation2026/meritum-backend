import pytest

from meritum_backend.health.factory import blob_store_problems
from meritum_backend.health.readiness import Problems


@pytest.mark.parametrize(
    ("env", "problems"),
    [
        ({}, Problems(["MERITUM_BLOB_PROVIDER"], [])),
        (
            {"MERITUM_BLOB_PROVIDER": "filesystem"},
            Problems(["MERITUM_BLOB_DIRECTORY"], []),
        ),
        ({"MERITUM_BLOB_PROVIDER": "gcs"}, Problems(["MERITUM_BLOB_BUCKET"], [])),
        ({"MERITUM_BLOB_PROVIDER": "memory"}, Problems([], [])),
    ],
)
def test_blob_store_names_the_missing_variable(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str], problems: Problems
) -> None:
    for name in (
        "MERITUM_BLOB_PROVIDER",
        "MERITUM_BLOB_DIRECTORY",
        "MERITUM_BLOB_BUCKET",
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    assert blob_store_problems() == problems
