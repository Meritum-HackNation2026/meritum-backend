"""deploy/container_env.sh: secrets by name, files volume mounted in `docker run`."""

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


def test_login_secrets_reach_the_container() -> None:
    secrets = {"MERITUM_SESSION_SECRET_PRD": "k", "GOOGLE_CLIENT_SECRET_PRD": "g"}
    args, _ = run("prd", secrets, {"GOOGLE_CLIENT_ID_PRD": "id"})
    assert {
        "MERITUM_SESSION_SECRET",
        "MERITUM_GOOGLE_CLIENT_SECRET",
        "MERITUM_GOOGLE_CLIENT_ID",
    } <= set(args)


def test_admin_emails_reach_the_container() -> None:
    args, environment = run("dev", {"MERITUM_ADMIN_EMAILS_DEV": "a@x.pl,b@x.pl"}, {})
    assert "MERITUM_ADMIN_EMAILS" in args
    assert "MERITUM_ADMIN_EMAILS=a@x.pl,b@x.pl" in environment


def test_mcp_api_keys_reach_the_container_by_name() -> None:
    key = "dev-client=k3y-value"
    args, environment = run("dev", {"MERITUM_MCP_API_KEYS_DEV": key}, {})
    assert "MERITUM_MCP_API_KEYS" in args
    assert key not in " ".join(args)
    assert f"MERITUM_MCP_API_KEYS={key}" in environment


def mount(envfile: Path) -> list[str]:
    done = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed command, test data only
        [
            BASH,
            "-c",
            'source "$1"; files_mount "$2"; printf "%s\\n" "${mount_args[@]}"',
            "test",
            str(HELPER),
            str(envfile),
        ],
        capture_output=True,
        text=True,
        check=True,
        env={"PATH": os.environ["PATH"]},
    )
    return done.stdout.split()


def test_files_volume_of_the_env_file_is_mounted(tmp_path: Path) -> None:
    envfile = tmp_path / "api-dev.env"
    envfile.write_text(
        "MERITUM_DATABASE_URL=x\nMERITUM_FILES_VOLUME=meritum-files-dev\n"
        "MERITUM_FILES_DIR=/var/lib/meritum/files\n"
    )
    assert mount(envfile) == ["-v", "meritum-files-dev:/var/lib/meritum/files"]


def test_env_file_without_files_volume_mounts_nothing(tmp_path: Path) -> None:
    envfile = tmp_path / "api-dev.env"
    envfile.write_text("MERITUM_DATABASE_URL=x\n")
    assert mount(envfile) == []


def gcp_mount_args(envfile: Path) -> list[str]:
    done = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed command, test data only
        [
            BASH,
            "-c",
            'source "$1"; gcp_mounts "$2"; printf "%s\\n" "${gcp_args[@]}"',
            "test",
            str(HELPER),
            str(envfile),
        ],
        capture_output=True,
        text=True,
        check=True,
        env={"PATH": os.environ["PATH"]},
    )
    return done.stdout.split()


def test_each_gcp_mount_of_the_env_file_is_mounted(tmp_path: Path) -> None:
    envfile = tmp_path / "api-dev.env"
    envfile.write_text(
        "GOOGLE_APPLICATION_CREDENTIALS=/etc/meritum/gcp/meritum-backend/wif.json\n"
        "MERITUM_GCP_MOUNTS=/home/m/meritum/gcp/meritum-backend:/etc/meritum/gcp/"
        "meritum-backend:ro /home/m/meritum/gcp/pki:/etc/meritum/pki:ro\n"
    )
    assert gcp_mount_args(envfile) == [
        "-v",
        "/home/m/meritum/gcp/meritum-backend:/etc/meritum/gcp/meritum-backend:ro",
        "-v",
        "/home/m/meritum/gcp/pki:/etc/meritum/pki:ro",
    ]


def test_env_file_without_gcp_mounts_mounts_nothing(tmp_path: Path) -> None:
    envfile = tmp_path / "api-dev.env"
    envfile.write_text("MERITUM_DATABASE_URL=x\n")
    assert gcp_mount_args(envfile) == []


def test_gcp_mount_without_read_only_is_skipped(tmp_path: Path) -> None:
    envfile = tmp_path / "api-dev.env"
    envfile.write_text("MERITUM_GCP_MOUNTS=/h/gcp:/etc/gcp /h/pki:/etc/pki:ro\n")
    assert gcp_mount_args(envfile) == ["-v", "/h/pki:/etc/pki:ro"]


def test_sms_gateway_secrets_reach_the_container() -> None:
    names = (
        "SMS_GATEWAY_USERNAME",
        "SMS_GATEWAY_PASSWORD",
        "SMS_GATEWAY_WEBHOOK_SIGNING_KEY",
        "SMS_GATEWAY_NUMBER",
    )
    args, environment = run("dev", {f"{n}_DEV": "v" for n in names}, {})
    assert {f"MERITUM_{n}" for n in names} <= set(args)
    assert all(f"MERITUM_{n}=v" in environment for n in names)
