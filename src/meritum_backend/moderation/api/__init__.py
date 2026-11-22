"""Moderation HTTP API: the panel's routes and the citizen's hand-off routes.

Features:
    US-MOD-03, US-MOD-05, US-MOD-06, US-MOD-07, F-20, F-24, F-25, F-39
"""

from meritum_backend.moderation.api._answer import router as answer_router
from meritum_backend.moderation.api._cases import router
from meritum_backend.moderation.api._close import router as close_router
from meritum_backend.moderation.api._handoff import router as handoff_router

__all__ = ["answer_router", "close_router", "handoff_router", "router"]
