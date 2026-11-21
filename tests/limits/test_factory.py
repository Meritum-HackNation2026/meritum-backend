from dbos import DBOSClient
from meritum_core.jobs.contracts import APPLICATION_NAME

from meritum_backend.limits import LimitSettings, MemoryRateCounter, build_check_gate
from meritum_backend.limits.adapters import DbosPendingChecks, PostgresRateCounter
from meritum_backend.settings import Settings

DB = "postgresql://x:x@127.0.0.1:1/x"


def build(counter: str) -> object:
    client = DBOSClient(
        system_database_url=DB, application_name=APPLICATION_NAME, lazy=True
    )
    limits = LimitSettings.model_validate({"rate_counter": counter})
    try:
        gate = build_check_gate(Settings(database_url=DB), limits, client)
    finally:
        client.destroy()
    assert isinstance(gate.pending, DbosPendingChecks)
    return gate.counter


def test_postgres_is_the_shared_counter() -> None:
    assert isinstance(build("postgres"), PostgresRateCounter)


def test_memory_counter_on_request() -> None:
    assert isinstance(build("memory"), MemoryRateCounter)
