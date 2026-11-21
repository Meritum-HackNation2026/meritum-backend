"""Names vulture cannot see being used: read by frameworks, not by our code.

Run: ``uv run vulture`` (paths come from ``[tool.vulture]`` in pyproject.toml).
"""

from meritum_backend.auth import Account
from meritum_backend.auth.models import Me
from meritum_backend.checks.api import AudioRejected
from meritum_backend.limits import LimitSettings
from meritum_backend.settings import Settings

Settings.model_config  # read by pydantic-settings
Account.email_verified  # Pydantic field, read by model_dump
Me.email_verified  # response field, serialised by FastAPI
AudioRejected.formats  # response fields with defaults, serialised by model_dump
AudioRejected.max_mb
AudioRejected.max_minutes
LimitSettings.empty_salt_is_unset  # pydantic field validator, called by pydantic
