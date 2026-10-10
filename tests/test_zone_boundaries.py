"""Each test name states the guarantee. The mechanism is in src/answerable/gate.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from answerable import Retrieved, Thresholds, Zone, decide  # noqa: E402

FLOORS = Thresholds(relevance_floor=0.50, evidence_floor=0.50)


def found(doc_id, score, terms):
    """One retrieval result, written out by hand so no corpus is involved."""
    return Retrieved(doc_id=doc_id, score=score, terms=frozenset(terms))


class ZoneBoundaries(unittest.TestCase):

    def test_a_question_one_document_fully_covers_may_reach_the_generator(self):
        """A well matched question whose terms are all in one document is answerable."""
        decision = decide(
            ("hardness", "velmarite"),
            [found("d01", 0.80, ("hardness", "velmarite", "scale"))],
            FLOORS,
        )
        self.assertIs(decision.zone, Zone.ANSWERABLE)
        self.assertTrue(decision.may_call_generator)

    def test_a_question_whose_topic_is_present_but_whose_asked_fact_is_missing_is_held_back(self):
        """A high score on the right subject does not make a missing fact answerable."""
        decision = decide(
            ("hardness", "thornodite"),
            [found("d02", 0.90, ("thornodite", "crystals", "ridges"))],
            Thresholds(relevance_floor=0.50, evidence_floor=0.75),
        )
        self.assertIs(decision.zone, Zone.AMBIGUOUS)
        self.assertFalse(decision.may_call_generator)

    def test_a_question_nothing_matches_is_refused_without_offering_a_document(self):
        """When the best score is under the relevance floor the question is empty."""
        decision = decide(
            ("spectrometer", "calibrate"),
            [found("d04", 0.04, ("density", "scarp"))],
            FLOORS,
        )
        self.assertIs(decision.zone, Zone.EMPTY)
        self.assertFalse(decision.may_call_generator)

    def test_a_score_exactly_on_the_relevance_floor_counts_as_clearing_it(self):
        """The relevance floor is inclusive, so a borderline query is not refused twice."""
        decision = decide(
            ("hardness", "velmarite"),
            [found("d01", 0.50, ("hardness", "velmarite"))],
            FLOORS,
        )
        self.assertIs(decision.zone, Zone.ANSWERABLE)

    def test_a_score_just_under_the_relevance_floor_is_refused(self):
        """The floor is a floor: just below it is below it."""
        decision = decide(
            ("hardness", "velmarite"),
            [found("d01", 0.49, ("hardness", "velmarite"))],
            FLOORS,
        )
        self.assertIs(decision.zone, Zone.EMPTY)

    def test_coverage_exactly_on_the_evidence_floor_counts_as_clearing_it(self):
        """The evidence floor is inclusive on the same reasoning as the relevance floor."""
        decision = decide(
            ("hardness", "velmarite"),
            [found("d01", 0.80, ("velmarite", "green"))],
            Thresholds(relevance_floor=0.50, evidence_floor=0.50),
        )
        self.assertIs(decision.zone, Zone.ANSWERABLE)
        self.assertEqual(decision.evidence, 0.50)

    def test_coverage_just_under_the_evidence_floor_is_held_back(self):
        """One of three terms covered is not enough when two thirds are required."""
        decision = decide(
            ("hardness", "market", "velmarite"),
            [found("d01", 0.80, ("velmarite", "green"))],
            Thresholds(relevance_floor=0.50, evidence_floor=0.66),
        )
        self.assertIs(decision.zone, Zone.AMBIGUOUS)

    def test_terms_covered_half_each_by_two_documents_do_not_count_as_covered(self):
        """Evidence is per document, so two half matches never add up to a whole one."""
        decision = decide(
            ("hardness", "thornodite"),
            [found("d02", 0.90, ("thornodite", "ridges")),
             found("d14", 0.70, ("hardness", "scale"))],
            Thresholds(relevance_floor=0.50, evidence_floor=0.75),
        )
        self.assertIs(decision.zone, Zone.AMBIGUOUS)
        self.assertEqual(decision.evidence, 0.50)

    def test_raising_the_relevance_floor_can_turn_an_answerable_question_empty(self):
        """Tightening the relevance floor costs recall, and the cost is silent."""
        results = [found("d01", 0.60, ("hardness", "velmarite"))]
        terms = ("hardness", "velmarite")
        self.assertIs(decide(terms, results, Thresholds(0.50, 0.50)).zone, Zone.ANSWERABLE)
        self.assertIs(decide(terms, results, Thresholds(0.70, 0.50)).zone, Zone.EMPTY)

    def test_raising_the_evidence_floor_can_turn_an_answerable_question_ambiguous(self):
        """Tightening the evidence floor trades answer rate for grounding."""
        results = [found("d01", 0.90, ("velmarite", "green"))]
        terms = ("hardness", "velmarite")
        self.assertIs(decide(terms, results, Thresholds(0.50, 0.50)).zone, Zone.ANSWERABLE)
        self.assertIs(decide(terms, results, Thresholds(0.50, 0.75)).zone, Zone.AMBIGUOUS)

    def test_a_refusal_says_which_floor_the_question_fell_short_of(self):
        """A refusal nobody can review is a refusal nobody can tune."""
        empty = decide(("chess",), [found("d01", 0.10, ("velmarite",))], FLOORS)
        held = decide(("hardness", "thornodite"),
                      [found("d02", 0.90, ("thornodite",))],
                      Thresholds(0.50, 0.75))
        self.assertIn("relevance floor", empty.reason)
        self.assertIn("evidence floor", held.reason)

    def test_the_document_credited_with_the_coverage_is_named(self):
        """The caller can show its work, and two equal documents are resolved the same way."""
        decision = decide(
            ("hardness", "velmarite"),
            [found("d09", 0.70, ("hardness", "velmarite")),
             found("d01", 0.70, ("hardness", "velmarite"))],
            FLOORS,
        )
        self.assertEqual(decision.support_doc_id, "d01")


if __name__ == "__main__":
    unittest.main()
