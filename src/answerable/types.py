"""Data shapes the gate reads and returns.

Nothing here has behaviour beyond construction and range checking. The gate is a function
over these values, which is what makes it testable without a corpus, a retriever or a
generator.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class Zone(str, Enum):
    """Where a query lands.

    The three values are not a severity scale. ANSWERABLE is the only one that may reach a
    generator; AMBIGUOUS and EMPTY differ in what the caller may show instead, not in
    whether an answer may be written.
    """

    ANSWERABLE = "answerable"
    AMBIGUOUS = "ambiguous"
    EMPTY = "empty"


@dataclass(frozen=True)
class Document:
    """A unit of retrievable text. One document is the largest thing an answer may be
    grounded in, which is why coverage is measured per document and not across the set."""

    doc_id: str
    title: str
    text: str


@dataclass(frozen=True)
class Retrieved:
    """One retrieval result handed to the gate.

    `terms` is the document's content term set. The retriever supplies it so that the gate
    performs no tokenisation of its own: a caller using a different tokeniser only has to
    use the same one for documents and for queries.
    """

    doc_id: str
    score: float
    terms: frozenset


@dataclass(frozen=True)
class Thresholds:
    """The two floors.

    `relevance_floor` is on the retriever's score scale, so it has to be re-derived for any
    retriever other than the one in this repository. `evidence_floor` is a share of the
    query's content terms and is scale free.
    """

    relevance_floor: float
    evidence_floor: float

    def __post_init__(self) -> None:
        # The relevance floor has no upper bound, because the scale it sits on has none. A
        # dot product over unnormalised vectors, a BM25 score and a reranker logit can all
        # exceed 1.0, and a caller using one of those must be able to say so.
        if not math.isfinite(self.relevance_floor) or self.relevance_floor < 0.0:
            raise ValueError("relevance_floor must be a finite number and not negative")
        # Evidence is a share of the query's content terms, so this one genuinely is bounded.
        if not 0.0 <= self.evidence_floor <= 1.0:
            raise ValueError("evidence_floor must be between 0.0 and 1.0")


@dataclass(frozen=True)
class Decision:
    """What the gate concluded, and enough of the arithmetic to explain it.

    `reason` is a sentence meant to be logged next to the query. Reading a log of refusals
    is how a floor gets re-derived later, and a refusal that does not say which signal fell
    short is not reviewable.
    """

    zone: Zone
    relevance: float
    evidence: float
    support_doc_id: str
    reason: str

    @property
    def may_call_generator(self) -> bool:
        """The single place that answers whether a generator may run.

        Callers are expected to branch on this and not on `zone`, so that adding a
        fourth zone later cannot silently open the generator to it.
        """
        return self.zone is Zone.ANSWERABLE
