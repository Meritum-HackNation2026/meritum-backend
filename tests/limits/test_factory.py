from dbos import DBOSClient
from meritum_core.jobs.contracts import APPLICATION_NAME

from meritum_backend.limits import LimitSettings, build_check_gate
from meritum_backend.limits.adapters import DbosPendingChecks, PostgresRateCounter
from meritum_backend.settings import Settings

DB = "postgresql://x:x@127.0.0.1:1/x"


def test_gate_counts_on_postgres_and_reads_the_dbos_queue() -> None:
    client = DBOSClient(
        system_database_url=DB, application_name=APPLICATION_NAME, lazy=True
    )
    try:
        gate = build_check_gate(Settings(database_url=DB), LimitSettings(), client)
    finally:
        client.destroy()
    assert isinstance(gate.counter, PostgresRateCounter)
    assert isinstance(gate.pending, DbosPendingChecks)
