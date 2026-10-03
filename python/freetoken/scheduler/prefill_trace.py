"""Stable schedule-time labels for prefill segment instrumentation."""

SEG_REASON_ANCHOR_CAP = "anchor_cap"
SEG_REASON_TOKEN_BUDGET = "token_budget"
SEG_REASON_LAYER_MAJOR_WHOLE = "layer_major_whole"
SEG_REASON_CONTINUATION = "continuation"
SEG_REASON_OTHER = "other"

# Higher entries win when a batch contains requests capped for different reasons.
PREFILL_SEG_REASONS = (
    SEG_REASON_ANCHOR_CAP,
    SEG_REASON_TOKEN_BUDGET,
    SEG_REASON_LAYER_MAJOR_WHOLE,
    SEG_REASON_CONTINUATION,
    SEG_REASON_OTHER,
)
