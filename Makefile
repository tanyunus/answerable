# Standard library only, so there is no install target: there is nothing to install.
PYTHON ?= python3

.PHONY: eval test

# Rewrites eval/results.md. Exits non zero if a labelled question lands in the wrong zone,
# if anything unanswerable reaches a generator, or if two runs disagree.
eval:
	$(PYTHON) eval/run.py

test:
	$(PYTHON) -m unittest discover -s tests -v
