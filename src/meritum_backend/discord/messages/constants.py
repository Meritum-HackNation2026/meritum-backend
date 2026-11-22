"""Limits and colours of the reply embed.

Features:
    US-WTY-06, F-03
"""

from typing import Final

EMBED_MAX_CHARS: Final = 5800
"""Discord allows 6000 characters over one embed; the rest is slack for counting."""

DESCRIPTION_MAX_CHARS: Final = 1500
"""Longest embed description (transcript, note, case number)."""

FIELD_NAME_MAX_CHARS: Final = 256
"""Discord limit of an embed field's name."""

FIELD_VALUE_MAX_CHARS: Final = 1024
"""Discord limit of an embed field's value."""

FIELDS_MAX: Final = 25
"""Discord limit of fields in one embed."""

FRAGMENT_LIMITS: Final = (600, 300, 150, 60, 0)
"""Quote lengths tried in turn until the embed fits: quotes shrink, claims stay."""

BUTTON_LINK: Final = 5
"""Component button style: a link, no interaction."""

VERDICT_COLORS: Final = {
    "false": 0xC8213A,
    "misleading": 0xB7791F,
    "confirmed": 0x1D6A86,
}
"""design-system verdict colours, most serious first: the embed takes the first
one any claim has."""

COLOR_MUTED: Final = 0x4C5862
"""design-system secondary ink: no evidence or not verifiable."""

EMPTY_FIELD: Final = "\u200b"
"""Discord rejects an empty field value: a zero-width space stands in."""
