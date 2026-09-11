"""
resolver.py
-----------
Core resolution engine: maps a user clause to a set of matching FlatCameras.

Two-stage process per clause
-----------------------------
1. _lookup_token
     For each meaningful token find the best-matching node (folder) or camera
     group. Returns a set of camera keys and match metadata.

2. _resolve_clause
     AND-intersect the per-token camera sets so multi-word queries narrow
     results. If an intersection would empty the set, that constraint is
     skipped (cross-hierarchy fall-through).

IP fast-path
------------
Before token matching, each clause is scanned for IPv4 literals (x.x.x.x)
and 3-octet prefixes (x.x.x). Matches are resolved directly via the ip_index
and bypass the token pipeline entirely:
  "192.168.1.5"  → exact match, confidence 100.0
  "192.168.1"    → prefix match, confidence 75.0

Tie-breaking
------------
When multiple nodes match a token with equal match-type and confidence:
  1. match type    exact > partial > fuzzy   (lower MATCH_ORDER value wins)
  2. confidence    higher is better
  3. category      folder/node match > direct camera-name match
                   (folder match is always more intentional than a camera
                    substring match at equal confidence)
  4. depth         shallower folder wins     (broader coverage)
  5. size          smaller subtree wins      (more specific when depth ties)

matched_token vs matched_name
------------------------------
  matched_token    — the verbatim query token that caused the match
                     (what the user typed; always a clean string)
  matched_raw_slice — the verbatim substring of the original user query
  matched_name      — internal: the node name (folder) or "[N camera(s)]"
                     that was matched; used for diagnostics, NOT surfaced
                     in FlatCamera output
"""

from __future__ import annotations

from typing import Optional

from .constants import FUZZY_THRESHOLD, MATCH_ORDER, STOPWORDS
from .matching import (
    is_meaningful,
    match_ip_exact,
    match_ip_prefix,
    normalize,
    score_match,
)
from .models import FlatCamera
from .tokenizer import extract_ips, extract_tokens_prioritized, split_clauses, strip_ips

# ── Depth inference ───────────────────────────────────────────────────────────


def _node_depth(node_name: str, node_index: dict[str, list[FlatCamera]]) -> int:
    """
    Infer the shallowest depth (minimum path segments) of a node.
    Lower depth → higher ancestor → broader coverage.
    """
    cams = node_index.get(node_name, [])
    if not cams:
        return 0
    return min(len(cam.path) for cam in cams)


# ── Tie-breaking helper ───────────────────────────────────────────────────────

# Category constants: lower = higher priority
_CAT_NODE = 0  # folder/node subtree match
_CAT_CAMERA = 1  # direct camera-name match


def _is_better(
    best_keys: Optional[set],
    best_mtype: str,
    best_conf: float,
    best_depth: int,
    best_cat: int,
    mtype: str,
    conf: float,
    depth: int,
    cat: int,
    size: int,
) -> bool:
    """
    Return True if the new candidate beats the current best.

    Priority:
      1. match type   exact > partial > fuzzy
      2. confidence   higher is better
      3. category     node/folder match > direct camera match
      4. depth        shallower node is better (broader coverage)
      5. size         smaller subtree when depth ties (more specific)
    """
    if best_keys is None:
        return True
    cur = (MATCH_ORDER[best_mtype], -best_conf, best_cat, best_depth, len(best_keys))
    new = (MATCH_ORDER[mtype], -conf, cat, depth, size)
    return new < cur


# ── Token → camera-key set ───────────────────────────────────────────────────


