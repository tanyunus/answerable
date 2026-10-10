# answerable

A retrieval abstention gate: given the retrieval results for a query, it decides whether an
acceptable answer exists at all, before any generator is called.

## The problem

A retriever answers every query with its best matches, so a query the corpus cannot support
still arrives at the generator with context attached, and that context reads as plausible.
Asking the generator to abstain does not fix this, because abstention requires noticing what
is absent, and a model conditioned on the retrieved text has no signal for the documents it
was not given or for the attribute the one it was given happens to omit. The decision has to
be made from the retrieval results, before the generator is reachable.

## The decision

Two signals are computed from the retrieval results, and each has a floor: the value it has
to reach for the query to stay in play. A signal under its floor sends the query out of the
answerable zone.

`relevance` is the score of the best retrieved document. It answers one question: is anything
in the corpus about this query at all.

`evidence` is the largest share of the query's content terms that any single retrieved
document covers. It answers a different question: does one document address enough of what
was asked.

Neither signal is a property of one result, and the two need not come from the same document.
Relevance is the top score and evidence is a maximum over the whole retrieved list, so the
document that ranks first and the document that covers the most terms are often different
ones. In the fixtures, "what is the odour of taskelite" ranks the taskelite record first at
0.293 and takes its evidence from the thornodite record, which is the one that carries the
word odour. `Decision.support_doc_id` names the document the evidence came from and says
nothing about which document ranked first.

The two signals disagree in a specific and common case, which is the reason for having both.
The examples here come from the fixtures in `eval/`, a synthetic corpus of invented mineral
records written for this repository. Take the question "what is the hardness of thornodite".
The thornodite record ranks first for it, because the name is rare and matches exactly. Its
score is 0.203, which is not a high score: on the current fixtures the questions that land in
the answerable zone score between 0.302 and 0.582. It is simply the best of a weak field, and
ranking first is all the relevance signal reports. That record gives a habit, a formation
setting and an odour, and no hardness, so evidence is 0.50. The subject is present and the
asked-about fact is not. A single score cannot separate that from an answerable question, and
a generator handed the record will supply a hardness from nowhere.

Evidence is measured per document, not over the union of the retrieved set. A query whose
terms are covered by two documents, each covering half, is the shape of a confident wrong
answer: the generator stitches the halves together and the result is grounded in neither.
Taking the maximum over single documents refuses that case instead of rewarding it.

| zone | condition | what it may do |
|---|---|---|
| answerable | relevance and evidence both at or above their floors | the retrieved documents may be passed to a generator |
| ambiguous | relevance at or above its floor, evidence below it | no generator call; the retrieved documents may be shown as they are, or the asker may be invited to narrow the question |
| empty | relevance below its floor | no generator call and no documents; the caller reports that nothing is available |

The ambiguous zone is the on-topic but unsupported case: the corpus has material about the
subject, and no single document backs the question that was asked about it.

`Decision.may_call_generator` is the only place that answers whether a generator may run.
Callers branch on it and not on the zone, so that adding a fourth zone later cannot
silently open the generator to it.

The split between empty and ambiguous is about how strong the best match is, and not about
whether an answer exists. Empty means nothing retrieved scored high enough to be worth
showing. Sharing a term with the corpus is not enough to escape it: the six fixture questions
at 0.104 each share one, and they stay in the empty zone. Ambiguous means something did score
high enough to show and no single document covered the question. "Is quelbrite toxic" has no
answer in the fixture corpus, and quelbrite is in it, so the query lands in ambiguous and its
documents may be shown. Both zones refuse the generator, which is the property being enforced.

The library ships no threshold values. A floor is a property of a corpus and a retriever, not
of the gate, so the caller supplies both. The values used below live in `eval/run.py`.

## Tightening each floor

Raising the relevance floor moves queries out of answerable and ambiguous and into empty.
Fewer queries reach a generator on a thin match, and more queries the corpus could have
answered are refused without their documents being shown at all. The cost falls on recall and
it falls silently: a query in the empty zone produces no output to inspect, so the queries
lost this way never appear in a review of bad answers.

