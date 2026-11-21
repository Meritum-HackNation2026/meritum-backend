"""The return path rule on the login model: only same-origin relative paths."""

import pytest

from meritum_backend.auth import PendingLogin

FIELDS = {
    "provider": "google",
    "state": "s",
    "nonce": "n",
    "code_verifier": "v",
    "redirect_uri": "https://x/cb",
}


@pytest.mark.parametrize("path", ["/panel", "/panel/sprawy?id=7#a//b", "/"])
def test_relative_path_is_kept(path: str) -> None:
    assert PendingLogin(**FIELDS, return_to=path).return_to == path


@pytest.mark.parametrize(
    "path", ["//zly.example", "/\\zly.example", "/.//zly.example", "/a//b", "x:/a"]
)
def test_path_that_could_leave_the_site_becomes_home(path: str) -> None:
    assert PendingLogin(**FIELDS, return_to=path).return_to == "/"


def test_login_from_before_the_return_path_goes_home() -> None:
    assert PendingLogin(**FIELDS).return_to == "/"
