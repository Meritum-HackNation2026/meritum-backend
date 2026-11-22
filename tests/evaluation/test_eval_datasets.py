"""Case files: accepted formats, refused files, running on an uploaded set."""

import pytest
from fastapi import FastAPI
from tests.evaluation.fakes import CSV_HEAD, Queue, csv_file, member


def test_uploaded_set_runs_as_a_user_file(app: FastAPI, queue: Queue) -> None:
    client = member(app, "analyst")
    upload = client.post(
        "/api/v1/eval/datasets", files={"file": ("cases.csv", csv_file())}
    )
    assert upload.status_code == 201
    assert upload.json()["cases"] == 30
    run = client.post("/api/v1/eval/runs", json={"dataset": upload.json()["id"]})
    assert run.status_code == 202
    payload = queue.enqueued[0].payload
    assert (payload.case_set, payload.case_file) == ("user_file", "cases.csv")  # ty: ignore[missing-attribute]
    assert payload.dataset_blob_id is not None  # ty: ignore[missing-attribute]
    assert str(payload.dataset_blob_id).startswith("dataset_")  # ty: ignore[missing-attribute]


def test_json_upload_is_accepted(app: FastAPI) -> None:
    body = (
        "["
        + ",".join(
            f'{{"case_id":"c{i}","scenario":"B","text":"t","expected":"confirmed"}}'
            for i in range(30)
        )
        + "]"
    ).encode()
    response = member(app, "analyst").post(
        "/api/v1/eval/datasets", files={"file": ("cases.json", body)}
    )
    assert response.status_code == 201


@pytest.mark.parametrize(
    "data",
    [
        csv_file(29),
        b"a,b\n1,2\n",
        (CSV_HEAD + "c1,Z,t,false\n" * 30).encode(),
        (CSV_HEAD + "c1,A,t,false\n" * 30).encode(),
        b"\xff\xfe",
    ],
    ids=["too few", "bad header", "bad scenario", "repeated id", "not utf-8"],
)
def test_bad_case_file_is_refused(app: FastAPI, data: bytes) -> None:
    response = member(app, "analyst").post(
        "/api/v1/eval/datasets", files={"file": ("cases.csv", data)}
    )
    assert response.status_code == 422