def _lookup_token(
    token: str,
    flat: list[FlatCamera],
    node_index: dict[str, list[FlatCamera]],
) -> Optional[tuple[set[tuple], str, float, str]]:
    """
    Find the best camera set for a single token.

    Checks folder names first (subtree expansion), then individual camera
    names. Folder/node matches beat direct camera-name matches at equal
    mtype and confidence (category tie-break).

    Returns (camera_keys, match_type, confidence, matched_node_name)
    or None if nothing scores above threshold.
    """
    best_keys: Optional[set[tuple]] = None
    best_mtype: str = "fuzzy"
    best_conf: float = 0.0
    best_depth: int = 0
    best_cat: int = _CAT_NODE
    best_name: str = ""

    # ── 1. Folder names → subtree expansion ──────────────────────────────────
    for node_name, subtree_cams in node_index.items():
        mtype, conf = score_match(token, node_name)
        if not mtype:
            continue
        keys = {c.key for c in subtree_cams}
        depth = _node_depth(node_name, node_index)
        if _is_better(
            best_keys,
            best_mtype,
            best_conf,
            best_depth,
            best_cat,
            mtype,
            conf,
            depth,
            _CAT_NODE,
            len(keys),
        ):
            best_keys, best_mtype, best_conf, best_depth, best_cat, best_name = (
                keys,
                mtype,
                conf,
                depth,
                _CAT_NODE,
                node_name,
            )

    # ── 2. Camera names → collect ALL at equal best confidence ───────────────
    best_cam_mtype: Optional[str] = None
    best_cam_conf: float = 0.0
    cam_keys: set[tuple] = set()

    for cam in flat:
        mtype, conf = score_match(token, cam.camera_name)
        if not mtype:
            continue
        if conf > best_cam_conf:
            best_cam_mtype = mtype
            best_cam_conf = conf
            cam_keys = {cam.key}
        elif conf == best_cam_conf:
            if MATCH_ORDER.get(mtype, 2) < MATCH_ORDER.get(
                best_cam_mtype or "fuzzy", 2
            ):
                best_cam_mtype = mtype
            cam_keys.add(cam.key)

    if best_cam_mtype and cam_keys:
        # Camera matches: depth=999 (leaf level), category=_CAT_CAMERA
        cam_label = f"[{len(cam_keys)} camera(s)]"
        if _is_better(
            best_keys,
            best_mtype,
            best_conf,
            best_depth,
            best_cat,
            best_cam_mtype,
            best_cam_conf,
            999,
            _CAT_CAMERA,
            len(cam_keys),
        ):
            best_keys, best_mtype, best_conf, best_depth, best_cat, best_name = (
                cam_keys,
                best_cam_mtype,
                best_cam_conf,
                999,
                _CAT_CAMERA,
                cam_label,
            )

    return (best_keys, best_mtype, best_conf, best_name) if best_keys else None


# ── Raw-slice extraction ──────────────────────────────────────────────────────


def _trim_stopword_words(s: str) -> str:
    """
    Strip leading and trailing words that are pure stopwords from a
    space-separated string.  Preserves the original casing of inner words.
    Falls back to the original string if stripping would leave it empty.

    Example: "from secl hq floor2" → "secl hq floor2"
             "show me korba"       → "korba"
    """
    words = s.split()
    while words and normalize(words[0]) in STOPWORDS:
        words = words[1:]
    while words and normalize(words[-1]) in STOPWORDS:
        words = words[:-1]
    return " ".join(words) if words else s


def _raw_slice(clause: str, token: str) -> str:
    """
    Return the verbatim substring of *clause* that corresponds to *token*,
    with leading/trailing stopword words trimmed.

    Finds the first span in clause whose normalised form equals the
    normalised token, returns the original characters at that span
    (preserving casing and delimiters), then strips pure-stopword words
    from both ends so attribution is clean for the caller.

    Falls back to the token itself if no span can be located.
    """
    norm_clause = normalize(clause)
    norm_token = normalize(token)
    idx = norm_clause.find(norm_token)
    if idx == -1:
        return _trim_stopword_words(token)
    raw = clause[idx : idx + len(norm_token)]
    return _trim_stopword_words(raw)


# ── IP resolution ─────────────────────────────────────────────────────────────


def _resolve_ips(
    clause: str,
    ip_index: dict[str, FlatCamera],
) -> dict[tuple, tuple[str, float, str, str]]:
    """
    Extract all IP literals from *clause* and resolve them via ip_index.

    Full IPv4 (x.x.x.x) → exact match, confidence 100.0
    3-octet prefix (x.x.x) → prefix match, confidence 75.0

    Returns {camera_key: (match_type, confidence, matched_token, raw_slice)}.
    """
    hits: dict[tuple, tuple[str, float, str, str]] = {}
    for ip in extract_ips(clause):
        if ip.count(".") == 3:
            matched_cams = match_ip_exact(ip, ip_index, raw_slice=ip)
        else:
            matched_cams = match_ip_prefix(ip, ip_index, raw_slice=ip)
        for cam in matched_cams:
            key = cam.key
            prev = hits.get(key)
            if prev is None or cam.confidence > prev[1]:
                hits[key] = (
                    cam.match_type,
                    cam.confidence,
                    cam.matched_token,
                    cam.matched_raw_slice,
                )
    return hits


# ── Single-clause resolution ──────────────────────────────────────────────────