Raising the evidence floor moves queries out of answerable and into ambiguous. The generator
is called on fewer partially supported questions, which is the failure the gate exists to
prevent, and the price is paid in clarification round trips on questions that one document did
cover, using wording the term match missed. This floor trades answer rate against grounding,
and it has no effect on what the empty zone catches.

## Results

Fixtures: 21 documents and 50 labelled questions, 24 of them calibration and 26 held out,
retrieval depth 5. Both floors are read off the calibration half alone: relevance 0.153,
evidence 0.900. The held-out half took no part in choosing them. A floor read off a set of
questions will separate that set, so accuracy on it measures almost nothing, which is the
reason for the split. Regenerated by `make eval` into `eval/results.md`, which lists every
individual decision.

Held out:

| zone | labelled questions | classified correctly | accuracy |
|---|---|---|---|
| answerable | 9 | 8 | 88.9% |
| ambiguous | 8 | 8 | 100% |
| empty | 9 | 9 | 100% |
| all | 26 | 25 | 96.2% |

The one miss is "what colour and lustre does pellomite have", labelled answerable and
decided ambiguous. Its document gives the lustre and calls the specimen straw yellow, so a
reader can answer the whole question from it, but the document never uses the word colour.
Evidence counts term presence, so coverage came to 0.667 and the question was held back.
That is a false refusal and it is counted as one.

Zone accuracy measures the three-way classification. The property the gate exists to enforce
is narrower: nothing the corpus cannot answer may reach a generator.

| check | result |
|---|---|
| held-out questions with no answer in the corpus | 17 |
| of those, routed to a generator | 0 |
| across both halves, questions with no answer | 33 |
| of those, routed to a generator | 0 |
| decisions identical across hash seeds 0, 1, 2 | yes |
| decision digest | `fe31badcb355fc9a37facab27194b1b04b9dcc9e422e65b5efdfb32d25a9ae4f` |

Calibration accuracy is 24 of 24. Those are the questions the floors were read off, so that
number is internal consistency and nothing more. It is reported because a large gap between
it and the held-out table is the signature of an overfitted floor.

Set iteration order can reach a decision: the gate intersects term sets, and code that
iterated one of those sets and kept the first match it found would pick a different document
on a different run, because the order a Python set yields its members depends on the
interpreter's hash seed. The determinism check runs the whole evaluation again in separate
processes under different values of `PYTHONHASHSEED` and compares digests. Repeating the run inside one process would
not establish anything: the hash seed is fixed for the lifetime of a process, so a result
that depends on set iteration order is perfectly stable until the next start.

### What the second signal buys

A one signal baseline beside the gate: the same relevance floor, with the evidence floor at
0.0. Coverage never falls below zero, so under that baseline every query clearing the
relevance floor is answerable. It is the gate with its second signal removed.

| set | questions | routed by the gate | routed by relevance alone |
|---|---|---|---|
| labelled, no answer in the corpus | 33 | 0 | 17 |
| labelled, answerable | 17 | 16 | 17 |
| external, no answer in the corpus | 16 | 1 | 13 |
| external, answerable from one document | 10 | 0 | 10 |
| external, answerable from two documents | 4 | 0 | 4 |

On the labelled set the second signal is what stops all 17 unanswerable questions that score
above the relevance floor, at a cost of one answerable question out of 17. On the external set
it cuts the unanswerable questions reaching a generator from 13 to 1, and it also refuses all
14 that the corpus does answer.

### The external question set

Thirty questions written from the corpus alone by a model that never saw the floors, the gate
or `queries.json`. It answers a question the labelled set cannot: every labelled question was
written by the same hand as the corpus and the floors, so none of them says what happens to a
question somebody else phrased. The set takes no part in deriving a floor and no part in the
exit status.

| kind | questions | routed by the gate | routed by relevance alone |
|---|---|---|---|
| paraphrase | 10 | 0 | 10 |
| two_documents | 4 | 0 | 4 |
| missing_fact | 8 | 1 | 8 |
| shared_words | 4 | 0 | 4 |
| unrelated | 4 | 0 | 1 |
| all | 30 | 1 | 27 |

