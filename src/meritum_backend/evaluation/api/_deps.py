"""FastAPI dependencies of the evaluation routes."""

from typing import Annotated

from fastapi import Depends, Request

from meritum_backend.evaluation.constants import RUN_ROLES
from meritum_backend.evaluation.ports import EvalStore
from meritum_backend.staff import StaffMember
from meritum_backend.staff.api import StaffGate

Analyst = Annotated[StaffMember, Depends(StaffGate(RUN_ROLES, allow_jury=True))]
Starter = Annotated[StaffMember, Depends(StaffGate(RUN_ROLES))]


def get_eval_store(request: Request) -> EvalStore:
    """The run index the app built (overridden in tests).

    Args:
        request: the current request (holds the app state).

    Returns:
        The app's evaluation store.

    Features:
        US-OBS-06, F-28
    """
    return request.app.state.eval_store


Store = Annotated[EvalStore, Depends(get_eval_store)]
