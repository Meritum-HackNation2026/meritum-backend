"""Discord application commands (registered by scripts/register_discord_commands.py)."""

from typing import Any

CHECK = "sprawdz"  # slash command: /sprawdz tekst:<text or link>
CHECK_MESSAGE = "Sprawdź w Meritum"  # message command: Apps menu on any message
TEXT_OPTION = "tekst"

# Usable in servers, in DMs with the app and in private channels; installable on a
# server or on a user's own account (citizens can use it anywhere).
_WHERE: dict[str, Any] = {"contexts": [0, 1, 2], "integration_types": [0, 1]}

COMMANDS: list[dict[str, Any]] = [
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
