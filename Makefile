# Standard library only, so there is no install target: there is nothing to install.
PYTHON ?= python3

.PHONY: eval test

# Rewrites eval/results.md. Exits non zero if anything unanswerable reaches a generator or
# if two runs disagree. A question in the wrong zone is reported and does not fail the run:
# the held-out half is there to be failed, and a runner that failed on a miss would put
# pressure on the next person to bury it.
eval:
	$(PYTHON) eval/run.py

test:
	$(PYTHON) -m unittest discover -s tests -v
