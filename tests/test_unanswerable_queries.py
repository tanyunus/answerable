"""The cases the gate exists for: questions that must not reach a generator."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))

from answerable import (  # noqa: E402
    Decision, LexicalIndex, Thresholds, Zone, content_terms, decide,
    documents_from_records,
)
import run as runner  # noqa: E402  (eval/run.py, for the fixtures and the floors)


def decide_fixture_question(index, question, floors):
    terms = content_terms(question)
    return decide(terms, index.search(terms, runner.RETRIEVAL_DEPTH), floors)


class UnanswerableQuestions(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        corpus, cls.queries = runner.load_fixtures()
        cls.index = LexicalIndex(documents_from_records(corpus))
        cls.floors = runner.derive_floors(corpus, cls.queries)

    def test_every_fixture_question_without_an_answer_is_kept_away_from_the_generator(self):
        """This is the guarantee. Everything else in the repository serves it."""
        leaked = []
        for item in self.queries:
            if item["answerable_in_corpus"]:
                continue
            if decide_fixture_question(self.index, item["query"], self.floors).may_call_generator:
                leaked.append(item["query"])
        self.assertEqual(leaked, [])

    def test_the_fixtures_contain_questions_with_no_answer_in_the_corpus(self):
        """Guards the test above: it cannot pass by having nothing to check."""
        without = [i for i in self.queries if not i["answerable_in_corpus"]]
        self.assertGreaterEqual(len(without), 10)

    def test_the_gate_lets_questions_through_and_only_answerable_ones(self):
        """Guards the test above from the other side, in two parts. A gate that refuses
        everything would satisfy the guarantee and be useless, so some questions have to
        get through. Every one that does must have an answer in the corpus."""
        allowed = [i for i in self.queries
                   if decide_fixture_question(
                       self.index, i["query"], self.floors).may_call_generator]
        self.assertGreaterEqual(len(allowed), 15)
        for item in allowed:
            self.assertTrue(item["answerable_in_corpus"], item["query"])

    def test_a_question_about_a_subject_the_corpus_never_mentions_is_empty(self):
        """No lexical anchor at all means no documents are worth showing either."""
        decision = decide_fixture_question(self.index, "how do I reset my password", self.floors)
        self.assertIs(decision.zone, Zone.EMPTY)

    def test_a_question_naming_a_known_subject_but_an_unrecorded_fact_is_ambiguous(self):
        """The subject exists, the asked fact does not, so the documents may be shown."""
        decision = decide_fixture_question(self.index, "is quelbrite toxic", self.floors)
        self.assertIs(decision.zone, Zone.AMBIGUOUS)
        self.assertFalse(decision.may_call_generator)

    def test_a_question_with_no_retrieval_results_at_all_is_refused(self):
        """An empty result list is a normal input, not an error."""
        decision = decide(("chess",), [], Thresholds(0.10, 0.75))
        self.assertIs(decision.zone, Zone.EMPTY)
        self.assertEqual(decision.relevance, 0.0)

    def test_a_question_made_only_of_function_words_is_refused(self):
        """Nothing was asked, so nothing can be grounded."""
        self.assertEqual(content_terms("what is it about"), ())
        decision = decide_fixture_question(self.index, "what is it about", self.floors)
        self.assertIs(decision.zone, Zone.EMPTY)

    def test_only_the_answerable_zone_reports_that_a_generator_may_be_called(self):
        """Checks the permission directly, for every zone, not through a worked example."""
        allowed = {
            zone: Decision(zone=zone, relevance=1.0, evidence=1.0,
                           support_doc_id="d01", reason="constructed for this test")
            .may_call_generator
            for zone in Zone
        }
        self.assertEqual(allowed, {Zone.ANSWERABLE: True,
                                   Zone.AMBIGUOUS: False,
                                   Zone.EMPTY: False})

    def test_the_corpus_and_the_query_set_agree_on_what_is_being_tested(self):
        """A labelled set that drifted from the corpus would measure nothing."""
        corpus = json.loads((ROOT / "eval" / "corpus.json").read_text(encoding="utf-8"))
        self.assertEqual(len({d["doc_id"] for d in corpus}), len(corpus))
        for item in self.queries:
            self.assertIn(item["expected_zone"], {z.value for z in Zone})
            self.assertIsInstance(item["answerable_in_corpus"], bool)


if __name__ == "__main__":
    unittest.main()
