"""behave hooks: every scenario starts with fresh rate-limit counters."""

from behave.model import Scenario
from behave.runner import Context

from meritum_backend.limits import limiter


def before_scenario(context: Context, scenario: Scenario) -> None:
    """Reset the module-level slowapi counters before each scenario.

    Args:
        context: the behave context.
        scenario: the scenario about to run.

    Features:
        none (infrastructure)
    """
    del context, scenario
    limiter.reset()
