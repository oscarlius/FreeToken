# D09 T16 batch163 executable closure handoff

2026-10-10T13:25:15.715640+08:00 — read-only mapping.

`CandidateRunner` does **not** initialize a formal round. The root must create a new bd57/batch163-specific closure adapter after terminal evidence exists. It creates the initial `ft_round/v2` `pending_review` document, validates all 8/100 raw evidence and bindings, then invokes `round_close.py` to create `round_history`/`MANIFEST.sha256`, and only then uses `round_json_append.py ... verdict --new kept`. The batch144/c17 closer is not reusable. T17 requires exact hashes of the resulting immutable kept `round.json` and `MANIFEST.sha256`, plus bd57, 8-service, and 100-call identity fields.
