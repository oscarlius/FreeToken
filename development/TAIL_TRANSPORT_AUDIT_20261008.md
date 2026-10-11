# R052 v5 / R044 v5 / R047 v9 tail transport audit

Date: 2026-10-08.  Scope is a bounded read-only trace of the current formal
entry sources and their CPU-stage copies.  No service, socket, GPU, lock,
FILEdry, formal round, or product source was started or changed.  The three
entries remain queued behind their declared closures; this note changes no
admission or verdict.

| Entry | Positive source path and checked chain | Result |
| --- | --- | --- |
| R052 v5 | `r052_t11_replay.py:112-126` calls the frozen candidate's real `build_payload` then normal SSE `post_events`; the candidate function exists at `wt/e2base1-ordinary-rewind/scripts/_agent_trace_original.py:234-247`.  `stream_uid` uses `chatcmpl-{uid}` as the required identity and treats `ft_dev` only as an optional consistency check (`r052_t11_replay.py:82-98`).  The worker rejects route/pause configuration (`r052_d0_shutdown_startup_v1.py:16-18`). | No forced ACK/pause mismatch and no nonexistent helper.  Its 200/64 values are bounds: `request` accepts `stop`, `length`, or `tool_calls` and does not assert exact completion length (`r052_t11_replay.py:112-161`), so absence of `ignore_eos` is not an exact-length defect. |
| R044 v5 | The replay adapter makes ordinary SSE mandatory and rejects every `ft_dev` event (`r046c_t06_ordinary_client_v2.py:44-89`); `validate_replay` additionally requires `ordinary_sse_no_ft_dev_ack` and forbids `ack_schema` (`t10_e2_r044_prepare.py:154-171`).  Service plan writes `route_trace:false`, `pause:false` (`:241-250`). | No ACK/pause mismatch.  `REPLAY_MAX_TOKENS=200` is explicitly a cap, with actual terminal length required in `[1,200]` (`t10_e2_r044_prepare.py:338-339`); it is not an exact-200 claim, so `ignore_eos` is not required for this contract.  The adapter records API cache field as missing versus reported and binds reported values to D0 (`r046c_t06_ordinary_client_v2.py:151-185`), before R044 requires integer cache evidence. |
| R047 v9 | Six-arm entry remains gated by `E2-R044 measured` and the other formal predecessors (`t03b_e2_r047_prepare_v9.py:47-50`).  It uses ordinary OpenAI SSE (`stream_request`, `:277-292`), has no ACK reader, and supplies no pause/route-trace environment (`start_server`, `:199-217`).  The 2048 positive and 64 negative token values only feed qualitative trigger/negative probes (`:301-335`, `:535-547`); no equality-to-max completion assertion exists. | No forced ACK/pause or exact-length/EOS defect. **Evidence-label defect:** `stream_request` permits missing API `cached_tokens` (`:284-288`), but `_run_arms` stores that optional value as `post_trigger_cache_hit_length` (`:542-563`) and `summarize_arms` does not require cache evidence (`:573-590`).  A completed result can therefore contain `null` under a field whose name implies a proven cache hit. |

All three runtime copy routines explicitly use `shutil.copyfile`, chmod the
copy to `0600`, and compare hashes (`R052: r052_t11_replay.py:174-183`; R044:
`t10_e2_r044_prepare.py:37-44`; R047: `t03b_e2_r047_prepare_v9.py:95-111`).
This prevents a copied source from inheriting a read-only source mode.  The
CPU tests import their intended versioned entry paths: R052
`test_r052_runtime_v5.py:114-115`, R044 `test_t10_e2_r044_prepare.py:4`, and
R047 `test_t03b_e2_r047_prepare_v9.py:13-17`.  Existing CPU evidence is
R052 v5 38 pass (`R052_RUNTIME_CPU_V5_20261007.json`), R044 v5 29 pass
(`R044_RUNTIME_CPU_V5_20261007.json`), and the separate R047 v9 stage path
`/data2/FreeToken/runs/dev_T03b/r047_runtime_v9_cpu_20261007_233456`.

## R047 card requirement and minimal necessary repair

The T03b card retains cache readings as a required measurement: its formal
design names `post-trigger cache-hit length` beside each arm's final snapshot
count and first-token timing (`t03b_e2_r047_prepare_v9.py:351-360`), while
the handoff states that each arm records its cached-token reading
(`development/T03B_TRIGGER_READ_20261006.md`).  It must therefore not be
dropped or silently renamed away.

Current D0 can provide the authoritative scheduled cache length: its prefill
records have `{rid,new_tokens,cached_tokens}`, and R052 already proves the
correct first-admission/continuation accounting pattern
(`r052_t11_replay.py:256-299`).  R047 currently enables that D0 writer, but
does not parse it, and its ordinary SSE records only hold the unbound API
usage/event list.  D0 alone contains no input SHA.  The narrow new-version
tooling should therefore, for the final positive turn only: (1) bind the
ordinary SSE `chatcmpl-{uid}` to the raw SSE SHA and a canonical request-input
SHA; (2) bind that same UID to its D0 prefill rows; (3) require the first
admission's integer `cached_tokens`, require continuation cache values to be
zero, and require D0 `cached + sum(new) == API prompt_tokens`; (4) publish
both `api_cache: {state: reported|unreported, value: int|null}` and
`scheduled_cached_tokens: int` under the retained `post_trigger_cache_hit`
record.  An unreported API field stays `unreported` (never `0`); a cache-hit
claim requires the complete UID/input-SHA/D0 binding.  Existing T10's
`r046c_t06_ordinary_client_v2.py:151-185` is the proven shape for this
ordinary-SSE plus D0 binding, but R047 must record its own final-turn input
identity rather than fabricate it from a response.

Do not change the D0 snapshot criterion, predecessor closure, candidate, or
launch policy as part of this repair.
