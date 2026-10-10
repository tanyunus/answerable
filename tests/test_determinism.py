"""The same inputs must produce the same decision, in this process and in the next one."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))

from answerable import LexicalIndex, content_terms, decide, documents_from_records  # noqa: E402
import run as runner  # noqa: E402


class Determinism(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.corpus, cls.queries = runner.load_fixtures()
        cls.floors = runner.derive_floors(cls.corpus, cls.queries)

    def test_deciding_the_same_question_twice_gives_the_same_answer(self):
        """No hidden state accumulates between calls."""
        index = LexicalIndex(documents_from_records(self.corpus))
        terms = content_terms("what is the hardness of thornodite")
        first = decide(terms, index.search(terms, runner.RETRIEVAL_DEPTH), self.floors)
        second = decide(terms, index.search(terms, runner.RETRIEVAL_DEPTH), self.floors)
        self.assertEqual(first, second)

    def test_running_the_whole_evaluation_repeatedly_gives_one_digest(self):
        """Rebuilding the index from scratch changes nothing."""
        digests = {runner.digest(runner.evaluate(self.corpus, self.queries, self.floors))
                   for _ in range(5)}
        self.assertEqual(len(digests), 1)

    def test_the_decisions_do_not_depend_on_the_order_documents_were_supplied(self):
        """Reversing the corpus changes neither a score nor a zone."""
        forward = runner.digest(runner.evaluate(self.corpus, self.queries, self.floors))
        reversed_corpus = list(reversed(self.corpus))
        backward = runner.digest(runner.evaluate(reversed_corpus, self.queries,
                                         runner.derive_floors(reversed_corpus, self.queries)))
        self.assertEqual(forward, backward)

    def test_documents_with_identical_content_are_ranked_in_a_stable_order(self):
        """Equal scores need a second sort key. The fixture questions happen to produce
        no ties, so this builds one instead of assuming the corpus will keep providing
        the case."""
        records = [
            {"doc_id": "d02", "title": "Entry", "text": "The hardness of velmarite is 4.5."},
            {"doc_id": "d01", "title": "Entry", "text": "The hardness of velmarite is 4.5."},
        ]
        terms = content_terms("what is the hardness of velmarite")
        forward = LexicalIndex(documents_from_records(records)).search(terms, 5)
        backward = LexicalIndex(
            documents_from_records(list(reversed(records)))).search(terms, 5)
        self.assertEqual([r.score for r in forward], [r.score for r in backward])
        self.assertEqual([r.doc_id for r in forward], ["d01", "d02"])
        self.assertEqual([r.doc_id for r in backward], ["d01", "d02"])

    def test_the_evaluation_gives_the_same_digest_under_different_hash_seeds(self):
        """Repeating inside one process cannot catch this: the hash seed is fixed per
        process, so an iteration order bug stays stable until the next start."""
        digests = set()
        for seed in ("0", "1", "2", "7"):
            env = dict(os.environ)
            env["PYTHONHASHSEED"] = seed
            proc = subprocess.run(
                [sys.executable, str(ROOT / "eval" / "run.py"), "--digest-only"],
                capture_output=True, text=True, env=env, check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            digests.add(proc.stdout.strip())
        self.assertEqual(len(digests), 1, digests)

    def test_the_committed_results_file_matches_a_fresh_run(self):
        """`eval/results.md` is checked in, so it has to be the output of the code
        beside it and not a snapshot of an older one."""
        fresh = runner.digest(runner.evaluate(self.corpus, self.queries, self.floors))
        committed = (ROOT / "eval" / "results.md").read_text(encoding="utf-8")
        self.assertIn(fresh, committed)


if __name__ == "__main__":
    unittest.main()
