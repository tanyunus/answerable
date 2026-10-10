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
floors from calibration only: relevance 0.153, evidence 0.900

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

SECOND SIGNAL (gate, then the same relevance floor with evidence floor 0.0)
  labelled, no answer     33 questions  gate   0  relevance alone  17
  labelled, answerable    17 questions  gate  16  relevance alone  17

EXTERNAL (30 questions, no part in the floors or the exit status)
  paraphrase       10 questions  gate   0  relevance alone  10
  two_documents     4 questions  gate   0  relevance alone   4
  missing_fact      8 questions  gate   1  relevance alone   8
  shared_words      4 questions  gate   0  relevance alone   4
  unrelated         4 questions  gate   0  relevance alone   1
  all              30 questions  gate   1  relevance alone  27
  routed with no answer in the corpus: what temperature are the sample trays kept at

wrong zone [held_out] what colour and lustre does pellomite have: labelled answerable, decided ambiguous
digest fe31badcb355fc9a37facab27194b1b04b9dcc9e422e65b5efdfb32d25a9ae4f
repeated in process: identical
hash seeds 0, 1, 2: identical
written: eval/results.md
```

Exit status is 0 when no labelled question without an answer reached a generator and the
digest matched across hash seeds. Zone accuracy is reported as it comes and does not affect the
exit status: the held-out half is there to be failed, and a run that hid a miss by failing
would be worse than one that prints it. The external set does not affect it either. The run
above exits 0 and prints one external question that reached a generator with no answer in the
corpus. The digest is a `sha256` over every decision of the run, tagged by which pass made it,
so the labelled set, the external set and the one signal baseline are all inside it.

`eval/results.md` is committed and contains no timestamp, so running `make eval` on an
unchanged tree leaves `git diff` empty. A non empty diff means a decision changed.

`make test` runs 49 tests and takes under a second.

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
5. `eval/run.py`: all of the input and output. `derive_floors` reads the calibration half
   alone, `relevance_only` builds the one signal baseline, and `run_all` is the single bundle
   the runner, the fingerprint and the tests all read, so a number cannot drift between them.
6. `eval/external.json`: thirty questions written from the corpus alone by a model that never
   saw the floors, the gate or `queries.json`. Do not derive a floor from it and do not edit
   it to improve a number. `kind` says what each question tests and `answer_in` says whether
   the corpus answers it from one document, from two, or not at all.

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

The labelled set is split in two. Both floors, 0.153 for relevance and 0.900 for evidence, are
read off the 24 calibration questions and the 26 held-out questions take no part in choosing
them. `tests/test_evaluation_design.py` asserts that: relabelling a held-out question leaves
both floors unmoved, and relabelling a calibration question moves one, so the first assertion
cannot pass by accident.

Each floor is placed midway between the two groups it has to separate. For relevance those are
the calibration questions labelled empty, which top out at 0.104, and every other calibration
question, which starts at 0.203. For evidence they are the calibration questions labelled
ambiguous, which top out at 0.800, and those labelled answerable, which are all at 1.000. The
margins table in `eval/results.md` gives the nearest value on each side of each floor for both
halves, so a floor that separates the half it came from and not the other one is visible.

Every question labelled empty or ambiguous carries an `absent` field in
`eval/queries.json` naming what the corpus does not supply and what its best document records
instead, so a label can be checked against the corpus without rerunning anything.
`tests/test_evaluation_design.py` asserts the field is present on every such question and
absent on the answerable ones.

## Limits of the results

Held out accuracy is 25 of 26. The miss is "what colour and lustre does pellomite have": its
document gives the lustre and calls the specimen straw yellow without using the word colour,
so coverage came to 0.667 and the question was held back although a reader could answer it.

Calibration accuracy is 24 of 24, measured on the questions the floors were read off. It shows
internal consistency and no more.

Both floors are exercised by the fixtures. Sixteen questions fall under the relevance floor.
Ten of them score exactly 0.000, because no term of the question appears anywhere in the
corpus, and those ten would be refused by any floor above zero. The other six score 0.104, two
in the calibration half and four in the held-out half, and they are the ones that constrain the
value: a floor of 0.10 would admit them. On the evidence side the nearest questions below the
floor sit at 0.800 in the calibration half and 0.750 in the held-out half, so a floor of 0.75
would let all of them through. Neither value is free.

Evidence is term presence and not semantic support, and this is the gate's largest weakness.
The external set measures it: all ten paraphrased questions that a single document answers were
refused, because "how hard is velmarite" does not contain the word hardness, so coverage came
to 0.500 against a floor of 0.900. Any claim that this gate is ready to sit in front of
ordinary phrasing is contradicted by that row.

The false pass side of the same weakness shows up once in the external set: "what temperature
are the sample trays kept at" reaches a generator because the storage record contains both
content terms, and it records a steady temperature with no value. The README scope limits give
two further probes of this kind from the labelled corpus.

The one signal baseline is in the results to answer what the second signal buys. On the
labelled set it stops all 17 unanswerable questions that clear the relevance floor and costs
one answerable question out of 17. On the external set relevance alone routes 27 of 30,
including 13 of the 16 with no answer in the corpus, and the gate cuts that 13 to 1.
