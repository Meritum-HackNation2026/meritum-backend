"""Login provider adapters: Authlib (Google, Microsoft) and a fake for tests."""

from meritum_backend.auth.adapters._authlib import AuthlibLogin, OidcClient
from meritum_backend.auth.adapters._fake import FakeLogin

__all__ = ["AuthlibLogin", "FakeLogin", "OidcClient"]
