"""The decision.

Pure functions over values: no file access, no network, no clock, no randomness, no global
state, no logging. Everything the gate knows arrives as an argument, which is why a zone
boundary can be tested without building a corpus.

Two signals, both read off the retrieval results:

  relevance   the score of the best retrieved document. It answers one question: is
              anything in the corpus about this query at all.

  evidence    the largest share of the query's content terms that any SINGLE retrieved
              document covers. It answers a different question: does one document address
              enough of what was asked.

The two disagree in a specific and common case, which is the reason for having both. A
question naming a rare entity ranks that entity's document first even when the document
does not record the attribute the question asks for. Ranking first is all that relevance
reports, and the score behind it may be low: the best of a weak field still comes first.
Evidence is then a fraction, and a single number cannot tell that apart from an answerable
question. A generator handed the document will supply the missing attribute from nowhere.

The two signals need not come from the same document. Relevance is the top score and
evidence is a maximum taken over the whole retrieved list, so the document that ranks first
and the document that covers the most terms are often different ones. Neither signal is a
property of a single result, and `support_doc_id` names only the second of them.

Evidence is measured per document on purpose. A question whose terms are covered by two
documents, each covering half, is the shape of a confident wrong answer: the generator
stitches the halves and the result is grounded in nothing. Taking the maximum over single
documents refuses that case instead of rewarding it.
"""

from __future__ import annotations

from .types import Decision, Thresholds, Zone


def relevance_of(results) -> float:
    """The best score among the results, or 0.0 when there are none.

    Takes the maximum and not `results[0]`, so that an unsorted result list cannot
    quietly lower relevance.
    """
    if not results:
        return 0.0
    return max(float(r.score) for r in results)


def evidence_of(results, terms) -> tuple:
    """(largest single document coverage, the document that supplied it).

    Ties are broken by document identifier so that two documents covering the same share
    always yield the same attribution. Without that, the reported document would depend on
    retrieval order and two identical runs could explain themselves differently.
    """
    if not terms or not results:
        return 0.0, ""
    wanted = frozenset(terms)
    total = float(len(wanted))
    best_share = 0.0
    best_doc = ""
    for r in sorted(results, key=lambda r: r.doc_id):
        share = len(wanted & frozenset(r.terms)) / total
        if share > best_share:
            best_share = share
            best_doc = r.doc_id
    return best_share, best_doc


def _say(value: float) -> str:
    return "{0:.2f}".format(value)


def decide(terms, results, thresholds: Thresholds) -> Decision:
    """Sort one query into a zone.

    `terms` is the query's content terms, `results` the retrieval results for it. Both are
    plain sequences; the gate does not care where they came from.
    """
    relevance = relevance_of(results)
    evidence, support = evidence_of(results, terms)

    if not terms:
        return Decision(
            zone=Zone.EMPTY,
            relevance=relevance,
            evidence=0.0,
            support_doc_id="",
            reason="the question carries no content terms, so there is nothing to ground",
        )

    if relevance < thresholds.relevance_floor:
        return Decision(
            zone=Zone.EMPTY,
            relevance=relevance,
            evidence=evidence,
            support_doc_id=support,
            reason=(
                "best score " + _say(relevance) + " is under the relevance floor "
                + _say(thresholds.relevance_floor)
                + ", so nothing retrieved is about this question"
            ),
        )

    if evidence < thresholds.evidence_floor:
        return Decision(
            zone=Zone.AMBIGUOUS,
            relevance=relevance,
            evidence=evidence,
            support_doc_id=support,
            reason=(
                "best score " + _say(relevance) + " clears the relevance floor, but the "
                "best single document covers " + _say(evidence) + " of "
                + str(len(terms)) + " content terms, under the evidence floor "
                + _say(thresholds.evidence_floor)
            ),
        )

    return Decision(
        zone=Zone.ANSWERABLE,
        relevance=relevance,
        evidence=evidence,
        support_doc_id=support,
        reason=(
            "document " + support + " scores " + _say(relevance) + " and covers "
            + _say(evidence) + " of " + str(len(terms)) + " content terms, so both floors "
            "are clear"
        ),
    )
