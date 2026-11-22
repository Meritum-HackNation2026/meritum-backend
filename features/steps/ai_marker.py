"""Steps of features/channels.feature: the AI marker of a cached result.

Features:
    US-BEZ-07, US-WTY-03
"""

from behave import then
from behave.runner import Context


@then(
    "oba wyniki mają ten sam znacznik AI z dostawcą i modelem,"
    " który napisał uzasadnienie"
)
def same_ai_marker(context: Context) -> None:
    """The hit carries the marker of the check whose model wrote the answer.

    Args:
        context: the behave context with ``results`` from result_cache steps.

    Features:
        US-BEZ-07, US-WTY-03
    """
    first, hit = (r.ai_marker for r in context.results)
    assert first is not None
    assert first.ai_generated
    assert hit == first
