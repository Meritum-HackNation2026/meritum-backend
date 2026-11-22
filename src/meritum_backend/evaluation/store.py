"""In-memory ``EvalStore``.

shortcut: runs and case files are lost on a restart and not shared between API
replicas; a table needs a core migration (the API role has no DDL, backend#85).
"""

from meritum_backend.evaluation.models import Dataset, RunRef


class MemoryEvalStore:
    """Keeps the index and the case files in this process.

    Features:
        US-OBS-06, US-OBS-05, F-28
    """

    def __init__(self) -> None:
        self._runs: dict[str, RunRef] = {}
        self._datasets: dict[str, Dataset] = {}

    async def add_run(self, ref: RunRef) -> None:
        """Remember a run.

        Args:
            ref: the run.
        """
        self._runs[ref.run_id] = ref

    async def runs(self) -> list[RunRef]:
        """Every run.

        Returns:
            The runs, newest first.
        """
        return sorted(self._runs.values(), key=lambda r: r.started_at, reverse=True)

    async def run(self, run_id: str) -> RunRef | None:
        """One run.

        Args:
            run_id: the run id.

        Returns:
            The run, or None.
        """
        return self._runs.get(run_id)

    async def add_dataset(self, dataset: Dataset) -> None:
        """Remember an uploaded case set.

        Args:
            dataset: the set.
        """
        self._datasets[dataset.id] = dataset

    async def dataset(self, dataset_id: str) -> Dataset | None:
        """One uploaded set.

        Args:
            dataset_id: the id the upload returned.

        Returns:
            The set, or None.
        """
        return self._datasets.get(dataset_id)
