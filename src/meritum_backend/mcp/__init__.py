"""MCP channel: the check and the source search as tools for chat apps.

Features:
    US-WDR-06, US-WTY-09, F-37, F-42, ADR-17, ADR-32
"""

from meritum_backend.mcp._search import SourceFragment, SourceSearch
from meritum_backend.mcp.api import build_mcp
from meritum_backend.mcp.constants import FRAGMENT_MAX_CHARS, RESULT_LIMIT
from meritum_backend.mcp.factory import build_corpus_reader
from meritum_backend.mcp.ports import SourceCatalogue, SourceInfo

__all__ = [
    "FRAGMENT_MAX_CHARS",
    "RESULT_LIMIT",
    "SourceCatalogue",
    "SourceFragment",
    "SourceInfo",
    "SourceSearch",
    "build_corpus_reader",
    "build_mcp",
]
