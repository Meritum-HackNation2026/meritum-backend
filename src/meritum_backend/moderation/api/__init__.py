"""Moderation HTTP API: the panel's routes and the citizen's hand-off routes.

Features:
    US-MOD-03, US-MOD-05, US-MOD-06, F-20, F-24, F-25
"""

from meritum_backend.moderation.api._cases import router
from meritum_backend.moderation.api._handoff import router as handoff_router

__all__ = ["handoff_router", "router"]
