"""Derive the floors from the calibration half, score the held-out half, write results.md.

This file holds all of the input and output. The decision path it calls into reads no files
and takes no arguments it was not given, so the same decision can be reproduced from a unit
test with three lines of setup.

WHY THE SET IS SPLIT. A floor read off a set of questions will separate that set, so
reporting accuracy on it measures almost nothing. The labelled set is split in two. Both
floors come from the calibration half alone. The headline numbers come from the held-out
half, which took no part in choosing them.

There is no circularity in the derivation: the two signals are computed from retrieval
results and do not depend on the floors, so the signals come first and each floor is then
placed midway between the two groups it has to separate.

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
    evidence_of, relevance_of,
)

# How many results the retriever hands the gate. Evidence is a per document maximum, so a
# deeper list can only raise it, never lower it.
RETRIEVAL_DEPTH = 5

CALIBRATION = "calibration"
HELD_OUT = "held_out"
ZONES = (Zone.ANSWERABLE, Zone.AMBIGUOUS, Zone.EMPTY)


def load_fixtures():
    corpus = json.loads((HERE / "corpus.json").read_text(encoding="utf-8"))
    queries = json.loads((HERE / "queries.json").read_text(encoding="utf-8"))
    return corpus, queries


def _signals(index, question):
    terms = content_terms(question)
    results = index.search(terms, RETRIEVAL_DEPTH)
    return terms, results, relevance_of(results), evidence_of(results, terms)[0]


def _midpoint(below: float, above: float) -> float:
    """Halfway between the highest value a floor must refuse and the lowest it must pass.

    A negative gap would mean the two groups overlap and that no floor separates them. The
    midpoint is still returned in that case, and the margins table makes the overlap
    visible instead of hiding it behind a number that looks fitted.
    """
    return round((below + above) / 2.0, 3)


def derive_floors(corpus, queries) -> Thresholds:
    """Both floors, read off the calibration half only.

    The relevance floor separates the questions labelled empty from everything else. The
    evidence floor separates ambiguous from answerable, and the empty questions take no
    part in it: their zone is already settled by relevance.
    """
    index = LexicalIndex(documents_from_records(corpus))
    relevance_empty, relevance_rest = [], []
    evidence_ambiguous, evidence_answerable = [], []
    for item in queries:
        if item["set"] != CALIBRATION:
            continue
        _, _, relevance, evidence = _signals(index, item["query"])
        if item["expected_zone"] == Zone.EMPTY.value:
            relevance_empty.append(relevance)
            continue
        relevance_rest.append(relevance)
        if item["expected_zone"] == Zone.AMBIGUOUS.value:
            evidence_ambiguous.append(evidence)
        else:
            evidence_answerable.append(evidence)
    return Thresholds(
        relevance_floor=_midpoint(max(relevance_empty), min(relevance_rest)),
        evidence_floor=_midpoint(max(evidence_ambiguous), min(evidence_answerable)),
    )


def evaluate(corpus, queries, floors):
    """One decision per question, in fixture order, over both halves of the set."""
    index = LexicalIndex(documents_from_records(corpus))
    out = []
    for item in queries:
        terms, results, _, _ = _signals(index, item["query"])
        out.append((item, decide(terms, results, floors)))
    return out


def digest(decisions) -> str:
    """A stable fingerprint of every decision.

    Formatted to six decimal places and not hashed from the floats directly: the point is
    to detect a changed decision, and not to notice that two runs differ in the last bit
    of a sum carried out in a different order.
    """
    lines = [
        "\t".join([
            item["query"],
            item["set"],
            d.zone.value,
            "{0:.6f}".format(d.relevance),
            "{0:.6f}".format(d.evidence),
            d.support_doc_id,
        ])
        for item, d in decisions
    ]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _subset(decisions, set_name):
    return [(i, d) for i, d in decisions if i["set"] == set_name]


def _zone_accuracy(decisions):
    rows = []
    for zone in ZONES:
        group = [(i, d) for i, d in decisions if i["expected_zone"] == zone.value]
        rows.append((zone.value, len(group), sum(1 for _, d in group if d.zone is zone)))
    rows.append(("all", sum(r[1] for r in rows), sum(r[2] for r in rows)))
    return rows


def _share(correct: int, total: int) -> str:
    if total == 0:
        return "n/a"
    pct = 100.0 * correct / total
    return "{0:.0f}%".format(pct) if pct == int(pct) else "{0:.1f}%".format(pct)


def _without_answer(decisions):
    group = [(i, d) for i, d in decisions if not i["answerable_in_corpus"]]
    return len(group), [i["query"] for i, d in group if d.may_call_generator]


def _misses(decisions):
    return [(i["query"], i["set"], i["expected_zone"], d.zone.value)
            for i, d in decisions if d.zone.value != i["expected_zone"]]


def _margins(decisions, floors):
    """The nearest value on each side of each floor, per half of the set.

    The calibration columns say how wide the gap the floor was placed in was. The held-out
    columns are the real test: a floor that separates one half and not the other was
    fitted to the half it came from.

    Evidence margins cover only the questions that cleared the relevance floor. For a
    question in the empty zone the evidence value had no part in the outcome, and counting
    it would make the gap look wider than it is.
    """
    out = {}
    for name in ("relevance", "evidence"):
        floor = getattr(floors, name + "_floor")
        row = {}
        for set_name in (CALIBRATION, HELD_OUT):
            if name == "relevance":
                values = [d.relevance for _, d in _subset(decisions, set_name)]
            else:
                values = [d.evidence for _, d in _subset(decisions, set_name)
                          if d.relevance >= floors.relevance_floor]
            below = [v for v in values if v < floor]
            above = [v for v in values if v >= floor]
            row[set_name] = (max(below) if below else None,
                             min(above) if above else None)
        out[name] = (floor, row)
    return out


def _accuracy_table(decisions, heading):
    lines = [heading, "",
             "| zone | labelled questions | classified correctly | accuracy |",
             "|---|---|---|---|"]
    for name, total, correct in _zone_accuracy(decisions):
        lines.append("| {0} | {1} | {2} | {3} |".format(
            name, total, correct, _share(correct, total)))
    return lines


def _value(v):
    return "none" if v is None else "{0:.3f}".format(v)


def _markdown(decisions, floors, seeds, agree, document_count) -> str:
    held = _subset(decisions, HELD_OUT)
    calib = _subset(decisions, CALIBRATION)
    held_total, held_leaked = _without_answer(held)
    all_total, all_leaked = _without_answer(decisions)

    lines = [
        "# Results",
        "",
        "Regenerated by `make eval`. There is no timestamp in this file, so an unchanged",
        "tree produces an empty diff and a changed decision produces a readable one.",
        "",
        "Fixtures: {0} documents, {1} labelled questions ({2} calibration, {3} held out), "
        "retrieval depth {4}.".format(
            document_count, len(decisions), len(calib), len(held), RETRIEVAL_DEPTH),
        "",
        "Floors, both read off the calibration half alone: relevance {0:.3f}, evidence "
        "{1:.3f}. The held-out half took no part in choosing them.".format(
            floors.relevance_floor, floors.evidence_floor),
        "",
    ]

    lines += _accuracy_table(held, "## Held out results")
    lines += [
        "",
        "Zone accuracy measures the three-way classification. The property the gate exists",
        "to enforce is narrower: nothing the corpus cannot answer may reach a generator.",
        "",
        "| check | result |",
        "|---|---|",
        "| held-out questions with no answer in the corpus | {0} |".format(held_total),
        "| of those, routed to a generator | {0} |".format(len(held_leaked)),
        "| across both halves, questions with no answer | {0} |".format(all_total),
        "| of those, routed to a generator | {0} |".format(len(all_leaked)),
        "| decisions identical across hash seeds {0} | {1} |".format(
            ", ".join(seeds), "yes" if agree else "no"),
        "| decision digest | `{0}` |".format(digest(decisions)),
        "",
    ]
    lines += _accuracy_table(calib, "## Calibration results")
    lines += [
        "",
        "These are the questions the floors were read off, so this table is not evidence",
        "of anything beyond internal consistency. It is here because a large gap between",
        "it and the held-out table would be the signature of an overfitted floor.",
        "",
        "## Floor margins",
        "",
        "| signal | floor | calibration below | calibration at or above | held-out below | held-out at or above |",
        "|---|---|---|---|---|---|",
    ]
    for name, (floor, row) in _margins(decisions, floors).items():
        lines.append("| {0} | {1:.3f} | {2} | {3} | {4} | {5} |".format(
            name, floor,
            _value(row[CALIBRATION][0]), _value(row[CALIBRATION][1]),
            _value(row[HELD_OUT][0]), _value(row[HELD_OUT][1])))

    missed = _misses(decisions)
    lines += ["", "## Questions in the wrong zone", ""]
    if missed:
        lines += ["| question | half | labelled | decided |", "|---|---|---|---|"]
        lines += ["| {0} | {1} | {2} | {3} |".format(*m) for m in missed]
    else:
        lines.append("None.")

    lines += [
        "",
        "## Every decision",
        "",
        "| question | half | labelled | decided | relevance | evidence | support |",
        "|---|---|---|---|---|---|---|",
    ]
    for item, d in decisions:
        lines.append("| {0} | {1} | {2} | {3} | {4:.3f} | {5:.3f} | {6} |".format(
            item["query"], item["set"], item["expected_zone"], d.zone.value,
            d.relevance, d.evidence, d.support_doc_id or "none"))

    return "\n".join(lines) + "\n"


def _cross_seed_digests(expected: str):
    """Rerun the whole evaluation in fresh processes with different hash seeds.

    Repeating the run inside one process cannot catch an ordering bug. PYTHONHASHSEED is
    fixed for the lifetime of a process, so a result that depends on set iteration order
    stays stable until the next start. The seeds have to differ, which means separate
    processes.
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
    return seeds, results, all(c == 0 and o == expected for _, o, c in results)


