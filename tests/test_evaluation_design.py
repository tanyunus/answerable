"""The evaluation has to be able to fail. These tests guard the things that make it so."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))

from answerable import LexicalIndex, documents_from_records  # noqa: E402
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

    def test_every_question_belongs_to_exactly_one_half(self):
        halves = {item["set"] for item in self.queries}
        self.assertEqual(halves, {runner.CALIBRATION, runner.HELD_OUT})
        self.assertEqual(len({item["query"] for item in self.queries}),
                         len(self.queries))


if __name__ == "__main__":
    unittest.main()
