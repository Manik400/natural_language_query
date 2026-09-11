"""
tokenizer.py
------------
Splits user text into clauses and then into prioritised token n-grams,
with a dedicated fast-path for IP address literals.

Clause splitting
----------------
Splits on comma "," OR the whole-word "and" (case-insensitive), so:
  "kusmunda, korba and bishrampur"
  → ["kusmunda", "korba", "bishrampur"]

N-gram extraction
-----------------
Produces (token, [word_positions]) pairs, longest n-gram first.
Compound raw words (with _ or -) are also emitted as high-priority
single tokens before being split, so "SECL_KSM_SARANGI" can match
as one unit against a camera name before its parts are considered.

IP extraction
-------------
IPv4 literals (full x.x.x.x or partial x.x.x subnet prefix) are
extracted before any tokenisation so they are never fragmented by
the n-gram pipeline. Each IP is returned for direct or prefix-based
index lookup:
  "192.168.1.5"  → exact camera match
  "192.168.1"    → all cameras whose IP starts with that prefix
"""

from __future__ import annotations

import re

# Matches IPv4 (x.x.x.x) or a 3-octet subnet prefix (x.x.x).
# Full 4-octet pattern is listed first so it takes priority when both could match.
_IP_RE = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3}|\d{1,3}(?:\.\d{1,3}){2})\b")


def extract_ips(text: str) -> list[str]:
    """
    Return every IPv4 literal or 3-octet prefix found in *text*,
    in order of appearance.

      "192.168.1.5"   → exact match against ip index
      "192.168.1"     → prefix match: all cameras in that subnet

    Duplicates are preserved so the caller can attribute each occurrence.
    """
    return _IP_RE.findall(text)


def strip_ips(text: str) -> str:
    """
    Remove all IPv4 literals and 3-octet prefixes from *text* so they
    are not re-tokenised as ordinary word n-grams by the token pipeline.
    """
    return _IP_RE.sub(" ", text).strip()


def split_clauses(user_text: str) -> list[str]:
    """
    Split user query into independent clauses on:
      - comma  ","
      - whole-word  "and"  (case-insensitive)

    Each clause is resolved independently and results are unioned.
    IPs inside clauses are left intact here; the resolver calls
    extract_ips() on each clause before token matching.
    """
    parts = re.split(r"\s*,\s*|\s+and\s+", user_text, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]


def _normalize(s: str) -> str:
    """Lowercase, replace _ and - with spaces, strip whitespace."""
    return s.lower().replace("_", " ").replace("-", " ").strip()


def _split_digit_suffix(s: str) -> str:
    """Insert a space between a letter and a following digit: cam01 → cam 01."""
    return re.sub(r"([a-zA-Z])(\d)", r"\1 \2", s)


def strip_stopwords(text: str, stopwords: set[str]) -> str:
    """
    Remove stopword words from text before n-gram building.
    Preserves original casing of non-stopword words.
    Only removes whole words that are stopwords after normalization.

      "from secl hq sec cam01" → "secl hq sec cam01"
      "show me korba and kusmunda" → "korba kusmunda"
    """
    words = text.split()
    return " ".join(w for w in words if _normalize(w) not in stopwords)


def extract_tokens_prioritized(
    text: str,
    stopwords: set[str] | None = None,
) -> list[tuple[str, list[int]]]:
    """
    Return (token, [word_positions]) pairs for a single clause,
    ordered longest n-gram first.

    Stopwords are stripped from the clause before n-gram building so
    noise words like "from", "show", "at" never anchor or fragment
    meaningful spans.

    IP literals are stripped before any word splitting so octets are
    never emitted as tokens.

    Two passes:
      1. Raw compound words (contain _ or -) → emitted with position [-1]
         (synthetic, never consumes real word positions).
      2. Word n-grams over ALL lengths (no cap), longest first, built over
         digit-split, stopword-free words.
    """
    clean_text = strip_ips(text)

    # Strip stopwords before n-gram building
    if stopwords:
        clean_text = strip_stopwords(clean_text, stopwords)

    result: list[tuple[str, list[int]]] = []

    # Pass 1: raw compound tokens — synthetic position [-1]
    for raw_word in clean_text.split():
        if "_" in raw_word or "-" in raw_word:
            result.append((raw_word, [-1]))

    # Normalise: compound delimiters → spaces + digit-split
    normalised = clean_text.replace("_", " ").replace("-", " ")
    normalised = _split_digit_suffix(normalised)
    words = normalised.split()

    # Pass 2: all n-gram lengths, longest first — no artificial cap
    for n in range(len(words), 0, -1):
        for i in range(len(words) - n + 1):
            result.append((" ".join(words[i : i + n]), list(range(i, i + n))))

    return result
