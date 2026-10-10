"""What a pair of floors may be. The floors themselves live in eval/run.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from answerable import Retrieved, Thresholds, Zone, decide  # noqa: E402


class ThresholdValues(unittest.TestCase):

    def test_a_relevance_floor_above_one_is_accepted_for_retrievers_scoring_above_one(self):
        """The relevance floor is on the retriever's own scale, which has no upper bound."""
        floors = Thresholds(relevance_floor=12.5, evidence_floor=0.75)
        decision = decide(
            ("hardness", "velmarite"),
            [Retrieved(doc_id="d01", score=14.0,
                       terms=frozenset(("hardness", "velmarite")))],
            floors,
        )
        self.assertIs(decision.zone, Zone.ANSWERABLE)

    def test_a_score_under_a_relevance_floor_above_one_is_still_refused(self):
        """Accepting a larger floor does not stop it being a floor."""
        floors = Thresholds(relevance_floor=12.5, evidence_floor=0.75)
        decision = decide(
            ("hardness", "velmarite"),
            [Retrieved(doc_id="d01", score=9.0,
                       terms=frozenset(("hardness", "velmarite")))],
            floors,
        )
        self.assertIs(decision.zone, Zone.EMPTY)

    def test_a_negative_relevance_floor_is_accepted_for_rerankers_that_score_below_zero(self):
        """A reranker emitting a logit scores below zero for most of what it sees, so the
        useful cut can be a negative number."""
        floors = Thresholds(relevance_floor=-1.5, evidence_floor=0.75)
        terms = ("hardness", "velmarite")
        result = [Retrieved(doc_id="d01", score=-0.8,
                            terms=frozenset(("hardness", "velmarite")))]
        self.assertIs(decide(terms, result, floors).zone, Zone.ANSWERABLE)

    def test_a_score_under_a_negative_relevance_floor_is_still_refused(self):
        """A negative floor is still a floor."""
        floors = Thresholds(relevance_floor=-1.5, evidence_floor=0.75)
        result = [Retrieved(doc_id="d01", score=-2.4,
                            terms=frozenset(("hardness", "velmarite")))]
        self.assertIs(decide(("hardness", "velmarite"), result, floors).zone, Zone.EMPTY)

    def test_a_relevance_floor_that_is_not_a_finite_number_is_rejected(self):
        """An infinite floor would refuse everything silently."""
        for bad in (float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                Thresholds(relevance_floor=bad, evidence_floor=0.75)

    def test_a_question_with_nothing_retrieved_is_refused_whatever_the_floors_are(self):
        """An empty result list cannot support an answer and has no documents to show, so
        it is refused even by a floor low enough that every score clears it."""
        for floor in (-1.5, 0.0, 0.10, 12.5):
            decision = decide(("chess",), [], Thresholds(relevance_floor=floor,
                                                         evidence_floor=0.75))
            self.assertIs(decision.zone, Zone.EMPTY, floor)
            self.assertFalse(decision.may_call_generator, floor)

    def test_an_evidence_floor_above_one_is_rejected_because_coverage_is_a_share(self):
        """Coverage cannot exceed every term being covered, so neither can its floor."""
        with self.assertRaises(ValueError):
            Thresholds(relevance_floor=0.10, evidence_floor=1.5)

    def test_a_negative_evidence_floor_is_rejected(self):
        with self.assertRaises(ValueError):
            Thresholds(relevance_floor=0.10, evidence_floor=-0.25)


if __name__ == "__main__":
    unittest.main()