def _resolve_clause(
    clause: str,
    flat: list[FlatCamera],
    node_index: dict[str, list[FlatCamera]],
    ip_index: dict[str, FlatCamera],
) -> dict[tuple, tuple[str, float, str, str]]:

    ip_hits = _resolve_ips(clause, ip_index)

    token_clause = strip_ips(clause)

    all_matches: list[tuple[set[tuple], str, float, str, str, list[int]]] = []
    # (camera_keys, match_type, confidence, matched_token, raw_slice, positions)

    for token, positions in extract_tokens_prioritized(
        token_clause, stopwords=STOPWORDS
    ):

        if not is_meaningful(token):
            continue

        result = _lookup_token(token, flat, node_index)

        if result:

            keys, mtype, conf, node_name = result

            raw = _raw_slice(token_clause, token)

            # ── Determine correct matched_token ──
            if node_name.startswith("["):
                # camera-name match
                matched_token = token
            else:
                # folder/node match → canonical JSON value
                matched_token = node_name

            all_matches.append((keys, mtype, conf, matched_token, raw, positions))

    if not all_matches:
        return ip_hits

    # ── Select best non-overlapping matches ─────────────────────────────────

    all_matches.sort(
        key=lambda x: (
            len(x[0]),
            MATCH_ORDER[x[1]],
            -x[2],
            -len(x[5]),
        )
    )

    selected: list[tuple[set[tuple], str, float, str, str, list[int]]] = []

    used_positions: set[int] = set()

    for match in all_matches:

        keys, mtype, conf, token, raw, positions = match

        real_positions = [p for p in positions if p != -1]

        if real_positions and used_positions.issuperset(real_positions):
            continue

        selected.append(match)

        used_positions |= set(real_positions)

    # ── Intersect camera sets ───────────────────────────────────────────────

    selected.sort(key=lambda x: (len(x[0]), MATCH_ORDER[x[1]], -x[2]))

    surviving_keys: set[tuple] = selected[0][0].copy()

    for cand_keys, *_ in selected[1:]:

        new_intersection = surviving_keys & cand_keys

        if new_intersection:
            surviving_keys = new_intersection

    # ── Attach best metadata ───────────────────────────────────────────────

    token_hits: dict[tuple, tuple[str, float, str, str]] = {}

    for keys, mtype, conf, token, raw, _ in selected:

        for key in keys & surviving_keys:

            prev = token_hits.get(key)

            if prev is None or (MATCH_ORDER[mtype], -conf) < (
                MATCH_ORDER[prev[0]],
                -prev[1],
            ):
                token_hits[key] = (mtype, conf, token, raw)

    return {**token_hits, **ip_hits}


# ── Public entry point ────────────────────────────────────────────────────────


def resolve_video_resources(
    user_text: str,
    flat: list[FlatCamera],
    node_index: dict[str, list[FlatCamera]],
    ip_index: dict[str, FlatCamera],
    fuzzy_threshold: int = FUZZY_THRESHOLD,
) -> list[FlatCamera]:
    """
    Resolve raw user text to a deduplicated, ranked list of FlatCamera objects.

    Args:
        user_text:       Raw query string from the user.
        flat:            Pre-built flat camera list from flatten_tree().
        node_index:      Pre-built node index from build_node_index().
        ip_index:        Pre-built IP index from build_ip_index().
        fuzzy_threshold: Minimum rapidfuzz score to count as a fuzzy match.

    Returns:
        List of FlatCamera sorted by (match_type priority, confidence desc).
        Each camera carries:
          matched_token     — the query token that caused this match
          matched_raw_slice — verbatim substring of user_text
    """
    clauses = split_clauses(user_text)
    all_hits: dict[tuple, tuple[str, float, str, str]] = {}

    for clause in clauses:
        for key, (mtype, conf, token, raw) in _resolve_clause(
            clause, flat, node_index, ip_index
        ).items():
            prev = all_hits.get(key)
            if prev is None or (MATCH_ORDER[mtype], -conf) < (
                MATCH_ORDER[prev[0]],
                -prev[1],
            ):
                all_hits[key] = (mtype, conf, token, raw)

    results: list[FlatCamera] = []
    for cam in flat:
        if cam.key in all_hits:
            mtype, conf, token, raw = all_hits[cam.key]
            results.append(
                FlatCamera(
                    path=cam.path,
                    camera_name=cam.camera_name,
                    ip=cam.ip,
                    match_type=mtype,
                    matched_token=token,
                    matched_raw_slice=raw,
                    confidence=round(conf, 1),
                )
            )

    results.sort(key=lambda x: (MATCH_ORDER[x.match_type], -x.confidence))
    return results
