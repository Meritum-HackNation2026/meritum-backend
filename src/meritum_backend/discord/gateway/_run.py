"""Composition of the Gateway process: the API's ports, a discord.py client.

Features:
    US-WTY-06, F-03, ADR-01
"""

import logging

from meritum_backend.discord.api import Ports
from meritum_backend.discord.constants import BOT_TOKEN_MISSING
from meritum_backend.discord.gateway._client import MeritumClient
from meritum_backend.discord.gateway._handler import GatewayHandler
from meritum_backend.main import create_app
from meritum_backend.settings import Settings

_log = logging.getLogger(__name__)


async def run(settings: Settings | None = None) -> int:
    """Connect to the Gateway and answer until the process is stopped.

    The ports are the API's own (its lifespan builds them), so a check started
    here is the check POST /api/v1/checks starts.

    Args:
        settings: read from the environment when None.

    Returns:
        1 when the bot token is not configured.

    Features:
        US-WTY-06, F-03, ADR-01
    """
    settings = settings or Settings()
    token = settings.discord_bot_token
    if token is None or not token.get_secret_value():
        _log.error(BOT_TOKEN_MISSING)
        return 1
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        state = app.state
        ports = Ports(
            state.jobs,
            state.check_gate,
            state.pii_gate,
            state.readiness,
            state.result_cache,
            state.repositories.records,
            settings,
        )
        async with MeritumClient(GatewayHandler(ports)) as client:
            await client.start(token.get_secret_value())
    return 0
