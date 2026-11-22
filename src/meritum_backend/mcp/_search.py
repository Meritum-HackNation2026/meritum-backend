"""The search_sources tool: passages of the corpus, as short fragments with links.

Features:
    US-WDR-06, US-WTY-09, US-KOR-05, F-37, F-42, ADR-32
"""

from collections.abc import Mapping
from datetime import UTC, date, datetime

from fastmcp.exceptions import ToolError
from meritum_core.corpus import (
    CorpusSearchPort,
    CorpusUnavailableError,
    Passage,
    UnknownCorpusVersionError,
)
from meritum_core.security import PiiGatePort
from meritum_core.shared.embeddings import EmbeddingsUnavailableError
from pydantic import BaseModel

from meritum_backend.checks import masked_text
from meritum_backend.limits import CheckGate, Origin
from meritum_backend.mcp.constants import (
    BLANK_QUERY_TEXT,
    CORPUS_UNAVAILABLE_TEXT,
    ELLIPSIS,
    FRAGMENT_MAX_CHARS,
    QUERY_MAX_CHARS,
    RATE_LIMITED_TEXT,
    RESULT_LIMIT,
)
from meritum_backend.mcp.ports import SourceCatalogue, SourceInfo


class SourceFragment(BaseModel):
    """One found passage: a short fragment and where it comes from.

    Attributes:
        source_id: the corpus document id.
        title: the document title, when the corpus has it.
        publisher: the catalogue publisher id.
        published_on: the publication date, when known.
        url: the document link, when the catalogue knows it.
        fragment: at most FRAGMENT_MAX_CHARS of the passage, never the full text.
        corpus_version: the snapshot the passage was found in.

    Features:
        US-WDR-06, US-KOR-05, F-37, ADR-32
    """

    source_id: str
    title: str | None
    publisher: str | None
    published_on: date | None
    url: str | None
    fragment: str
    corpus_version: str


class SourceSearch(BaseModel):
    """Result of ``search_sources``.

    Attributes:
        corpus_version: the pinned snapshot that was searched.
        fragments: best first; empty when nothing matched.

    Features:
        US-WDR-06, F-37, ADR-32
    """

    corpus_version: str
    fragments: list[SourceFragment]


def _cut(text: str) -> str:
    if len(text) <= FRAGMENT_MAX_CHARS:
        return text
    return text[: FRAGMENT_MAX_CHARS - len(ELLIPSIS)].rstrip() + ELLIPSIS


async def search_sources(  # ruff: ignore[too-many-arguments]
    query: str,
    *,
    origin: Origin,
    gate: CheckGate,
    pii: PiiGatePort,
    corpus: CorpusSearchPort,
    catalogue: SourceCatalogue,
    corpus_version: str,
) -> SourceSearch:
    """Search the pinned corpus snapshot with a masked query.

    Args:
        query: the caller's query.
        origin: the caller's address and region, for the search limit.
        gate: counts the search against the address's budget.
        pii: masks personal data in the query.
        corpus: the corpus search port (ADR-32).
        catalogue: gives title, publisher and link of found sources.
        corpus_version: the pinned snapshot.

    Returns:
        Fragments with source data.

    Raises:
        ToolError: blank query, over the limit, or the corpus is unavailable.

    Features:
        US-WDR-06, US-WTY-09, US-KOR-05, F-37, F-42, ADR-32
    """
    if not query.strip():
        raise ToolError(BLANK_QUERY_TEXT)
    if await gate.search_refusal(origin):
        raise ToolError(RATE_LIMITED_TEXT)
    safe = await masked_text(query.strip(), QUERY_MAX_CHARS, pii)
    try:
        passages = await corpus.search(
            safe,
            claim_date=datetime.now(UTC).date(),
            corpus_version=corpus_version,
            limit=RESULT_LIMIT,
        )
        known = await catalogue.describe({p.source_id for p in passages})
    except (
        UnknownCorpusVersionError,
        CorpusUnavailableError,
        EmbeddingsUnavailableError,
    ) as exc:
        raise ToolError(CORPUS_UNAVAILABLE_TEXT) from exc
    return SourceSearch(
        corpus_version=corpus_version,
        fragments=[_fragment(p, known, corpus_version) for p in passages],
    )


def _fragment(
    passage: Passage, known: Mapping[str, SourceInfo], corpus_version: str
) -> SourceFragment:
    info = known.get(passage.source_id)
    return SourceFragment(
        source_id=passage.source_id,
        title=info.title if info else None,
        publisher=info.publisher if info else None,
        published_on=passage.published_on,
        url=info.url if info else None,
        fragment=_cut(passage.text),
        corpus_version=corpus_version,
    )
