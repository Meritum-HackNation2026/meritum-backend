"""Names vulture cannot see being used: read by frameworks, not by our code.

Run: ``uv run vulture`` (paths come from ``[tool.vulture]`` in pyproject.toml).
"""

from meritum_backend.auth import Account
from meritum_backend.auth.models import Me
from meritum_backend.checks.api import AudioRejected
from meritum_backend.discord.gateway import MeritumClient
from meritum_backend.evaluation.models import Comparison
from meritum_backend.notifications import NotifierConfigView
from meritum_backend.settings import Settings
from meritum_backend.staff import StaffMember

Settings.model_config  # read by pydantic-settings
Account.email_verified  # Pydantic field, read by model_dump
Me.email_verified  # response field, serialised by FastAPI
AudioRejected.formats  # response fields with defaults, serialised by model_dump
AudioRejected.max_mb
AudioRejected.max_minutes
StaffMember.read_only  # response field, serialised by FastAPI
MeritumClient.on_message  # called by discord.py for each Gateway message
NotifierConfigView.secret_set  # response field, serialised by FastAPI
Comparison.changed_cases  # response field, serialised by FastAPI
