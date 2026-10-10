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


def load_external():
    """The external question set.

    Written from the corpus alone by a model that never saw the floors, the gate or
    `queries.json`. It takes no part in deriving a floor and no part in the exit status. Its
    job is to answer a question the labelled set cannot: the labelled set was written by the
    same hand as the corpus and the floors, so it cannot say what happens to questions
    phrased by someone else.
    """
    return json.loads((HERE / "external.json").read_text(encoding="utf-8"))


def relevance_only(floors: Thresholds) -> Thresholds:
    """The one signal baseline: same relevance floor, evidence floor at zero.

    Coverage is never below zero, so every query that clears the relevance floor becomes
    answerable. This is what the gate would be with the second signal removed, and it is the
    comparison that says what the second signal buys.
    """
    return Thresholds(relevance_floor=floors.relevance_floor, evidence_floor=0.0)


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


def evaluate_external(corpus, external, floors):
    """One decision per external question, under the gate and under the baseline.

    Returns [(item, gate decision, baseline decision)]. Both go through `decide`, so the
    baseline is the real code path with one floor lowered and not a reimplementation of the
    comparison.
    """
    index = LexicalIndex(documents_from_records(corpus))
    baseline = relevance_only(floors)
    out = []
    for item in external:
        terms, results, _, _ = _signals(index, item["query"])
        out.append((item, decide(terms, results, floors),
                    decide(terms, results, baseline)))
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
            item.get("set") or item.get("kind") or "",
            d.zone.value,
            "{0:.6f}".format(d.relevance),
            "{0:.6f}".format(d.evidence),
            d.support_doc_id,
        ])
        for item, d in decisions
    ]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def run_all(floors=None):
    """Everything this evaluation decides, in one place.

    The runner, the fingerprint and the tests all read this, so a number reported in one of
    them cannot drift from the same number in another.
    """
    corpus, queries = load_fixtures()
    external = load_external()
    if floors is None:
        floors = derive_floors(corpus, queries)
    baseline = relevance_only(floors)
    return {
        "corpus": corpus,
        "queries": queries,
        "floors": floors,
        "baseline": baseline,
        "labelled": evaluate(corpus, queries, floors),
        "labelled_baseline": evaluate(corpus, queries, baseline),
        "external": evaluate_external(corpus, external, floors),
    }


def full_digest(bundle) -> str:
    """One fingerprint over every decision of the run, gate and baseline, both sets.

    Tagged by which pass produced each row, so a gate decision and a baseline decision on
    the same question cannot collide and cancel out.
    """
    rows = []
    for item, d in bundle["labelled"]:
        rows.append(("labelled " + item["set"], item["query"], d))
    for item, d in bundle["labelled_baseline"]:
        rows.append(("baseline " + item["set"], item["query"], d))
    for item, gate, base in bundle["external"]:
        rows.append(("external " + item["kind"], item["query"], gate))
        rows.append(("external baseline " + item["kind"], item["query"], base))
    lines = ["\t".join([tag, query, d.zone.value,
                        "{0:.6f}".format(d.relevance), "{0:.6f}".format(d.evidence),
                        d.support_doc_id])
             for tag, query, d in rows]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _routed(rows, pick):
    """(questions, routed by the gate, routed by relevance alone) over the given rows."""
    chosen = [r for r in rows if pick(r[0])]
    return len(chosen), sum(1 for r in chosen if r[1].may_call_generator), \
        sum(1 for r in chosen if r[2].may_call_generator)


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


