from __future__ import annotations

import re
from typing import Optional

from rapidfuzz import fuzz

from .constants import FUZZY_THRESHOLD, STOPWORDS
from .models import FlatCamera

# ── Normalisation ─────────────────────────────────────────────────────────────


def normalize(s: str) -> str:
    return s.lower().replace("_", " ").replace("-", " ").strip()


def _split_digit_suffix(s: str) -> str:
    return re.sub(r"([a-zA-Z])(\d)", r"\1 \2", s)


def normalize_full(s: str) -> str:
    s = s.lower().replace("_", " ").replace("-", " ").replace("/", " ").strip()
    s = _split_digit_suffix(s)
    return re.sub(r"\s+", " ", s).strip()


# ── Core helpers ──────────────────────────────────────────────────────────────


def is_meaningful(token: str) -> bool:
    return normalize(token) not in STOPWORDS and len(normalize(token)) >= 3


def exact_match(token: str, candidate: str) -> bool:
    return normalize(token) == normalize(candidate)


def partial_match(token: str, candidate: str) -> bool:
    t, c = normalize(token), normalize(candidate)

    shorter, longer = (t, c) if len(t) <= len(c) else (c, t)

    if len(shorter) < max(3, len(longer) * 0.5):
        return False

    return shorter in longer


def fuzzy_score(token: str, candidate: str) -> float:
    nt = normalize_full(token)
    nc = normalize_full(candidate)

    base = fuzz.token_set_ratio(nt, nc)

    if base == 0:
        return 0.0

    token_words = set(nt.split())
    cand_words = set(nc.split())

    digit_tokens = {w for w in token_words if w.isdigit()}

    if digit_tokens and not digit_tokens.issubset(cand_words):
        return 0.0

    if token_words == cand_words:
        return float(base)

    smaller = token_words if len(token_words) < len(cand_words) else cand_words
    larger = token_words if len(token_words) > len(cand_words) else cand_words

    if smaller < larger:
        coverage = len(smaller) / len(larger)
        return base * (coverage**0.4)

    return float(base)


def score_match(token: str, candidate: str) -> tuple[Optional[str], float]:

    if not is_meaningful(token):
        return None, 0.0

    if exact_match(token, candidate):
        return "exact", 100.0

    if partial_match(token, candidate):
        return "partial", max(fuzzy_score(token, candidate), 80.0)

    score = fuzzy_score(token, candidate)

    if score >= FUZZY_THRESHOLD:
        return "fuzzy", float(score)

    return None, 0.0


# ── IP matching ───────────────────────────────────────────────────────────────


def match_ip_exact(
    query_ip: str,
    ip_index: dict[str, FlatCamera],
    raw_slice: str = "",
) -> list[FlatCamera]:
    """
    Exact IPv4 match.
    matched_token = IP (because query matched directly on IP)
    """

    cam = ip_index.get(query_ip)

    if cam is None:
        return []

    matched = FlatCamera(
        path=cam.path,
        camera_name=cam.camera_name,
        ip=cam.ip,
        match_type="ip",
        # For IP matches token should remain IP
        matched_token=query_ip,
        matched_raw_slice=raw_slice,
        confidence=100.0,
    )

    return [matched]


def match_ip_prefix(
    prefix: str,
    ip_index: dict[str, FlatCamera],
    raw_slice: str = "",
) -> list[FlatCamera]:
    """
    Subnet prefix match (x.x.x)
    matched_token = IP prefix from query
    """

    needle = prefix if prefix.endswith(".") else prefix + "."

    results: list[FlatCamera] = []

    for ip, cam in ip_index.items():

        if ip.startswith(needle):

            results.append(
                FlatCamera(
                    path=cam.path,
                    camera_name=cam.camera_name,
                    ip=cam.ip,
                    match_type="ip",
                    # token remains query IP prefix
                    matched_token=prefix,
                    matched_raw_slice=raw_slice,
                    confidence=75.0,
                )
            )

    return results
