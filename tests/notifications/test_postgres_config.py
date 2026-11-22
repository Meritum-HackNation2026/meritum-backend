"""PostgresNotifierConfigStore on a real database (local only, -m integration).

Needs `docker compose up -d --wait db`.
"""

import asyncio

import pytest
from pydantic import SecretStr

from meritum_backend.constants import LOCAL_DB
from meritum_backend.notifications import NotifierConfig
from meritum_backend.notifications.adapters import PostgresNotifierConfigStore


@pytest.mark.integration
def test_the_target_is_saved_replaced_and_deleted() -> None:
    store = PostgresNotifierConfigStore(LOCAL_DB)
    hook = NotifierConfig(
        kind="webhook", url="https://hooks.example/x", secret=SecretStr("k")
    )

    async def cycle() -> list[NotifierConfig | None]:
        await store.delete()
        seen = [await store.get()]
        await store.save(hook)
        seen.append(await store.get())
        await store.save(NotifierConfig(kind="email"))
        seen.append(await store.get())
        await store.delete()
        seen.append(await store.get())
        return seen

    empty, first, second, gone = asyncio.run(cycle())
    assert empty is None
    assert first is not None
    assert first.secret is not None
    assert first.secret.get_secret_value() == "k"
    assert second == NotifierConfig(kind="email")
    assert gone is None
