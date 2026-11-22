"""Evaluation slice: start, list and compare evaluation runs, upload case files.

The worker runs and scores them (``eval_run`` workflow); the API enqueues, reads.

Features:
    US-OBS-06, US-OBS-05, US-POW-05, F-28
"""

from meritum_backend.evaluation.factory import build_eval_store
from meritum_backend.evaluation.ports import EvalStore

__all__ = ["EvalStore", "build_eval_store"]
