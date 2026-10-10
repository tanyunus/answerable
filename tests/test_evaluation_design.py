"""The evaluation has to be able to fail. These tests guard the things that make it so."""

from __future__ import annotations

import copy
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))

from answerable import (  # noqa: E402
    LexicalIndex, content_terms, documents_from_records,
)
import run as runner  # noqa: E402


class EvaluationDesign(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.corpus, cls.queries = runner.load_fixtures()
        cls.floors = runner.derive_floors(cls.corpus, cls.queries)
        index = LexicalIndex(documents_from_records(cls.corpus))
        cls.signals = {
            item["query"]: runner._signals(index, item["query"])[2:]
            for item in cls.queries
        }

    def _relabel(self, half, old_zone, new_zone):
        changed = copy.deepcopy(self.queries)
        for item in changed:
            if item["set"] == half and item["expected_zone"] == old_zone:
                item["expected_zone"] = new_zone
                return changed
        self.fail("no question to relabel in " + half)

    def test_the_floors_are_read_off_the_calibration_half_only(self):
        """Relabelling a held out question leaves both floors where they were."""
        changed = self._relabel(runner.HELD_OUT, "ambiguous", "answerable")
        self.assertEqual(runner.derive_floors(self.corpus, changed), self.floors)

    def test_relabelling_a_calibration_question_does_move_a_floor(self):
        """Guards the test above: it would also pass if the floors ignored every label."""
        changed = self._relabel(runner.CALIBRATION, "empty", "ambiguous")
        self.assertNotEqual(runner.derive_floors(self.corpus, changed), self.floors)

    def test_some_questions_score_above_zero_and_under_the_relevance_floor(self):
        """Without these the relevance floor could hold any value under the weakest real
        match and the fixtures would not notice."""
        near = [q for q, (relevance, _) in self.signals.items()
                if 0.0 < relevance < self.floors.relevance_floor]
        self.assertGreaterEqual(len(near), 4)
        labelled = {item["query"]: item["expected_zone"] for item in self.queries}
        for query in near:
            self.assertEqual(labelled[query], "empty", query)

    def test_near_miss_questions_appear_in_both_halves(self):
        """A boundary case present only in calibration would not be held out at all."""
        halves = {item["set"] for item in self.queries
                  if 0.0 < self.signals[item["query"]][0] < self.floors.relevance_floor}
        self.assertEqual(halves, {runner.CALIBRATION, runner.HELD_OUT})

    def test_some_questions_cover_between_half_and_all_of_their_terms(self):
        """Without these the evidence floor could hold any value between 0.5 and 1.0."""
        between = sorted({round(evidence, 3)
                          for _, (_, evidence) in self.signals.items()
                          if 0.5 < evidence < 1.0})
        self.assertGreaterEqual(len(between), 3, between)

    def test_both_halves_contain_all_three_zones(self):
        for half in (runner.CALIBRATION, runner.HELD_OUT):
            zones = {item["expected_zone"] for item in self.queries
                     if item["set"] == half}
            self.assertEqual(zones, {"answerable", "ambiguous", "empty"}, half)

    def test_the_two_halves_are_of_similar_size(self):
        """A held out half much smaller than the calibration half would turn one wrong
        answer into a large swing in the headline number."""
        sizes = [len([i for i in self.queries if i["set"] == half])
                 for half in (runner.CALIBRATION, runner.HELD_OUT)]
        self.assertLessEqual(abs(sizes[0] - sizes[1]), max(sizes) // 4)

    def test_every_refusal_label_names_what_the_corpus_is_missing(self):
        """A label nobody can audit against the corpus is a label nobody audits. Eight of
        these were wrong at one point, and all eight made a refusal count as correct."""
        for item in self.queries:
            if item["expected_zone"] == "answerable":
                self.assertNotIn("absent", item, item["query"])
                continue
            self.assertIn("absent", item, item["query"])
            self.assertIn(":", item["absent"], item["query"])
            self.assertGreater(len(item["absent"]), 20, item["query"])

    def test_each_near_miss_question_shares_one_term_with_one_long_document(self):
        """The near-miss questions sit just under the relevance floor because they share a
        single term with the longest document, where one match is weak evidence. A second
        shared term, or a term from a short document, would lift them over the floor and
        the floor would stop being exercised."""
        corpus_terms = {}
        for doc in self.corpus:
            for term in content_terms(doc["title"] + " " + doc["text"]):
                corpus_terms.setdefault(term, set()).add(doc["doc_id"])
        near = [item for item in self.queries
                if 0.0 < self.signals[item["query"]][0] < self.floors.relevance_floor]
        self.assertGreaterEqual(len(near), 4)
        for item in near:
            shared = {t: corpus_terms[t] for t in content_terms(item["query"])
                      if t in corpus_terms}
            self.assertEqual(len(shared), 1, (item["query"], shared))
            self.assertEqual(list(shared.values())[0], {"d21"}, (item["query"], shared))

    def test_the_external_set_takes_no_part_in_either_floor(self):
        """The external set is only worth having if it never touched the floors. Deriving
        them from a corpus with the external questions appended to the labelled set must
        leave both floors where they were."""
        external = runner.load_external()
        intruders = [dict(item, set=runner.CALIBRATION, expected_zone="empty",
                          answerable_in_corpus=False, absent="planted by this test")
                     for item in external]
        self.assertEqual(runner.derive_floors(self.corpus, self.queries), self.floors)
        moved = runner.derive_floors(self.corpus, self.queries + intruders)
        self.assertNotEqual(moved, self.floors)

    def test_the_relevance_only_baseline_keeps_the_relevance_floor(self):
        """The baseline has to differ from the gate in exactly one floor, or it is not a
        comparison with the second signal removed."""
        base = runner.relevance_only(self.floors)
        self.assertEqual(base.relevance_floor, self.floors.relevance_floor)
        self.assertEqual(base.evidence_floor, 0.0)

    def test_the_external_set_does_not_affect_the_exit_status(self):
        """One external question reaches a generator with no answer in the corpus. The run
        reports it and still exits zero, because the external set is a measurement."""
        bundle = runner.run_all()
        leaked = [item["query"] for item, gate, _ in bundle["external"]
                  if gate.may_call_generator and item["answer_in"] == "none"]
        self.assertEqual(len(leaked), 1, leaked)
        proc = subprocess.run([sys.executable, str(ROOT / "eval" / "run.py")],
                              capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn(leaked[0], proc.stdout)

    def test_every_question_belongs_to_exactly_one_half(self):
        halves = {item["set"] for item in self.queries}
        self.assertEqual(halves, {runner.CALIBRATION, runner.HELD_OUT})
        self.assertEqual(len({item["query"] for item in self.queries}),
                         len(self.queries))


if __name__ == "__main__":
    unittest.main()
