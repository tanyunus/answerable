"""Run the gate over the fixture corpus and query set, and write eval/results.md.

This file holds all of the input and output. The decision path it calls into reads no
files and takes no arguments it was not given, which is what lets the same decision be
reproduced from a unit test with three lines of setup.

The thresholds live here and not in `src`, because a floor is a property of a corpus and a
retriever, not of the gate. Shipping a default would invite someone to keep it.

Usage:
    python3 eval/run.py                 run everything and rewrite eval/results.md
    python3 eval/run.py --digest-only   print the decision digest and exit
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from answerable import (  # noqa: E402  (path bootstrap has to come first)
    LexicalIndex, Thresholds, Zone, content_terms, decide, documents_from_records,
)

# Derived from the fixture signal distribution, not carried in from anywhere else. Each
# floor sits in an observed gap; `_floor_margins` below reports how wide the gap is, so a
# later change to the fixtures that narrows it shows up in the committed results.
THRESHOLDS = Thresholds(relevance_floor=0.10, evidence_floor=0.75)

# How many results the retriever hands the gate. Evidence is a per document maximum, so a
# deeper list can only raise it, never lower it.
RETRIEVAL_DEPTH = 5

ZONES = (Zone.ANSWERABLE, Zone.AMBIGUOUS, Zone.EMPTY)


def load_fixtures():
    corpus = json.loads((HERE / "corpus.json").read_text(encoding="utf-8"))
    queries = json.loads((HERE / "queries.json").read_text(encoding="utf-8"))
    return corpus, queries


def evaluate(corpus, queries):
    """One decision per query, in fixture order."""
    index = LexicalIndex(documents_from_records(corpus))
    out = []
    for item in queries:
        terms = content_terms(item["query"])
        results = index.search(terms, RETRIEVAL_DEPTH)
        out.append((item, decide(terms, results, THRESHOLDS)))
    return out


def digest(decisions) -> str:
    """A stable fingerprint of every decision.

    Formatted to six decimal places rather than hashing the floats directly: the point is
    to detect a changed decision, not to notice that two runs differ in the last bit of a
    sum carried out in a different order.
    """
    lines = [
        "\t".join([
            item["query"],
            d.zone.value,
            "{0:.6f}".format(d.relevance),
            "{0:.6f}".format(d.evidence),
            d.support_doc_id,
        ])
        for item, d in decisions
    ]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _zone_accuracy(decisions):
    rows = []
    for zone in ZONES:
        group = [(i, d) for i, d in decisions if i["expected_zone"] == zone.value]
        correct = sum(1 for i, d in group if d.zone is zone)
        rows.append((zone.value, len(group), correct))
    total = sum(r[1] for r in rows)
    correct = sum(r[2] for r in rows)
    rows.append(("all", total, correct))
    return rows


def _share(correct: int, total: int) -> str:
    if total == 0:
        return "n/a"
    pct = 100.0 * correct / total
    return "{0:.0f}%".format(pct) if pct == int(pct) else "{0:.1f}%".format(pct)


def _unanswerable_reaching_generator(decisions):
    without_answer = [(i, d) for i, d in decisions if not i["answerable_in_corpus"]]
    leaked = [i["query"] for i, d in without_answer if d.may_call_generator]
    return len(without_answer), leaked


def _floor_margins(decisions):
    """How much room each floor has on the fixtures.

    A floor whose nearest fixture sits a thousandth away is a floor that will move the
    first time the corpus changes. Reporting the gap makes that visible in the diff.
    """
    out = {}
    for name, floor, values in (
        ("relevance", THRESHOLDS.relevance_floor, [d.relevance for _, d in decisions]),
        ("evidence", THRESHOLDS.evidence_floor, [d.evidence for _, d in decisions]),
    ):
        below = [v for v in values if v < floor]
        above = [v for v in values if v >= floor]
        out[name] = (
            floor,
            max(below) if below else None,
            min(above) if above else None,
        )
    return out


def _cross_seed_digests(expected: str):
    """Rerun the whole evaluation in fresh processes with different hash seeds.

    Repeating the run inside one process cannot catch an ordering bug: PYTHONHASHSEED is
    fixed for the lifetime of a process, so a result that depends on set iteration order
    is perfectly stable until the next start. The seeds have to differ, which means
    separate processes.
    """
    seeds = ("0", "1", "2")
    results = []
    for seed in seeds:
        env = dict(os.environ)
        env["PYTHONHASHSEED"] = seed
        proc = subprocess.run(
            [sys.executable, str(HERE / "run.py"), "--digest-only"],
            capture_output=True, text=True, env=env, check=False,
        )
        results.append((seed, proc.stdout.strip(), proc.returncode))
    agree = all(code == 0 and out == expected for _, out, code in results)
    return seeds, results, agree


def _markdown(decisions, margins, seeds, agree, document_count) -> str:
    rows = _zone_accuracy(decisions)
    total_without_answer, leaked = _unanswerable_reaching_generator(decisions)

    lines = [
        "# Results",
        "",
        "Regenerated by `make eval`. There is no timestamp in this file, so an unchanged",
        "tree produces an empty diff and a changed decision produces a readable one.",
        "",
        "Fixtures: {0} documents, {1} labelled questions, retrieval depth {2}, "
        "relevance floor {3:.2f}, evidence floor {4:.2f}.".format(
            document_count, len(decisions), RETRIEVAL_DEPTH,
            THRESHOLDS.relevance_floor, THRESHOLDS.evidence_floor,
        ),
        "",
        "## Zone accuracy",
        "",
        "| zone | labelled questions | classified correctly | accuracy |",
        "|---|---|---|---|",
    ]
    for name, total, correct in rows:
        lines.append("| {0} | {1} | {2} | {3} |".format(
            name, total, correct, _share(correct, total)))

    lines += [
        "",
        "## The guarantee that matters",
        "",
        "Zone accuracy measures the three way classification. The property the gate exists",
        "to enforce is narrower: nothing the corpus cannot answer may reach a generator.",
        "",
        "| check | result |",
        "|---|---|",
        "| labelled questions with no answer in the corpus | {0} |".format(total_without_answer),
        "| of those, routed to a generator | {0} |".format(len(leaked)),
        "| decisions identical across hash seeds {0} | {1} |".format(
            ", ".join(seeds), "yes" if agree else "no"),
        "| decision digest | `{0}` |".format(digest(decisions)),
    ]
    if leaked:
        lines += ["", "Routed to a generator despite having no answer in the corpus:", ""]
        lines += ["- " + q for q in leaked]

    lines += [
        "",
        "## Floor margins",
        "",
        "The nearest fixture value on each side of each floor. A narrow gap means the floor",
        "is fitted to the fixtures rather than separated by them.",
        "",
        "| signal | floor | nearest value below | nearest value at or above |",
        "|---|---|---|---|",
    ]
    for name in ("relevance", "evidence"):
        floor, below, above = margins[name]
        lines.append("| {0} | {1:.2f} | {2} | {3} |".format(
            name, floor,
            "none" if below is None else "{0:.3f}".format(below),
            "none" if above is None else "{0:.3f}".format(above),
        ))

    lines += [
        "",
        "## Every decision",
        "",
        "| question | expected | decided | relevance | evidence | support |",
        "|---|---|---|---|---|---|",
    ]
    for item, d in decisions:
        lines.append("| {0} | {1} | {2} | {3:.3f} | {4:.2f} | {5} |".format(
            item["query"], item["expected_zone"], d.zone.value,
            d.relevance, d.evidence, d.support_doc_id or "none",
        ))

    return "\n".join(lines) + "\n"


def main(argv) -> int:
    corpus, queries = load_fixtures()
    decisions = evaluate(corpus, queries)
    own = digest(decisions)

    if "--digest-only" in argv:
        # No subprocess from here: this is the mode the cross seed check calls.
        print(own)
        return 0

    # Cheap in process check first. It cannot catch an ordering bug on its own, which is
    # why the cross seed check follows, but it does catch accidental state in the gate.
    repeated = {digest(evaluate(corpus, queries)) for _ in range(3)}
    seeds, seed_results, agree = _cross_seed_digests(own)

    margins = _floor_margins(decisions)
    (HERE / "results.md").write_text(
        _markdown(decisions, margins, seeds, agree, len(corpus)), encoding="utf-8")

    rows = _zone_accuracy(decisions)
    total_without_answer, leaked = _unanswerable_reaching_generator(decisions)
    for name, total, correct in rows:
        print("{0:<12} {1:>3} questions  {2:>3} correct  {3}".format(
            name, total, correct, _share(correct, total)))
    print()
    print("no answer in the corpus: {0}, routed to a generator: {1}".format(
        total_without_answer, len(leaked)))
    print("digest {0}".format(own))
    print("repeated in process: {0}".format(
        "identical" if repeated == {own} else "DIFFERENT"))
    print("hash seeds {0}: {1}".format(
        ", ".join(seeds), "identical" if agree else "DIFFERENT"))
    print("written: eval/results.md")

    failed = []
    if rows[-1][1] != rows[-1][2]:
        failed.append("{0} of {1} questions landed in the wrong zone".format(
            rows[-1][1] - rows[-1][2], rows[-1][1]))
    if leaked:
        failed.append("{0} questions with no answer reached a generator".format(len(leaked)))
    if repeated != {own}:
        failed.append("repeated runs in one process disagreed")
    if not agree:
        failed.append("runs under different hash seeds disagreed: {0}".format(
            [(s, o or "error", c) for s, o, c in seed_results]))
    if failed:
        print()
        for line in failed:
            print("FAILED: " + line)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
