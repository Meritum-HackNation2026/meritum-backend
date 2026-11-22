"""Entrypoint: ``python -m meritum_backend.discord.gateway``.

Features:
    US-WTY-06, F-03
"""

import asyncio
import logging
import sys

from meritum_backend.discord.gateway._run import run

logging.basicConfig(level=logging.INFO)
sys.exit(asyncio.run(run()))
