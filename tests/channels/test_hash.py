import hashlib
import hmac
import re

from meritum_core.jobs.constants import HASH_PATTERN
from pydantic import SecretStr

from meritum_backend.channels import channel_user_hash
from meritum_backend.limits import LimitSettings
from meritum_backend.settings import Settings

SALT = SecretStr("test-salt")


def test_hash_is_the_salted_hmac_sha256_of_the_user_id() -> None:
    expected = hmac.new(b"test-salt", b"discord:1234567890", hashlib.sha256).hexdigest()
    assert channel_user_hash("discord", "1234567890", SALT) == expected
    assert re.fullmatch(HASH_PATTERN, expected)


def test_same_user_gets_the_same_hash_and_another_salt_another_one() -> None:
    assert channel_user_hash("discord", "1234567890", SALT) == channel_user_hash(
        "discord", "1234567890", SALT
    )
    assert channel_user_hash("discord", "1234567890", SALT) != channel_user_hash(
        "discord", "1234567890", SecretStr("other-salt")
    )


def test_one_id_in_two_channels_is_two_people() -> None:
    assert channel_user_hash("discord", "42", SALT) != channel_user_hash(
        "mcp", "42", SALT
    )


def test_an_empty_salt_is_no_salt_in_every_settings_class() -> None:
    empty = SecretStr("")
    assert Settings(channel_hash_salt=empty).channel_hash_salt is None
    assert LimitSettings(channel_hash_salt=empty).channel_hash_salt is None
