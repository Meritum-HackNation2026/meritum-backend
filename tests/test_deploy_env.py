"""deploy/container_env.sh: repo secrets reach `docker run` by name only."""

import json
import os
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- runs the deploy helper under bash
from pathlib import Path

HELPER = Path(__file__).resolve().parents[1] / "deploy" / "container_env.sh"
BASH = shutil.which("bash") or "/bin/bash"
SCRIPT = (
    'source "$1"; container_env "$2"; printf "%s\\n" "${env_args[@]}"; echo ---; env'
)
SALT = "s3cret-salt-value"


def run(
    env: str, secrets: dict[str, str], variables: dict[str, str]
) -> tuple[list[str], str]:
    done = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed command, test data only
        [BASH, "-c", SCRIPT, "test", str(HELPER), env],
        capture_output=True,
        text=True,
        check=True,
        env={
            "PATH": os.environ["PATH"],
            "SECRETS_JSON": json.dumps(secrets),
            "VARS_JSON": json.dumps(variables),
        },
    )
    args, environment = done.stdout.split("---\n")
    return args.split(), environment


def test_secret_of_the_branch_env_is_passed_by_name() -> None:
    args, environment = run(
        "dev",
        {"MERITUM_CHANNEL_HASH_SALT_DEV": SALT, "MERITUM_CHANNEL_HASH_SALT_PRD": "x"},
        {},
    )
    assert "MERITUM_CHANNEL_HASH_SALT" in args
    assert SALT not in " ".join(args)
    assert f"MERITUM_CHANNEL_HASH_SALT={SALT}" in environment


def test_discord_key_comes_from_repo_variable() -> None:
    args, environment = run("prd", {}, {"DISCORD_PUBLIC_KEY_PRD": "abc"})
    assert "MERITUM_DISCORD_PUBLIC_KEY" in args
    assert "MERITUM_DISCORD_PUBLIC_KEY=abc" in environment


def test_missing_secret_is_skipped() -> None:
    args, _ = run("dev", {}, {})
    assert args == []
