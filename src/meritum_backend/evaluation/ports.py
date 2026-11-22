"""Port of the evaluation slice: what the API itself remembers about runs."""

from typing import Protocol

from meritum_backend.evaluation.models import Dataset, RunRef


class EvalStore(Protocol):
    """Remembers the runs the API enqueued and the case files it accepted.

    The results stay with the worker (the workflow output); this index only says
    which workflows are evaluation runs.

    Features:
        US-OBS-06, US-OBS-05, F-28
    """

    async def add_run(self, ref: RunRef) -> None:
        """Remember a run.

        Args:
            ref: the run.
        """
        ...

    async def runs(self) -> list[RunRef]:
        """Every run, newest first."""
        ...

    async def run(self, run_id: str) -> RunRef | None:
        """One run, or None.

        Args:
            run_id: the run id.
        """
        ...

    async def add_dataset(self, dataset: Dataset) -> None:
        """Remember an uploaded case set.

        Args:
            dataset: the set.
        """
        ...

    async def dataset(self, dataset_id: str) -> Dataset | None:
        """One uploaded set, or None.

        Args:
            dataset_id: the id the upload returned.
        """
        ...
