"""Errors of the evaluation slice."""


class EvalStoreUnavailableError(RuntimeError):
    """The evaluation index database cannot be reached.

    Features:
        US-OBS-06, F-28
    """
