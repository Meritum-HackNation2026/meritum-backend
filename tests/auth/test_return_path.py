"""The return path on the login model: a session from before #82 goes home."""

from meritum_backend.auth import PendingLogin


def test_login_from_before_the_return_path_goes_home() -> None:
    pending = PendingLogin(
        provider="google",
        state="s",
        nonce="n",
        code_verifier="v",
        redirect_uri="https://x/cb",
    )
    assert pending.return_to == "/"
