"""A small deterministic retriever, so that the evaluation runs on a clean clone with no
model, no download and no network.

It is not the subject of this repository and it is not a good retriever. It exists to
produce scores and term sets for the gate to read. Replace it with whatever you actually
retrieve with; the gate only needs a score and a term set per result.

Weighting: one weight per distinct content term (the fixture documents are a few sentences
each, so repeating a term carries no extra information), inverse document frequency
log(1 + N / (1 + df)), vectors scaled to unit length, score is the dot product and
therefore lands in 0.0 to 1.0.

Query terms the corpus has never seen are dropped from the query vector, because a term no
document contains cannot raise or lower any document's score. They stay in the content
term set the gate receives. That asymmetry is deliberate and it is what lets relevance
stay high while evidence falls: the part of the question the corpus can speak to decides
the score, and the whole question decides the coverage.
"""

from __future__ import annotations

import math

from .terms import content_terms
from .types import Document, Retrieved


class LexicalIndex:
    """An in memory index over a fixed document set.

    Built once in the constructor. Nothing is read from disk here: the caller supplies
    already loaded documents, which keeps file handling out of the path the gate sits on.
    """

    def __init__(self, documents) -> None:
        self._docs = tuple(documents)
        self._doc_terms = {}
        document_frequency = {}
        for doc in self._docs:
            terms = frozenset(content_terms(doc.title + " " + doc.text))
            self._doc_terms[doc.doc_id] = terms
            for term in terms:
                document_frequency[term] = document_frequency.get(term, 0) + 1

        total = len(self._docs)
        self._idf = {
            term: math.log(1.0 + total / (1.0 + df))
            for term, df in document_frequency.items()
        }

        self._unit = {}
        for doc in self._docs:
            weights = {t: self._idf[t] for t in self._doc_terms[doc.doc_id]}
            self._unit[doc.doc_id] = _to_unit_length(weights)

    @property
    def size(self) -> int:
        return len(self._docs)

    def terms_of(self, doc_id: str) -> frozenset:
        return self._doc_terms[doc_id]

    def search(self, query_terms, limit: int = 5) -> list:
        """The `limit` best documents, best first.

        Sorted by descending score and then by ascending document identifier. The second
        key is not decoration: equal scores are common in a small corpus, and without a
        total order the result list would depend on the order documents were supplied.
        """
        known = {t: self._idf[t] for t in query_terms if t in self._idf}
        if not known:
            return []
        query_vector = _to_unit_length(known)

        scored = []
        for doc in self._docs:
            unit = self._unit[doc.doc_id]
            score = sum(w * unit.get(term, 0.0) for term, w in query_vector.items())
            if score > 0.0:
                scored.append(Retrieved(
                    doc_id=doc.doc_id,
                    score=score,
                    terms=self._doc_terms[doc.doc_id],
                ))

        scored.sort(key=lambda r: (-r.score, r.doc_id))
        return scored[:limit]


def _to_unit_length(weights) -> dict:
    """Scale a term weight mapping to unit length. An all zero mapping is returned as is,
    rather than raising: a document of nothing but stop words is a legitimate input."""
    norm = math.sqrt(sum(w * w for w in weights.values()))
    if norm == 0.0:
        return dict(weights)
    return {term: w / norm for term, w in weights.items()}


def documents_from_records(records) -> list:
    """Build documents from plain dictionaries, for a caller that loaded them from a file.

    Kept here rather than in the eval runner so that the shape of a document is defined in
    one place.
    """
    return [
        Document(doc_id=r["doc_id"], title=r["title"], text=r["text"])
        for r in records
    ]
