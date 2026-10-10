"""Tokenisation and content term extraction.

Deliberately plain: lower case, split on anything that is not a letter or a digit, drop a
fixed stop word list, drop single characters. No stemming, no synonyms, no multi-word
terms, no question classification. The gate does not import this module; a caller may
supply term sets from any tokeniser as long as documents and queries go through the same
one.

Content terms come back sorted and deduplicated. That is not cosmetic: a set would iterate
in an order that depends on the interpreter's hash seed, and anything derived from that
order would change between processes. Inside any one process it would look stable.
"""

from __future__ import annotations

import re

# Function words and question words only. Nothing here is specific to the fixture corpus:
# adding a domain word to this list would hide a real gap in the evidence signal, because a
# term that is never counted can never be found missing.
STOP_WORDS = frozenset({
    "a", "about", "all", "am", "an", "and", "any", "are", "as", "at", "be", "been",
    "being", "between", "both", "but", "by", "can", "could", "did", "do", "does", "each",
    "for", "from", "had", "has", "have", "he", "her", "him", "his", "how", "i", "if",
    "in", "into", "is", "it", "its", "me", "my", "no", "not", "of", "on", "or", "our",
    "over", "she", "should", "so", "some", "than", "that", "the", "their", "them", "then",
    "there", "these", "they", "this", "those", "to", "under", "us", "was", "we", "were",
    "what", "when", "where", "which", "who", "why", "will", "with", "would", "you",
    "your",
})

_SPLIT = re.compile(r"[^0-9a-z]+")


def tokenise(text: str) -> tuple:
    """Lower case tokens in the order they appear, duplicates kept.

    Separate from `content_terms` so that a caller can see what was thrown away.
    """
    if not text:
        return ()
    return tuple(t for t in _SPLIT.split(text.lower()) if t)


def content_terms(text: str) -> tuple:
    """The terms a question is actually about: sorted, deduplicated, stop words removed.

    A question made only of function words returns an empty tuple. That is a real case.
    The gate treats it as unanswerable and never divides by zero.
    """
    kept = {t for t in tokenise(text) if len(t) > 1 and t not in STOP_WORDS}
    return tuple(sorted(kept))
