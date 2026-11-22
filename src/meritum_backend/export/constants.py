"""Constants of the export slice."""

from typing import Final
from uuid import UUID

from meritum_core.checks.contracts import StaffRole

EXPORT_ROLES: Final[frozenset[StaffRole]] = frozenset({"analyst", "admin"})
"""Roles that may export."""

DEFAULT_DAYS: Final = 7
"""Window of the export when the caller names none: the last week."""

MAX_DAYS: Final = 365
"""Longest window a caller may ask for."""

MAX_EXPORT_CHECKS: Final = 10_000
"""Most check records one export can render in memory."""

EXPORT_LIMIT_DETAIL: Final = "too many checks to export; reduce days"
"""Error detail for a date range that exceeds the export limit."""

STIX_MEDIA_TYPE: Final = "application/stix+json;version=2.1"
"""Media type of a STIX 2.1 bundle."""

CSV_MEDIA_TYPE: Final = "text/csv; charset=utf-8"
"""Media type of the CSV export."""

CSV_FORMULA_PREFIXES: Final = ("=", "+", "-", "@", "\t", "\r")
"""Cell starts a spreadsheet runs as a formula; the export prefixes them with ``'``."""

CSV_COLUMNS: Final = (
    "check_id",
    "channel",
    "received_at",
    "answered_at",
    "status",
    "verdicts",
    "source_ids",
    "corpus_version",
    "cache_hit",
    "case_ids",
    "question_masked",
)
"""One row per check; no session, user or channel hash column."""

STIX_NAMESPACE: Final = UUID("6f1b1c7e-2a4d-4a53-9a5e-7b1d1d0c5e11")
"""UUID namespace of the deterministic (v5) STIX ids, so a re-export keeps the ids."""

IDENTITY_NAME: Final = "Meritum"
"""The STIX identity that created every object."""

TO_CONFIRM: Final = "do potwierdzenia przez analityka"
"""Annotation on every DISARM mapping: the mapping is ours, not an analyst's finding."""

DISARM_SOURCE: Final = "DISARM"
"""``source_name`` of the external reference that carries a DISARM technique id."""

DISARM_TECHNIQUES: Final[dict[str, tuple[str, str] | None]] = {
    "false_authority": None,
    "conspiracy_theory": ("T0022", "Leverage Conspiracy Theory Narratives"),
    "out_of_context": ("T0023.001", "Reframe Context"),
    "outdated": None,
    "fabricated_quote": ("T0023", "Distort Facts"),
    "manipulated_media": ("T0086.003", "Deceptively Edit Images (Cheap Fakes)"),
    "impersonation": ("T0099", "Impersonate Existing Entity"),
    "cherry_picking": ("T0023", "Distort Facts"),
}
"""``TechniqueCode`` -> (DISARM id, name); None where DISARM has no counterpart.

Every entry is flagged ``TO_CONFIRM`` in the bundle. Source: the DISARM framework
(https://www.disarm.foundation/framework).
"""
