from __future__ import annotations

from typing import List, Tuple

from .models import MatchedEvent


def validate_events(
    matched_events: List[MatchedEvent],
    valid_events: List[str],
) -> Tuple[List[MatchedEvent], List[MatchedEvent]]:
    """
    Validate matched events against the whitelist.

    Returns:
        valid:   MatchedEvent objects that passed validation
        invalid: MatchedEvent objects that were hallucinated
    """

    valid_set = set(valid_events)

    valid: List[MatchedEvent] = []
    invalid: List[MatchedEvent] = []

    for event in matched_events:
        if event.event_name in valid_set:
            valid.append(event)
        else:
            invalid.append(event)

    if invalid:
        print(
            "[WARNING] Hallucinated events removed:",
            [e.event_name for e in invalid],
        )

    return valid, invalid
