"""A retrieval abstention gate: decide whether a query can be answered from its retrieval
results at all, before a generator is called.

Reading order for the decision itself: `types`, `terms`, `gate`. `retrieve` is a stand in
retriever that exists so the evaluation runs without a model.
"""

from __future__ import annotations

from .gate import decide, evidence_of, relevance_of
from .retrieve import LexicalIndex, documents_from_records
from .terms import STOP_WORDS, content_terms, tokenise
from .types import Decision, Document, Retrieved, Thresholds, Zone

__all__ = [
    "Decision",
    "Document",
    "LexicalIndex",
    "Retrieved",
    "STOP_WORDS",
    "Thresholds",
    "Zone",
    "content_terms",
    "decide",
    "documents_from_records",
    "evidence_of",
    "relevance_of",
    "tokenise",
]