def main(argv) -> int:
    corpus, queries = load_fixtures()
    floors = derive_floors(corpus, queries)
    decisions = evaluate(corpus, queries, floors)
    own = digest(decisions)

    if "--digest-only" in argv:
        # No subprocess from here: this is the mode the cross seed check calls.
        print(own)
        return 0

    # Cheap in process check first. On its own it cannot catch an ordering bug, which is
    # why the cross seed check follows, but it does catch accidental state in the gate.
    repeated = {digest(evaluate(corpus, queries, floors)) for _ in range(3)}
    seeds, seed_results, agree = _cross_seed_digests(own)

    (HERE / "results.md").write_text(
        _markdown(decisions, floors, seeds, agree, len(corpus)), encoding="utf-8")

    held = _subset(decisions, HELD_OUT)
    held_total, held_leaked = _without_answer(held)
    all_total, all_leaked = _without_answer(decisions)

    print("floors from calibration only: relevance {0:.3f}, evidence {1:.3f}".format(
        floors.relevance_floor, floors.evidence_floor))
    print()
    print("HELD OUT ({0} questions)".format(len(held)))
    for name, total, correct in _zone_accuracy(held):
        print("  {0:<12} {1:>3} questions  {2:>3} correct  {3}".format(
            name, total, correct, _share(correct, total)))
    print("  no answer in the corpus: {0}, routed to a generator: {1}".format(
        held_total, len(held_leaked)))
    print()
    calib = _subset(decisions, CALIBRATION)
    print("CALIBRATION ({0} questions, the floors came from these)".format(len(calib)))
    for name, total, correct in _zone_accuracy(calib):
        print("  {0:<12} {1:>3} questions  {2:>3} correct  {3}".format(
            name, total, correct, _share(correct, total)))
    print()
    for query, half, labelled, decided in _misses(decisions):
        print("wrong zone [{0}] {1}: labelled {2}, decided {3}".format(
            half, query, labelled, decided))
    print("digest {0}".format(own))
    print("repeated in process: {0}".format(
        "identical" if repeated == {own} else "DIFFERENT"))
    print("hash seeds {0}: {1}".format(
        ", ".join(seeds), "identical" if agree else "DIFFERENT"))
    print("written: eval/results.md")

    # Zone accuracy is a measurement and is reported as it comes. These three are
    # guarantees, and a run that breaks one of them is a failed run.
    failed = []
    if all_leaked:
        failed.append("{0} questions with no answer reached a generator: {1}".format(
            len(all_leaked), all_leaked))
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
