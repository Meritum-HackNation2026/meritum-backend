"""Synced copy/pl.json matches SHA256SUMS; API keys used in checks exist there.

Features:
    US-SPR-11, F-08, design-system#90
"""

import hashlib
import json
import re
from pathlib import Path

from meritum_backend.checks.constants import AUDIO_FORMAT_KEY

ROOT = Path(__file__).resolve().parent.parent
COPY = ROOT / "copy" / "pl.json"
SUMS = ROOT / "SHA256SUMS"
SUM_LINE = re.compile(r"^([0-9a-f]{64}) {2}(.+)$")


def _lookup(data: object, dotted: str) -> str | None:
    node: object = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, str) else None


def test_synced_copy_matches_sha256sums() -> None:
    line = SUMS.read_text(encoding="utf-8").strip().splitlines()[0]
    match = SUM_LINE.match(line)
    assert match is not None, f"bad SHA256SUMS line: {line!r}"
    expected, path = match.group(1), match.group(2)
    assert path == "copy/pl.json"
    digest = hashlib.sha256(COPY.read_bytes()).hexdigest()
    assert digest == expected


def test_audio_format_rejection_key_exists_in_synced_copy() -> None:
    text = _lookup(json.loads(COPY.read_text(encoding="utf-8")), AUDIO_FORMAT_KEY)
    assert text is not None, f"missing copy key {AUDIO_FORMAT_KEY!r}"
    assert text, f"empty copy text for {AUDIO_FORMAT_KEY!r}"
    assert "nagran" in text.lower()
