"""Names vulture cannot see being used: read by frameworks, not by our code.

Run: ``uv run vulture`` (paths come from ``[tool.vulture]`` in pyproject.toml).
"""

from meritum_backend.settings import Settings

Settings.model_config  # read by pydantic-settings
