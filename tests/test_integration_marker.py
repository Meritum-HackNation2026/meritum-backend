"""The `integration` marker: deselected by default, selected with -m integration."""

import subprocess  # ruff: ignore[suspicious-subprocess-import] -- runs pytest itself on a generated test file
import sys
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"
MARKED = """
import pytest

@pytest.mark.integration
def test_needs_postgres() -> None:
    pass
"""


def run_pytest(tmp_path: Path, *args: str) -> str:
    test = tmp_path / "test_marked.py"
    test.write_text(MARKED, encoding="utf-8")
    command = [sys.executable, "-m", "pytest", "-c", str(PYPROJECT), *args, str(test)]
    done = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed command, no user input
        command, capture_output=True, text=True, check=False, cwd=tmp_path
    )
    return done.stdout


def test_integration_tests_are_deselected_by_default(tmp_path: Path) -> None:
    assert "1 deselected" in run_pytest(tmp_path)


def test_integration_tests_run_on_request(tmp_path: Path) -> None:
    assert "1 passed" in run_pytest(tmp_path, "-m", "integration")
