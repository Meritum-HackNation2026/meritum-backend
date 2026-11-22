"""Starting a run: resolve the dataset, enqueue ``eval_run``, remember the run."""

import uuid
from datetime import UTC, datetime

from meritum_core.jobs.contracts import EVAL_RUN, EvalRunInput
from meritum_core.jobs.ports import JobQueue

from meritum_backend.evaluation.constants import GOLDEN_DATASET
from meritum_backend.evaluation.models import RunRef, Started
from meritum_backend.evaluation.ports import EvalStore
from meritum_backend.notifications import staff_inbox_id
from meritum_backend.staff import StaffMember


class UnknownDatasetError(LookupError):
    """The run names a dataset that was not uploaded.

    Features:
        US-OBS-05, F-26
    """


class QueueUnavailableError(RuntimeError):
    """The worker's database cannot be reached.

    Features:
        ADR-03
    """


async def enqueue_run(
    dataset_id: str,
    member: StaffMember,
    store: EvalStore,
    jobs: JobQueue,
    corpus_version: str,
) -> Started:
    """Enqueue an evaluation run for a staff member.

    The worker ends the run with an ``eval_run_done`` notification to the member's
    staff inbox (``user_id``).

    Args:
        dataset_id: ``golden`` or an uploaded set's id.
        member: the analyst or administrator who starts it.
        store: the run index.
        jobs: the job queue port.
        corpus_version: the corpus snapshot the run pins.

    Returns:
        The run id (also the workflow id).

    Raises:
        UnknownDatasetError: ``dataset_id`` is not ``golden`` or an uploaded set.
        QueueUnavailableError: the job queue cannot be reached.

    Features:
        US-OBS-06, US-POW-05, F-28
    """
    dataset = None
    if dataset_id != GOLDEN_DATASET:
        dataset = await store.dataset(dataset_id)
        if dataset is None:
            raise UnknownDatasetError(dataset_id)
    ref = RunRef(
        run_id=uuid.uuid4().hex,
        case_set="golden" if dataset is None else "user_file",
        case_file=None if dataset is None else dataset.name,
        corpus_version=corpus_version,
        user_id=staff_inbox_id(member.email or ""),
        started_at=datetime.now(UTC),
    )
    payload = EvalRunInput(
        run_id=ref.run_id,
        case_set=ref.case_set,
        case_file=ref.case_file,
        dataset_blob_id=None if dataset is None else dataset.blob_id,
        corpus_version=ref.corpus_version,
        user_id=ref.user_id,
    )
    try:
        await jobs.enqueue(EVAL_RUN, payload, workflow_id=ref.run_id)
    except Exception as exc:  # DBOS wraps driver errors in its own types
        raise QueueUnavailableError from exc
    await store.add_run(ref)
    return Started(id=ref.run_id)
