"""Invalid pre-seal CPU helper retained only as history; do not import."""

from dataclasses import dataclass
from typing import Sequence

MIN_PREFIX_TOKENS = 8192
MAX_TAIL_TOKENS = 1024


@dataclass(frozen=True)
class MessageBoundaryEligibility:
    enabled: bool
    prefix_tokens: int
    tail_tokens: int
    eligible: bool
    reason: str


def preceding_message_boundary(previous_input_ids: Sequence[int], current_input_ids: Sequence[int], *, enabled: bool = False, min_prefix_tokens: int = MIN_PREFIX_TOKENS, max_tail_tokens: int = MAX_TAIL_TOKENS) -> MessageBoundaryEligibility:
    prefix = 0
    for previous, current in zip(previous_input_ids, current_input_ids):
        if previous != current:
            break
        prefix += 1
    tail = len(current_input_ids) - prefix
    if not enabled:
        return MessageBoundaryEligibility(False, prefix, tail, False, "disabled")
    if prefix < min_prefix_tokens:
        return MessageBoundaryEligibility(True, prefix, tail, False, "prefix_too_short")
    if tail > max_tail_tokens:
        return MessageBoundaryEligibility(True, prefix, tail, False, "tail_too_long")
    return MessageBoundaryEligibility(True, prefix, tail, True, "eligible")