def _markdown(decisions, baseline_decisions, external, floors, seeds, agree,
              document_count, fingerprint) -> str:
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
        "| decision digest | `{0}` |".format(fingerprint),
        "",
    ]
    lines += _accuracy_table(calib, "## Calibration results")
    lines += [
        "",
        "These are the questions the floors were read off, so this table is not evidence",
        "of anything beyond internal consistency. It is here because a large gap between",
        "it and the held-out table would be the signature of an overfitted floor.",
        "",
        "## What the second signal buys",
        "",
        "A one signal baseline beside the gate: the same relevance floor, and the evidence",
        "floor at 0.0. Coverage is never below zero, so under that baseline every query",
        "clearing the relevance floor is answerable. This is the gate with its second signal",
        "removed.",
        "",
        "| set | questions | routed by the gate | routed by relevance alone |",
        "|---|---|---|---|",
    ]
    rows_lab = [(i, g, b) for (i, g), b in zip(decisions, [d for _, d in baseline_decisions])]
    for label, pick in (
        ("labelled, no answer in the corpus", lambda i: not i["answerable_in_corpus"]),
        ("labelled, answerable", lambda i: i["answerable_in_corpus"]),
    ):
        lines.append("| {0} | {1} | {2} | {3} |".format(label, *_routed(rows_lab, pick)))
    for label, pick in (
        ("external, no answer in the corpus", lambda i: i["answer_in"] == "none"),
        ("external, answerable from one document", lambda i: i["answer_in"] == "one_document"),
        ("external, answerable from two documents", lambda i: i["answer_in"] == "two_documents"),
    ):
        lines.append("| {0} | {1} | {2} | {3} |".format(label, *_routed(external, pick)))

    lines += [
        "",
        "## External question set",
        "",
        "Thirty questions written from the corpus alone by a model that never saw the floors,",
        "the gate or `queries.json`. The set takes no part in deriving a floor and no part in",
        "the exit status. It answers a question the labelled set cannot: every labelled",
        "question was written by the same hand as the corpus and the floors, so none of them",
        "says what happens to a question phrased by somebody else.",
        "",
        "| kind | questions | routed by the gate | routed by relevance alone |",
        "|---|---|---|---|",
    ]
    for kind in ("paraphrase", "two_documents", "missing_fact", "shared_words", "unrelated"):
        lines.append("| {0} | {1} | {2} | {3} |".format(
            kind, *_routed(external, lambda i, k=kind: i["kind"] == k)))
    lines.append("| all | {0} | {1} | {2} |".format(*_routed(external, lambda i: True)))

    lines += [
        "",
        "Every external decision:",
        "",
        "| question | kind | answer in | gate | relevance alone | relevance | evidence | support |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for item, gate, base in external:
        lines.append("| {0} | {1} | {2} | {3} | {4} | {5:.3f} | {6:.3f} | {7} |".format(
            item["query"], item["kind"], item["answer_in"], gate.zone.value,
            base.zone.value, gate.relevance, gate.evidence,
            gate.support_doc_id or "none"))

    lines += [
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
    bundle = run_all()
    floors = bundle["floors"]
    decisions = bundle["labelled"]
    baseline_decisions = bundle["labelled_baseline"]
    external = bundle["external"]
    own = full_digest(bundle)

    if "--digest-only" in argv:
        # No subprocess from here: this is the mode the cross seed check calls.
        print(own)
        return 0

    # Cheap in process check first. On its own it cannot catch an ordering bug, which is
    # why the cross seed check follows, but it does catch accidental state in the gate.
    repeated = {full_digest(run_all()) for _ in range(3)}
    seeds, seed_results, agree = _cross_seed_digests(own)

    (HERE / "results.md").write_text(
        _markdown(decisions, baseline_decisions, external, floors, seeds, agree,
                  len(bundle["corpus"]), own),
        encoding="utf-8")

    held = _subset(decisions, HELD_OUT)
    calib = _subset(decisions, CALIBRATION)
    held_total, held_leaked = _without_answer(held)
    all_total, all_leaked = _without_answer(decisions)
    rows_lab = [(i, g, b) for (i, g), (_, b) in zip(decisions, baseline_decisions)]

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
    print("CALIBRATION ({0} questions, the floors came from these)".format(len(calib)))
    for name, total, correct in _zone_accuracy(calib):
        print("  {0:<12} {1:>3} questions  {2:>3} correct  {3}".format(
            name, total, correct, _share(correct, total)))
    print()
    print("SECOND SIGNAL (gate, then the same relevance floor with evidence floor 0.0)")
    for label, pick in (
        ("labelled, no answer", lambda i: not i["answerable_in_corpus"]),
        ("labelled, answerable", lambda i: i["answerable_in_corpus"]),
    ):
        n, g, b = _routed(rows_lab, pick)
        print("  {0:<22} {1:>3} questions  gate {2:>3}  relevance alone {3:>3}".format(
            label, n, g, b))
    print()
    print("EXTERNAL ({0} questions, no part in the floors or the exit status)".format(
        len(external)))
    for kind in ("paraphrase", "two_documents", "missing_fact", "shared_words", "unrelated"):
        n, g, b = _routed(external, lambda i, k=kind: i["kind"] == k)
        print("  {0:<15} {1:>3} questions  gate {2:>3}  relevance alone {3:>3}".format(
            kind, n, g, b))
    n, g, b = _routed(external, lambda i: True)
    print("  {0:<15} {1:>3} questions  gate {2:>3}  relevance alone {3:>3}".format(
        "all", n, g, b))
    for item, gate, _ in external:
        if gate.may_call_generator and item["answer_in"] == "none":
            print("  routed with no answer in the corpus: {0}".format(item["query"]))
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

    # Zone accuracy is a measurement and is reported as it comes, and so is everything the
    # external set says. These three are guarantees, and a run that breaks one has failed.
    failed = []
    if all_leaked:
        failed.append("{0} labelled questions with no answer reached a generator: {1}".format(
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
