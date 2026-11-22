"""Seed the dev environment with demo data for the jury accounts (backend#118).

    MERITUM_DEMO_CITIZEN_LINK=... MERITUM_DEMO_ADMIN_LINK=... \
        [MERITUM_MODERATOR_SESSION=...] uv run python scripts/seed_demo.py [--dry-run]

Everything goes through the public API with the same auth a person has: demo links
sign in as the technical accounts, nothing is written to the database. Safe to
re-run: a step whose result already exists is skipped. Works on dev and local only.

Features:
    US-OBS-06, US-MOD-05, US-MOD-07, F-28
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import httpx2

from meritum_backend.jury.constants import DEMO_PATH

DEV_URL = "https://meritum-dev.gburek.app"
ALLOWED_HOSTS = frozenset({"meritum-dev.gburek.app", "localhost", "127.0.0.1"})
API = "/api/v1"
SEED_SESSION = "demo-seed-session"
SESSION_COOKIE = "meritum_session"
CSRF_HEADER = "X-CSRF-Token"
POLL_SECONDS = 5
WAIT_SECONDS = 300
HTTP_TIMEOUT = 60
HTTP_SEE_OTHER = 303

# Invented, public-knowledge claims; no personal data.
CHECKS = (
    "Warszawa jest stolicą Polski.",
    "Wisła wpada do Morza Śródziemnego.",
    "Polska ma najniższe bezrobocie w całej Unii Europejskiej.",
    "Najlepszym miastem do życia w Polsce jest Kraków.",
    "https://pl.wikipedia.org/wiki/Polska",
    "Szczepionka przeciw grypie powoduje grypę.",
)
ESCALATED = CHECKS[-1]
ANSWER_TEXT = (
    "Szczepionka przeciw grypie nie zawiera żywych wirusów zdolnych wywołać "
    "chorobę; po szczepieniu może wystąpić krótkie osłabienie. Źródło poniżej."
)


def _say(message: str) -> None:
    print(message)  # ruff: ignore[print]


def _sign_in(base: str, link: str) -> httpx2.Client:
    # the returned client holds the session cookie
    token = link.rstrip("/").rsplit("/", 1)[-1]
    client = httpx2.Client(base_url=base, timeout=HTTP_TIMEOUT)
    reply = client.get(f"{DEMO_PATH}{token}", follow_redirects=False)
    if reply.status_code != HTTP_SEE_OTHER:
        sys.exit(f"demo link refused: HTTP {reply.status_code}")
    return client


def _moderator(base: str, cookie: str) -> httpx2.Client:
    client = httpx2.Client(base_url=base, timeout=HTTP_TIMEOUT)
    client.cookies.set(SESSION_COOKIE, cookie)
    return client


def _csrf(client: httpx2.Client) -> dict[str, str]:
    reply = client.get(f"{API}/auth/me")
    reply.raise_for_status()
    return {CSRF_HEADER: reply.json()["csrf_token"]}


def _wait(client: httpx2.Client, check_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        reply = client.get(f"{API}/checks/{check_id}")
        reply.raise_for_status()
        result = reply.json().get("result")
        if result is not None:
            return result
        time.sleep(POLL_SECONDS)
    sys.exit(f"check {check_id} did not finish in {WAIT_SECONDS} s")


def _start(client: httpx2.Client, body: dict[str, str]) -> str:
    reply = client.post(
        f"{API}/checks", json=body, headers={"X-Meritum-Session": SEED_SESSION}
    )
    reply.raise_for_status()
    return str(reply.json()["check_id"])


def _upload(client: httpx2.Client, path: Path, route: str, field: str) -> str:
    reply = client.post(f"{API}/{route}", content=path.read_bytes())
    reply.raise_for_status()
    return str(reply.json()[field])


def _seed_checks(
    citizen: httpx2.Client, files: dict[str, Path | None], *, dry_run: bool
) -> dict[str, str]:
    # starts the checks the history lacks; returns check ids by their input
    history = citizen.get(f"{API}/checks")
    history.raise_for_status()
    known = {item["question_masked"]: item["check_id"] for item in history.json()}
    ids: dict[str, str] = {}
    for text in CHECKS:
        if text in known:
            _say(f"skip   check {known[text]}  {text[:50]}")
            ids[text] = known[text]
        elif not dry_run:
            ids[text] = _start(
                citizen, {"url": text} if text.startswith("http") else {"text": text}
            )
            _say(f"create check {ids[text]}  {text[:50]}")
    for route, field, key in (
        ("audio", "audio_id", "audio"),
        ("images", "image_id", "image"),
    ):
        path = files[key]
        if path is not None and not dry_run:
            media = _start(citizen, {field: _upload(citizen, path, route, field)})
            _say(f"create check {media}  ({key}: {path.name}; rerun adds another)")
    return ids


def _find_case(admin: httpx2.Client, check_id: str) -> dict[str, Any] | None:
    reply = admin.get(f"{API}/moderation/cases")
    reply.raise_for_status()
    for case in reply.json():
        if any(check_id in c["check_ids"] for c in case["claims"]):
            return dict(case)
    return None


def _seed_case(
    base: str, citizen: httpx2.Client, admin: httpx2.Client, check_id: str
) -> None:
    case = _find_case(admin, check_id)
    if case is None:
        _wait(citizen, check_id)
        reply = citizen.post(f"{API}/checks/{check_id}/claims/0/escalate")
        reply.raise_for_status()
        case = {"id": reply.json()["escalation"]["case_id"], "state": "open"}
        _say(f"create case  {case['id']}")
    else:
        _say(f"skip   case  {case['id']} ({case['state']})")
    cookie = os.environ.get("MERITUM_MODERATOR_SESSION")
    if case["state"] != "open":
        return
    if cookie is None:
        _say("skip   answer: set MERITUM_MODERATOR_SESSION (a moderator's cookie)")
        return
    result = _wait(citizen, check_id)
    citations = result["claims"][0]["citations"] if result["claims"] else []
    if not citations:
        _say("skip   answer: the check has no citation to quote")
        return
    quote_body = {
        "source_id": citations[0]["source"]["id"],
        "fragment": citations[0]["fragment"],
    }
    moderator = _moderator(base, cookie)
    reply = moderator.post(
        f"{API}/moderation/cases/{quote(case['id'], safe='')}/answer",
        json={"text": ANSWER_TEXT, "quotes": [quote_body]},
        headers=_csrf(moderator),
    )
    reply.raise_for_status()
    _say(f"create answer to {case['id']}")


def _seed_eval(admin: httpx2.Client, *, dry_run: bool) -> None:
    runs = admin.get(f"{API}/eval/runs")
    runs.raise_for_status()
    if runs.json():
        _say(f"skip   eval run ({len(runs.json())} exist)")
    elif not dry_run:
        reply = admin.post(
            f"{API}/eval/runs", json={"dataset": "golden"}, headers=_csrf(admin)
        )
        reply.raise_for_status()
        _say(f"create eval run {reply.json()}")


def main(argv: list[str]) -> int:
    """Seed demo checks, one moderator case with an answer, an eval run.

    Args:
        argv: command line without the program name.

    Returns:
        The exit code.

    Features:
        US-OBS-06, US-MOD-05, US-MOD-07, F-28
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get("MERITUM_SEED_URL", DEV_URL))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--audio", type=Path, help="a recording to check (OGG, MP3, M4A, WAV)"
    )
    parser.add_argument(
        "--image", type=Path, help="a screenshot with text (PNG, JPEG, WebP)"
    )
    args = parser.parse_args(argv)
    base = args.url.rstrip("/")
    if urlparse(base).hostname not in ALLOWED_HOSTS:
        sys.exit(f"refusing {base}: the seed runs on dev or local only")
    citizen = _sign_in(base, os.environ["MERITUM_DEMO_CITIZEN_LINK"])
    admin = _sign_in(base, os.environ["MERITUM_DEMO_ADMIN_LINK"])
    ids = _seed_checks(
        citizen, {"audio": args.audio, "image": args.image}, dry_run=args.dry_run
    )
    if not args.dry_run and ESCALATED in ids:
        _seed_case(base, citizen, admin, ids[ESCALATED])
    _seed_eval(admin, dry_run=args.dry_run)
    notes = citizen.get(f"{API}/notifications")
    count = len(notes.json()) if notes.is_success else "?"
    _say(f"notifications for the citizen: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
