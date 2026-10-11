# Restore04 cold32K retry1 independent audit

The raw result remains `failed_harness`. Its validator required a usage field that the release API intentionally omits for zero cached tokens.

The completed stream binds `prompt_tokens=32064`, `completion_tokens=128`, TTFT 6.91625252389349 s, and decode 35.55916612085595 tok/s. The hash-bound production prefill line at 22:44:15 has the matching 32064 new tokens and `cached-token: 0`, so it is evidence for this dispatched request.

This review does not promote a formal cold baseline or cross-environment acceptance claim.
