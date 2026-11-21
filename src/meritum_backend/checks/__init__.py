"""Checks slice: the one API every channel calls to check a text, a link or audio.

Features:
    US-SPR-01, US-SPR-07, US-SPR-11, US-BEZ-04, US-BEZ-07, F-01, F-08, F-20, F-21,
    ADR-08
"""

from meritum_backend.checks._uploads import get_blobs
from meritum_backend.checks._uploads import router as audio_router

__all__ = ["audio_router", "get_blobs"]
