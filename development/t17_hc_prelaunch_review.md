# Standalone HC diagnostic prelaunch review

The exact stage `/data2/FreeToken/runs/dev_D14/hc_a5ba447e30df` has CPU report
SHA256 `5f4d5582f5786e7c76f626dfc256386e5f813244d534fac1167a5fb5c4d77a32`.
An independent read-only verifier rehashed all 22 sources and checked the
0555 directory, 0444 files, logs and actual candidate hook routing before GO.
Linux evidence: 15 HC observer/integration/startup/runner tests, 10 original
gate tests, compile and normal spawn passed. Spawn executed the protected
served configuration through the actual candidate parser, HF `[2]` to decoder
`[1]`, with CUDA uninitialized, exact-ID endpoint and HC wrappers installed.

The earlier stage `hc_3f22a1e378b7` is retained: its stage environment used the
old projection variable, and HC startup rejected it before Engine/weights.
The corrected stage uses `FT_T17_HC`; the failed CPU stage did not allocate a
round or use the GPU.

The protocol preserves candidate e4f3202, original exact inputs, default
`FT_LM_CHUNK=4096`, donor 8193/2 tokens, hit 8257/cache8192/128 tokens, and fresh
cold 8257/cache0/128 tokens. It observes decoder0 embedding/HC/GDN boundaries
only over shared rows `[4608,4672)`, while real logical M remains 3585 or3649.
Finalization rejects wrong UID/slot/coordinates, duplicate or missing roles;
all original calls and result objects are retained. It records actual operator
metadata without inferring a quantization implementation from the model name.

After GO and successful resource preflight, the atomic launcher reserved
`E2-R030-diagnostic-T17` / batch58. Actual batch PID/PGID/session699131,
birth122786283; first warm service699532/birth122786916. The initial monitor and
22-source launch receipt were captured in this directory. Measurement was
still pending at this record's creation; this proof grants diagnostic launch,
not T17/E2-base.1/T10 acceptance or a numerical-cause/performance conclusion.
