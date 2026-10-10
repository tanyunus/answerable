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
floors from calibration only: relevance 0.146, evidence 0.900

HELD OUT (26 questions)
  answerable     9 questions    8 correct  88.9%
  ambiguous      8 questions    8 correct  100%
  empty          9 questions    9 correct  100%
  all           26 questions   25 correct  96.2%
  no answer in the corpus: 17, routed to a generator: 0

CALIBRATION (24 questions, the floors came from these)
  answerable     8 questions    8 correct  100%
  ambiguous      9 questions    9 correct  100%
  empty          7 questions    7 correct  100%
  all           24 questions   24 correct  100%

wrong zone [held_out] what colour and lustre does pellomite have: labelled answerable, decided ambiguous
digest 4c7cbeedbadfb0e134176c9c69ce688c5e162a9ecbbddd057f3c5fa2eef774c8
repeated in process: identical
hash seeds 0, 1, 2: identical
written: eval/results.md
```

Exit status is 0 when nothing unanswerable reached a generator and the digest matched across
hash seeds. Zone accuracy is reported as it comes and does not affect the exit status: the
held out half is there to be failed, and a run that hid a miss by failing would be worse than
one that prints it. The digest is a `sha256` over `(question, half, zone, relevance, evidence,
support document)` for all 50 questions in fixture order.

`eval/results.md` is committed and contains no timestamp, so running `make eval` on an
unchanged tree leaves `git diff` empty. A non empty diff means a decision changed.

`make test` runs 27 tests and takes under a second.

## Files that carry the decision, in reading order

1. `src/answerable/types.py`: the five values. `Zone` is not a severity scale.
   `Decision.may_call_generator` is the only thing that grants a generator call.
2. `src/answerable/terms.py`: tokenisation, the stop word list, and content term extraction.
   Content terms come back sorted and deduplicated, and not as a set. Set iteration
   order depends on the interpreter's hash seed.
3. `src/answerable/gate.py`: the decision. Pure functions, no file access, no clock, no
   randomness, no global state. `relevance_of`, `evidence_of`, then `decide`. Read the module
   docstring first: it states why two signals are needed and why evidence is measured per
   document and not across the retrieved set.
4. `src/answerable/retrieve.py`: a lexical retriever included so the evaluation runs offline.
   It is not the subject of the repository. The one part worth reading is why query terms the
   corpus has never seen are dropped from the score but kept in the term set the gate sees.
   That asymmetry is what lets the two signals disagree. The score comes from the part of
   the question the corpus can speak to. The coverage comes from the whole question.
5. `eval/run.py`: all of the input and output, plus the threshold values.

## Deliberately out of scope

- Threshold values in the library. `src` ships none; a floor belongs to a corpus and a
  retriever, so the caller supplies both.
- Any judgement about an answer once a query is in the answerable zone. The gate decides
  whether to call a generator, not whether the generator was right.
- Query understanding. No intent classification, no query rewriting, no stemming, no
  synonyms, no multi-word terms, no more than one language.
- Retrieval quality. The bundled retriever is a stand in; swapping it is expected.
- Any input or output in the decision path. `gate.py` reads nothing and writes nothing, which
  is why a zone boundary can be tested in three lines without a corpus.

## Where the README numbers come from

Every number in `README.md` is produced by `make eval` and also written to `eval/results.md`.
The two must agree; `tests/test_determinism.py` asserts that the committed digest in
`eval/results.md` matches a fresh run.

The labelled set is split in two. Both floors, 0.146 for relevance and 0.900 for evidence, are
read off the 24 calibration questions and the 26 held out questions take no part in choosing
them. `tests/test_evaluation_design.py` asserts that: relabelling a held out question leaves
both floors unmoved, and relabelling a calibration question moves one, so the first assertion
cannot pass by accident.

Each floor is placed midway between the two groups it has to separate. For relevance those are
the calibration questions labelled empty, which top out at 0.104, and every other calibration
question, which starts at 0.189. For evidence they are the calibration questions labelled
ambiguous, which top out at 0.800, and those labelled answerable, which are all at 1.000. The
margins table in `eval/results.md` gives the nearest value on each side of each floor for both
halves, so a floor that separates the half it came from and not the other one is visible.

## Limits of the results

Held out accuracy is 25 of 26. The miss is "what colour and lustre does pellomite have": its
document gives the lustre and calls the specimen straw yellow without using the word colour,
so coverage came to 0.667 and the question was held back although a reader could answer it.

Calibration accuracy is 24 of 24, measured on the questions the floors were read off. It shows
internal consistency and no more.

Both floors are exercised by the fixtures. Six questions score between 0.000 and the relevance
floor, two in the calibration half and four in the held out half, so a lower floor would admit
them. On the evidence side the nearest questions below the floor sit at 0.800 in the calibration
half and 0.750 in the held out half, so a floor of 0.75 would let all of them through. Neither
value is free.

Evidence is term presence and not semantic support. The held out miss is the false refusal side
of that. The false pass side carries no label in the fixtures, and the README scope limits give
two probes from this corpus that show it: both reach the answerable zone and neither has an
answer in the corpus.
