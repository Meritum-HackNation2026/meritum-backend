"""The MCP tool `search_sources` over /mcp, on a fake CorpusSearchPort."""

from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastmcp.exceptions import ToolError
from meritum_core.corpus import (
    CorpusUnavailableError,
    Passage,
    UnknownCorpusVersionError,
)
from meritum_core.jobs.fakes import InMemoryJobQueue
from tests.conftest import MakeProbe
from tests.mcp.support import CLIENT, KEY, build_app, call_tool

from meritum_backend.limits import CheckGate, LimitSettings
from meritum_backend.limits.adapters import FixedPendingChecks, MemoryRateCounter
from meritum_backend.mcp import FRAGMENT_MAX_CHARS, RESULT_LIMIT, SourceInfo
from meritum_backend.mcp.adapters import (
    AnyOfAuthenticator,
    ApiKeyAuthenticator,
    MemorySourceCatalogue,
)
from meritum_backend.mcp_oauth import OAuthServer

QUERY = "ostrzeżenia IMGW Mazowsze"
FULL_TEXT = "IMGW wydał ostrzeżenie drugiego stopnia dla Mazowsza. " * 40
INFO = SourceInfo(
    title="Ostrzeżenia meteorologiczne",
    publisher="imgw",
    url="https://imgw.pl/ostrzezenia/1",
)


def _passage(source_id: str, text: str = FULL_TEXT) -> Passage:
    return Passage(
        passage_id=f"{source_id}-1",
        source_id=source_id,
        text=text,
        published_on=date(2026, 11, 1),
        fetched_at=datetime(2026, 11, 2, tzinfo=UTC),
    )


class FakeCorpus:
    def __init__(self, passages: list[Passage] | None = None) -> None:
        self.passages = passages or []
        self.calls: list[tuple[str, str, int]] = []
        self.error: Exception | None = None
        self.dates: list[date] = []

    async def search(
        self,
        query: str,
        *,
        claim_date: date,
        corpus_version: str,
        limit: int = 10,
    ) -> list[Passage]:
        self.dates.append(claim_date)
        self.calls.append((query, corpus_version, limit))
        if self.error:
            raise self.error
        return self.passages[:limit]


def _search(
    make_probe: MakeProbe,
    corpus: FakeCorpus,
    arguments: dict[str, str] | None = None,
    gate: CheckGate | None = None,
) -> dict[str, Any]:
    app = build_app(InMemoryJobQueue(), make_probe)
    app.state.corpus_search = corpus
    app.state.source_catalogue = MemorySourceCatalogue({"imgw-1": INFO})
    result = call_tool(app, arguments or {"query": QUERY}, "search_sources", gate)
    return result.structured_content


def test_returns_fragments_with_source_data_and_corpus_version(
    make_probe: MakeProbe,
) -> None:
    corpus = FakeCorpus([_passage("imgw-1")])

    found = _search(make_probe, corpus)

    [hit] = found["fragments"]
    assert hit["title"] == INFO.title
    assert hit["publisher"] == "imgw"
    assert hit["url"] == INFO.url
    assert hit["published_on"] == "2026-11-01"
    assert hit["corpus_version"] == found["corpus_version"] == "current"
    assert corpus.calls == [(QUERY, "current", RESULT_LIMIT)]
    assert corpus.dates == [datetime.now(UTC).date()]


def test_never_returns_the_full_text(make_probe: MakeProbe) -> None:
    found = _search(make_probe, FakeCorpus([_passage("imgw-1")]))

    [hit] = found["fragments"]
    assert len(hit["fragment"]) <= FRAGMENT_MAX_CHARS
    assert len(hit["fragment"]) < len(FULL_TEXT)


def test_a_source_the_catalogue_does_not_know_keeps_its_id(
    make_probe: MakeProbe,
) -> None:
    found = _search(make_probe, FakeCorpus([_passage("unknown-9")]))

    [hit] = found["fragments"]
    assert hit["source_id"] == "unknown-9"
    assert hit["url"] is None


def test_the_query_is_masked_before_the_search(make_probe: MakeProbe) -> None:
    corpus = FakeCorpus()

    _search(make_probe, corpus, {"query": "IMGW jan.kowalski@example.com"})

    [(sent, _, _)] = corpus.calls
    assert "kowalski" not in sent


@pytest.mark.parametrize(
    "error", [UnknownCorpusVersionError("x"), CorpusUnavailableError("x")]
)
def test_a_corpus_failure_is_a_tool_error(
    make_probe: MakeProbe, error: Exception
) -> None:
    corpus = FakeCorpus()
    corpus.error = error

    with pytest.raises(ToolError):
        _search(make_probe, corpus)


def test_a_blank_query_is_a_tool_error_and_searches_nothing(
    make_probe: MakeProbe,
) -> None:
    corpus = FakeCorpus()

    with pytest.raises(ToolError):
        _search(make_probe, corpus, {"query": "   "})

    assert corpus.calls == []


def test_searches_over_the_limit_are_refused(make_probe: MakeProbe) -> None:
    gate = CheckGate(
        MemoryRateCounter(),
        FixedPendingChecks(),
        LimitSettings(searches_per_ip_per_minute=1),
    )
    corpus = FakeCorpus()
    _search(make_probe, corpus, gate=gate)

    with pytest.raises(ToolError):
        _search(make_probe, corpus, gate=gate)

    assert len(corpus.calls) == 1


def test_search_limit_is_counted_per_authenticated_client(
    make_probe: MakeProbe,
) -> None:
    gate = CheckGate(
        MemoryRateCounter(),
        FixedPendingChecks(),
        LimitSettings(checks_per_client_per_minute=1),
    )
    corpus = FakeCorpus()
    app = build_app(InMemoryJobQueue(), make_probe)
    app.state.corpus_search = corpus
    oauth = app.state.mcp_oauth
    assert isinstance(oauth, OAuthServer)
    token = oauth.tokens("google:1", "test-client").access_token
    app.state.mcp_auth = AnyOfAuthenticator([ApiKeyAuthenticator({CLIENT: KEY}), oauth])
    arguments = {"query": QUERY}
    call_tool(app, arguments, "search_sources", gate)

    with pytest.raises(ToolError, match="Za dużo wyszukiwań"):
        call_tool(app, arguments, "search_sources", gate)

    oauth_headers = {"Authorization": f"Bearer {token}"}
    call_tool(app, arguments, "search_sources", gate, oauth_headers)
    with pytest.raises(ToolError, match="Za dużo wyszukiwań"):
        call_tool(app, arguments, "search_sources", gate, oauth_headers)

    assert len(corpus.calls) == 2
