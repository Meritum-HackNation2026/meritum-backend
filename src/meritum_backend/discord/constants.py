"""Discord constants: application commands and interaction codes.

``COMMANDS`` is registered by scripts/register_discord_commands.py.
"""

from typing import Any, Final

CHECK: Final = "sprawdz"
"""Slash command name: ``/sprawdz tekst:<text or link>``."""

CHECK_MESSAGE: Final = "Sprawdź w Meritum"
"""Message command name: the Apps menu on any message."""

TEXT_OPTION: Final = "tekst"
"""Option of the slash command that carries the text to check."""

_WHERE: Final[dict[str, Any]] = {"contexts": [0, 1, 2], "integration_types": [0, 1]}
"""Usable in servers, DMs with the app and private channels; installable on a
server or on a user's own account (citizens can use it anywhere)."""

COMMANDS: Final[list[dict[str, Any]]] = [
    {
        "name": CHECK,
        "type": 1,
        "description": "Check a claim against described sources",
        "description_localizations": {
            "pl": "Sprawdź twierdzenie w opisanych źródłach",
        },
        "options": [
            {
                "type": 3,
                "name": TEXT_OPTION,
                "description": "Text or link to check",
                "description_localizations": {"pl": "Tekst albo link do sprawdzenia"},
                "required": True,
                "max_length": 4000,
            }
        ],
        **_WHERE,
    },
    {"name": CHECK_MESSAGE, "type": 3, **_WHERE},
]
"""Global application commands of the Meritum Discord app."""

PING: Final = 1
"""Interaction type: Discord probes the endpoint."""

APPLICATION_COMMAND: Final = 2
"""Interaction type: a slash or message command."""

PONG: Final = 1
"""Response type answering PING."""

CHANNEL_MESSAGE: Final = 4
"""Response type: a message in the channel."""

EPHEMERAL: Final = 64
"""Message flag: only the person who asked sees the answer."""
