"""PostgreSQL evaluation index on core migration tables (eval_runs, eval_datasets)."""

from datetime import datetime
from typing import Any, cast

import psycopg
from meritum_core.checks.contracts import EvalCaseSet
from psycopg.types.json import Jsonb

from meritum_backend.evaluation.constants import (
    CONNECT_TIMEOUT,
    GET_EVAL_DATASET,
    GET_EVAL_RUN,
    INSERT_EVAL_DATASET,
    INSERT_EVAL_RUN,
    LIST_EVAL_RUNS,
)
from meritum_backend.evaluation.errors import EvalStoreUnavailableError
from meritum_backend.evaluation.models import Dataset, RunRef


def _run_index(ref: RunRef) -> dict[str, object]:
    return {
        "case_set": ref.case_set,
        "case_file": ref.case_file,
        "corpus_version": ref.corpus_version,
    }


def _ref_from_row(
    run_id: str, user_id: str | None, started_at: datetime, run: dict[str, Any]
) -> RunRef:
    return RunRef(
        run_id=run_id,
        case_set=cast("EvalCaseSet", run["case_set"]),
        case_file=run.get("case_file"),
        corpus_version=cast("str", run["corpus_version"]),
        user_id=user_id or "",
        started_at=started_at,
    )


class PostgresEvalStore:
    """Stores runs and uploaded set metadata in the API schema.

    Case file bytes live in the blob store; the worker owns full run documents in
    ``eval_runs.run`` once a workflow finishes.

    Args:
        conninfo: API database connection string.

    Features:
        US-OBS-06, US-OBS-05, F-28
    """

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    async def add_run(self, ref: RunRef) -> None:
        """Remember a run the API enqueued.

        Args:
            ref: the run reference.

        Raises:
            EvalStoreUnavailableError: the database operation failed.
        """
        try:
            async with await psycopg.AsyncConnection.connect(
                self._conninfo, connect_timeout=CONNECT_TIMEOUT
            ) as conn:
                await conn.execute(
                    INSERT_EVAL_RUN,
                    (
                        ref.run_id,
                        ref.user_id,
                        ref.started_at,
                        Jsonb(_run_index(ref)),
                    ),
                )
        except psycopg.Error:
            raise EvalStoreUnavailableError from None

    async def runs(self) -> list[RunRef]:
        """Every run the API or worker stored.

        Returns:
            The runs, newest first.

        Raises:
            EvalStoreUnavailableError: the database operation failed.
        """
        try:
            async with await psycopg.AsyncConnection.connect(
                self._conninfo, connect_timeout=CONNECT_TIMEOUT
            ) as conn:
                rows = await (await conn.execute(LIST_EVAL_RUNS)).fetchall()
        except psycopg.Error:
            raise EvalStoreUnavailableError from None
        return [
            _ref_from_row(
                run_id,
                user_id,
                started_at,
                cast("dict[str, Any]", run),
            )
            for run_id, user_id, started_at, run in rows
        ]

    async def run(self, run_id: str) -> RunRef | None:
        """One run.

        Args:
            run_id: the run id.

        Returns:
            The run, or None.

        Raises:
            EvalStoreUnavailableError: the database operation failed.
        """
        try:
            async with await psycopg.AsyncConnection.connect(
                self._conninfo, connect_timeout=CONNECT_TIMEOUT
            ) as conn:
                row = await (await conn.execute(GET_EVAL_RUN, (run_id,))).fetchone()
        except psycopg.Error:
            raise EvalStoreUnavailableError from None
        if row is None:
            return None
        run_id_col, user_id, started_at, run = row
        return _ref_from_row(
            run_id_col,
            user_id,
            started_at,
            cast("dict[str, Any]", run),
        )

    async def add_dataset(self, dataset: Dataset) -> None:
        """Persist metadata of an uploaded case set.

        Args:
            dataset: the set with its blob id and case count.

        Raises:
            EvalStoreUnavailableError: the database operation failed.
            ValueError: the dataset has no blob id.
        """
        if dataset.blob_id is None:
            msg = "a dataset row needs a blob id"
            raise ValueError(msg)
        try:
            async with await psycopg.AsyncConnection.connect(
                self._conninfo, connect_timeout=CONNECT_TIMEOUT
            ) as conn:
                await conn.execute(
                    INSERT_EVAL_DATASET,
                    (dataset.id, dataset.name, dataset.blob_id, len(dataset.cases)),
                )
        except psycopg.Error:
            raise EvalStoreUnavailableError from None

    async def dataset(self, dataset_id: str) -> Dataset | None:
        """One uploaded set.

        Args:
            dataset_id: the id the upload returned.

        Returns:
            The set metadata, or None.

        Raises:
            EvalStoreUnavailableError: the database operation failed.
        """
        try:
            async with await psycopg.AsyncConnection.connect(
                self._conninfo, connect_timeout=CONNECT_TIMEOUT
            ) as conn:
                row = await (
                    await conn.execute(GET_EVAL_DATASET, (dataset_id,))
                ).fetchone()
        except psycopg.Error:
            raise EvalStoreUnavailableError from None
        if row is None:
            return None
        ds_id, name, blob_id, _cases = row
        return Dataset(id=ds_id, name=name, blob_id=blob_id, cases=())
