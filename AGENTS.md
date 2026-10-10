# Notes for a model reading this repository

## What this is

A retrieval abstention gate: two floors over two signals computed from retrieval results,
sorting every query into `answerable`, `ambiguous` or `empty`, where only `answerable` may
reach a generator. The repository also carries the evaluation that produces the numbers in
`README.md`, over a synthetic corpus of invented mineral records.

## Running the evaluation

```
make eval
```

Python 3.9 or newer, standard library only. Nothing to install, no network access, no model.
Expect this on stdout:

```
answerable    10 questions   10 correct  100%
ambiguous     10 questions   10 correct  100%
empty         10 questions   10 correct  100%
all           30 questions   30 correct  100%

no answer in the corpus: 20, routed to a generator: 0
digest 41605d45ece914ac54f8011482a1985d9eb0422088039c3e1b7c919b5de6be33
repeated in process: identical
hash seeds 0, 1, 2: identical
written: eval/results.md
```

Exit status is 0 only if every labelled question landed in its expected zone, nothing
unanswerable reached a generator, and the digest matched across hash seeds. The digest is a
`sha256` over `(question, zone, relevance, evidence, support document)` for all 30 questions
in fixture order.

`eval/results.md` is committed and contains no timestamp, so running `make eval` on an
unchanged tree leaves `git diff` empty. A non empty diff means a decision changed.

`make test` runs 27 tests and takes under a second.

## Files that carry the decision, in reading order

1. `src/answerable/types.py`: the five values. `Zone` is not a severity scale.
   `Decision.may_call_generator` is the only thing that grants a generator call.
2. `src/answerable/terms.py`: tokenisation, the stop word list, and content term extraction.
   Content terms come back sorted and deduplicated rather than as a set, because set
   iteration order depends on the interpreter's hash seed.
3. `src/answerable/gate.py`: the decision. Pure functions, no file access, no clock, no
   randomness, no global state. `relevance_of`, `evidence_of`, then `decide`. Read the module
   docstring first: it states why two signals are needed and why evidence is measured per
   document rather than across the retrieved set.
4. `src/answerable/retrieve.py`: a lexical retriever included so the evaluation runs offline.
   It is not the subject of the repository. The one part worth reading is why query terms the
   corpus has never seen are dropped from the score but kept in the term set the gate sees:
   that asymmetry is what lets relevance stay high while evidence falls.
5. `eval/run.py`: all of the input and output, plus the threshold values.

## Deliberately out of scope

- Threshold values in the library. `src` ships none; a floor belongs to a corpus and a
  retriever, so the caller supplies both.
- Any judgement about an answer once a query is in the answerable zone. The gate decides
  whether to call a generator, not whether the generator was right.
- Query understanding. No intent classification, no query rewriting, no stemming, no
  synonyms, no multi word terms, no more than one language.
- Retrieval quality. The bundled retriever is a stand in; swapping it is expected.
- Any input or output in the decision path. `gate.py` reads nothing and writes nothing, which
  is why a zone boundary can be tested in three lines without a corpus.

## Where the README numbers come from

Every number in `README.md` is produced by `make eval` and also written to `eval/results.md`.
The two must agree; `tests/test_determinism.py` asserts that the committed digest in
`eval/results.md` matches a fresh run.

The floors, 0.10 for relevance and 0.75 for evidence, were read off the fixture distribution
rather than brought in from elsewhere. On the 30 labelled questions, relevance is 0.000 for
every `empty` question and at least 0.184 for every other one, and evidence is at most 0.500
for every `ambiguous` question and exactly 1.000 for every `answerable` one. Each floor sits
in the gap between those groups, and `eval/results.md` reports the nearest value on each side
so that a later change to the fixtures narrowing a gap is visible in the diff.

Two cautions if you are about to describe the results:

- 100% zone accuracy is measured on the set the floors were derived from. It shows the gate
  implements the stated decision, not that the floors generalise.
- The relevance floor's exact value is not exercised by the fixtures, because the empty
  questions all score exactly 0.000. `tests/test_zone_boundaries.py` tests that boundary with
  constructed inputs instead, including the value exactly on the floor.

The failure mode the gate does not catch is in the README scope limits, with two worked
examples from this corpus. Both reach the answerable zone and neither has an answer in the
corpus.
