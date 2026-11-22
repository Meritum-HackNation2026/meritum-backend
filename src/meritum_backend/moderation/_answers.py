"""A moderator's answer to a case: its quotes, their source texts and where both live.

Quotes are checked with core's verbatim rule, the one that checks the system's own
citations (ADR-06). Both stores are in-memory.

Features:
    US-MOD-07, F-39, ADR-06
"""

from collections.abc import Iterable, Sequence
from typing import Annotated, Protocol

from meritum_core.checks.contracts import Source
from meritum_core.evidence import SourceDocument, find_verbatim
from pydantic import BaseModel, Field

from meritum_backend.moderation.constants import (
    ANSWER_QUOTES_MAX,
    ANSWER_TEXT_MAX_CHARS,
    QUOTE_MAX_CHARS,
)


class QuoteDraft(BaseModel):
    """A quote the moderator pasted.

    Attributes:
        source_id: the catalogue source it comes from.
        fragment: the text, which must occur verbatim in the source.

    Features:
        US-MOD-07, F-39, ADR-06
    """

    source_id: Annotated[str, Field(min_length=1, max_length=80)]
    fragment: Annotated[str, Field(min_length=1, max_length=QUOTE_MAX_CHARS)]


class AnswerDraft(BaseModel):
    """Body of a moderator's answer.

    Attributes:
        text: the answer.
        quotes: at least one quote, each verified.

    Features:
        US-MOD-07, F-39
    """

    text: Annotated[str, Field(min_length=1, max_length=ANSWER_TEXT_MAX_CHARS)]
    quotes: Annotated[
        list[QuoteDraft], Field(min_length=1, max_length=ANSWER_QUOTES_MAX)
    ]


class VerifiedQuote(BaseModel):
    """A quote as the source writes it, with the source's metadata.

    Attributes:
        source: the cited source.
        fragment: the fragment exactly as in the source text.

    Features:
        US-MOD-07, F-39, ADR-06
    """

    source: Source
    fragment: str


class Answer(BaseModel):
    """What was sent: no asker, no channel, no session.

    Attributes:
        case_id: the answered case.
        text: the answer.
        quotes: the verified quotes.

    Features:
        US-MOD-07, F-39
    """

    case_id: str
    text: str
    quotes: list[VerifiedQuote]


class SourceDocuments(Protocol):
    """Reads the full text of a catalogue source (port).

    Features:
        US-MOD-07, F-39
    """

    async def get(self, source_id: str) -> SourceDocument | None:
        """Read one source.

        Args:
            source_id: the corpus document id.

        Returns:
            The document, or None when the catalogue has none.
        """
        ...


class AnswerStore(Protocol):
    """Keeps the answers by case (port).

    Features:
        US-MOD-07, F-39
    """

    async def save(self, answer: Answer) -> None:
        """Store the answer of a case.

        Args:
            answer: the answer.
        """
        ...

    async def get(self, case_id: str) -> Answer | None:
        """Read the answer of a case.

        Args:
            case_id: the case id.

        Returns:
            The answer, or None.
        """
        ...


class InMemorySourceDocuments:
    """SourceDocuments over a list.

    shortcut: no adapter over ``corpus.documents`` yet (it holds no title or
    tier), so the app starts with none; build it when the catalogue copy ships.

    Args:
        documents: the documents to serve.

    Features:
        US-MOD-07, F-39
    """

    def __init__(self, documents: Iterable[SourceDocument] = ()) -> None:
        self._documents = {d.source.id: d for d in documents}

    async def get(self, source_id: str) -> SourceDocument | None:
        """Read one source.

        Args:
            source_id: the corpus document id.

        Returns:
            The document, or None.
        """
        return self._documents.get(source_id)


class InMemoryAnswerStore:
    """AnswerStore over a dict.

    shortcut: lost on restart; move it to the app schema with the
    PostgreSQL case repository.

    Features:
        US-MOD-07, F-39
    """

    def __init__(self) -> None:
        self._answers: dict[str, Answer] = {}

    async def save(self, answer: Answer) -> None:
        """Store the answer of a case.

        Args:
            answer: the answer.
        """
        self._answers[answer.case_id] = answer

    async def get(self, case_id: str) -> Answer | None:
        """Read the answer of a case.

        Args:
            case_id: the case id.

        Returns:
            The answer, or None.
        """
        return self._answers.get(case_id)


async def verify_quotes(
    quotes: Sequence[QuoteDraft], documents: SourceDocuments
) -> tuple[list[VerifiedQuote], list[int]]:
    """Check every quote verbatim against its source text.

    Args:
        quotes: what the moderator pasted.
        documents: where the source texts are.

    Returns:
        The verified quotes, and the indexes of those that failed (unknown source or
        a fragment the text does not contain).

    Features:
        US-MOD-07, F-39, ADR-06
    """
    verified: list[VerifiedQuote] = []
    rejected: list[int] = []
    for index, quote in enumerate(quotes):
        document = await documents.get(quote.source_id)
        span = (
            None if document is None else find_verbatim(quote.fragment, document.text)
        )
        if document is None or span is None:
            rejected.append(index)
        else:
            fragment = document.text[span[0] : span[1]]
            verified.append(VerifiedQuote(source=document.source, fragment=fragment))
    return verified, rejected
