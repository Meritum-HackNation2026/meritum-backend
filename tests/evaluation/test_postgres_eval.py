"""PostgresEvalStore on a real database (local only, -m integration).

Needs ``docker compose up -d --wait db`` (or MERITUM_TEST_DATABASE_URL); runs as
a role without DDL, like the API on dev.
"""

import asyncio
import uuid
from datetime import UTC, datetime

import pytest

from meritum_backend.evaluation.adapters import PostgresEvalStore
from meritum_backend.evaluation.models import Dataset, EvalCaseInput, RunRef

CASE = EvalCaseInput(case_id="c1", scenario="A", text="t", expected="confirmed")


@pytest.mark.integration
def test_dataset_and_run_round_trip(api_url: str) -> None:
    store = PostgresEvalStore(api_url)
    ds_id = uuid.uuid4().hex
    blob_id = "dataset_test_blob"
    started = datetime.now(UTC)

    async def round_trip() -> tuple[Dataset | None, RunRef | None]:
        await store.add_dataset(
            Dataset(id=ds_id, name="cases.csv", cases=(CASE,), blob_id=blob_id)
        )
        saved = await store.dataset(ds_id)
        ref = RunRef(
            run_id=uuid.uuid4().hex,
            case_set="user_file",
            case_file="cases.csv",
            corpus_version="v1",
            user_id="staff:analyst@example.com",
            started_at=started,
        )
        await store.add_run(ref)
        return saved, await store.run(ref.run_id)

    dataset, run_ref = asyncio.run(round_trip())
    assert dataset == Dataset(id=ds_id, name="cases.csv", blob_id=blob_id, cases=())
    assert run_ref is not None
    assert run_ref.case_set == "user_file"
    assert run_ref.corpus_version == "v1"