**The gate refused all ten paraphrased questions that a single document answers.** The reason
is the definition of evidence: coverage is exact term presence, and "how hard is velmarite"
does not contain the word hardness, so the velmarite record covers one content term out of
two and scores 0.500 against a floor of 0.900. The same applies to the other nine. Exact term
presence is too literal for questions phrased in ordinary words. A deployment in front of
real users needs coverage computed through stemming, a synonym list or an embedding
similarity, with the evidence floor re-derived for that measure. The labelled set never
showed this, because its questions and its corpus were written by the same hand and share
vocabulary.

One external question reached a generator with no answer in the corpus: "what temperature are
the sample trays kept at". The storage record says the trays are kept at a steady temperature
and gives no value, so both content terms are present and coverage is 1.000. This is the
term-presence failure described under scope limits, now with a number against it.

Relevance alone routed 27 of the 30, including 13 of the 16 that have no answer in the corpus.
The three it refused are unrelated questions sharing no term with any record. The fourth
unrelated question got through it, "good recipe for banana bread", because "good" appears in
the cleavage terminology record and nothing else in the question does.

### Floor margins

The nearest fixture value on each side of each floor, per half:

| signal | floor | calibration below | calibration at or above | held-out below | held-out at or above |
|---|---|---|---|---|---|
| relevance | 0.153 | 0.104 | 0.203 | 0.104 | 0.190 |
| evidence | 0.900 | 0.800 | 1.000 | 0.750 | 1.000 |

Each floor sits inside a gap on both halves. The relevance floor of 0.153 has 0.104 below it
on both halves and 0.203 or 0.190 above it, so a floor of 0.10 would admit the six questions
at 0.104. Each of those shares a single term with the long procedure document and asks for
something that document does not record, such as how often gloves are replaced. The evidence
floor of 0.900 has 0.800 below it in the calibration half and 0.750 in the held-out half, so a
floor of 0.75 would pass every one of them, and each asks for an attribute its best document
leaves out.

## Reproducing

```
make eval
```

Python 3.9 or newer, standard library only: no dependency install, no API key, no network, no
model download. The command rewrites `eval/results.md` and exits non-zero if anything
unanswerable reaches a generator or if two runs disagree. Zone accuracy is printed as it comes
and does not affect the exit status, so a held-out miss is reported and not suppressed. The
external set is a measurement and does not affect it either.
`make test` runs the 49 tests.

## Scope limits

- The floors come from the calibration half, so the held-out table is a generalisation
  measurement and the calibration table is not. Neither is evidence that 0.153 and 0.900
  transfer to another corpus or another retriever. Re-derive both on your own data.
- Evidence is term presence, not semantic support. This is the gate's largest weakness and
  the external set measures it: ten paraphrased questions that a single document answers were
  all refused, because the words the question uses are not the words the document uses. The
  counted held-out miss is the same failure. The other side is a false pass, and the labelled set carries no example of it, so
  here are two probes from this corpus that are not in it. "Who stored the samples" has both
  of its content terms in one document and reaches the answerable zone, although the corpus
  never records who did the storing: "who" is a function word and is dropped before coverage
  is computed, which removes the part of the question carrying the demand. "What is the
  hardness of the scratch scale" reaches it from a document about a specimen that happens to
  contain all three terms.
- The retriever in `src/answerable/retrieve.py` exists so the evaluation runs offline. Scores
  from any other retriever are on a different scale, so the relevance floor has to be
  re-derived. Evidence is a share of the query's terms and is scale free.
- Unigrams, one language, one corpus. No stemming, no synonyms, no multi-word terms, no
  spelling correction.
- The gate reads scores and term sets. It does not parse the query, rewrite it, choose a
  retriever or rank anything.
- Nothing here measures answer quality inside the answerable zone. That is a separate
  question and this repository does not address it.

## Licence

MIT. See `LICENSE`.
