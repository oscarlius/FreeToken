# T08 runner

`t08_runner.py` uses `e2_runtime.CardRunner.round_scope()` and `service()`.
It is Linux-only, creates no round without `--run`, and leaves closure to the
root reviewer. P1 requires an assigned `E2-R###`; P2 requires its distinct
`E2-R###-p64k` ID.

Both phases launch exactly `numactl --interleave=all taskset -c 1,3-47`, then
verify the owned service affinity equals `{1,3..47}`. They run D0-off,
layer-major, prefill 4096 and checkpoint. P1 uses window 49152; P2 uses 73728.
The runner records hashes for every original probe, evaluator, trace, and
historical s5A input, and checks parsed layer-major/prefill/checkpoint/window
arguments before traffic.

The parsed-argument gate uses `max_extend_tokens=4096`: although the launch
flag is `--max-prefill-length`, `server/args.py` declares that flag with
`dest="max_extend_tokens"`. The other parsed fields are their actual
`ServerArgs` names: `prefill_layer_major`, `special_token_ckpt`, and
`max_seq_len_override`. P2 preserves the same three shared settings and only
changes the expected window to 73,728.

P1 preserves the first shot, runs two cold 32K, short 2000/512, and runs the
determinism probe with the literal historical cold ID `s5A`. It first requires
the old/new `(cold_id,built_tokens,prompt_tokens,cached_tokens)` tuple to
match, then compares text byte-for-byte with historical `pLM_s5A`, records the original concurrency
gap output, and executes reverse, forward and edit-at-10 agent replay under
`FT_REPLAY_MAX_TOKENS=200`. Replay validation requires twelve live non-error
rows and anchors every round's `trace_messages_sha` to the source trace's own
recorded digest. Edited replay hashes may differ only on rows reported as
edited. D06 remains explicitly pending.

P2 derives and binds its parent P1 RID by removing `-p64k`. Before starting it
requires P1's matching admission commit/tag, one completed measurement status,
P1 measurement summary and actual P1 source archives; it writes their SHA256
binding into the P2 round. P1 need not already be closed with a manifest.

Quality and soak return codes are retained and do not trigger a retry; when
they succeed their original artifacts are parsed. Historical quality comparison
is only meaningful when evaluator SHA is identical. A successful soak artifact
must report 1800 seconds and zero errors for the card's usable-number gate.
