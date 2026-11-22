"""Models of the evaluation slice: case files, the run index and the answers."""

from datetime import datetime
from typing import Annotated

from meritum_core.checks.contracts import CheckStatus, EvalCaseSet, Verdict
from pydantic import BaseModel, ConfigDict, Field


class EvalCaseInput(BaseModel):
    """One case of an uploaded set.

    Attributes:
        case_id: the case id, unique in the set.
        scenario: the scenario A-J.
        text: the text the check runs on.
        expected: the expected verdict, or the expected state when none is.

    Features:
        US-OBS-05, F-26
    """

    model_config = ConfigDict(frozen=True)

    case_id: Annotated[str, Field(min_length=1, max_length=80)]
    scenario: Annotated[str, Field(pattern=r"^[A-J]$")]
    text: Annotated[str, Field(min_length=1, max_length=5000)]
    expected: Verdict | CheckStatus


class Dataset(BaseModel):
    """An uploaded case set.

    Attributes:
        id: the id a run names as its ``dataset``.
        name: the uploaded file's name.
        cases: the validated cases (empty when read back from PostgreSQL).
        blob_id: the blob store id of the raw file; set on upload.

    Features:
        US-OBS-05, F-26
    """

    model_config = ConfigDict(frozen=True)

    id: str
    name: Annotated[str, Field(min_length=1, max_length=200)]
    cases: tuple[EvalCaseInput, ...] = ()
    blob_id: str | None = None


class RunRef(BaseModel):
    """What the backend knows about a run it enqueued; the worker holds the result.

    Attributes:
        run_id: the run id, also the workflow id.
        case_set: golden set or a user file.
        case_file: the uploaded file's name for a user file.
        corpus_version: the snapshot the run pins.
        user_id: the staff inbox that gets the end notification.
        started_at: when the backend enqueued it.

    Features:
        US-OBS-06, F-28
    """

    model_config = ConfigDict(frozen=True)

    run_id: str
    case_set: EvalCaseSet
    case_file: str | None = None
    corpus_version: str
    user_id: str
    started_at: datetime


class RunSummary(BaseModel):
    """A run in the list: the page's ``EvalRun``.

    Attributes:
        id: the run id.
        status: queued, running, done or failed.
        dataset: ``golden`` or the uploaded file's name.
        started_at: when it started.
        finished_at: when it ended.
        metrics: only the measured metrics.

    Features:
        US-OBS-06, F-28
    """

    id: str
    status: str
    dataset: str
    started_at: datetime
    finished_at: datetime | None = None
    metrics: dict[str, float] = {}


class CaseVerdict(BaseModel):
    """One case of a run for the page.

    Attributes:
        case_id: the case id.
        verdict: the predicted verdict; None when the check ended in a state.

    Features:
        US-OBS-06, F-28
    """

    case_id: str
    verdict: Verdict | None


class MetricPair(BaseModel):
    """One metric in both runs.

    Attributes:
        a: its value in run a.
        b: its value in run b.

    Features:
        US-OBS-06, F-28
    """

    a: float
    b: float


class ChangedCase(BaseModel):
    """A case whose predicted verdict differs between the runs.

    Attributes:
        case_id: the case id.
        a: the verdict in run a.
        b: the verdict in run b.

    Features:
        US-OBS-06, F-28
    """

    case_id: str
    a: Verdict | None
    b: Verdict | None


class Comparison(BaseModel):
    """Two runs side by side.

    Attributes:
        metrics: the metrics both runs measured.
        changed_cases: the cases whose predicted verdict differs.

    Features:
        US-OBS-06, F-28
    """

    metrics: dict[str, MetricPair]
    changed_cases: list[ChangedCase]


class Started(BaseModel):
    """Answer to an accepted run.

    Attributes:
        id: the run id.

    Features:
        US-OBS-06, F-28
    """

    id: str


class DatasetSaved(BaseModel):
    """Answer to an accepted case file.

    Attributes:
        id: the dataset id to start a run with.
        cases: how many cases it has.

    Features:
        US-OBS-05, F-26
    """

    id: str
    cases: int


class StartRun(BaseModel):
    """Body of POST /api/v1/eval/runs.

    Attributes:
        dataset: ``golden`` or the id of an uploaded set.

    Features:
        US-OBS-06, F-28
    """

    dataset: Annotated[str, Field(min_length=1, max_length=80)]
