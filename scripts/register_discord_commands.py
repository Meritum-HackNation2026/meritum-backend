"""Register Meritum's Discord commands (/sprawdz and "Sprawdź w Meritum") for one app.

    DISCORD_APPLICATION_ID=... DISCORD_BOT_TOKEN=... \
        uv run python scripts/register_discord_commands.py

Run once per Discord app (one for dev, one for prd) and after changing
src/meritum_backend/discord/constants.py. Overwrites the app's global commands.
"""

import json
import os
import urllib.request

from meritum_backend.discord.constants import COMMANDS

app_id = os.environ["DISCORD_APPLICATION_ID"]
request = urllib.request.Request(
    f"https://discord.com/api/v10/applications/{app_id}/commands",
    data=json.dumps(COMMANDS).encode(),
    method="PUT",
    headers={
        "Authorization": f"Bot {os.environ['DISCORD_BOT_TOKEN']}",
        "Content-Type": "application/json",
        "User-Agent": "DiscordBot (https://github.com/Meritum-HackNation2026, 0.1)",
    },
)
# Fixed https URL to Discord's API, no user input (bandit B310 / ruff S310).
with urllib.request.urlopen(request, timeout=30) as response:  # ruff: ignore[suspicious-url-open-usage] # nosec B310
    registered = json.load(response)
print("registered:", ", ".join(c["name"] for c in registered))  # ruff: ignore[print]
