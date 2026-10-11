# T06 ordinary observer v2 CPU preparation

The v1 tool remains unchanged. v2 adds `r046c_t06_ordinary_startup_v2.py` and `r046c_t06_ordinary_client_v2.py`; neither changes product code, enables pause, emits an old `ft_dev` ACK, or opens a listener.

The startup wrapper follows R057's delayed-Engine pattern. Parent and tokenizer children only install the `Engine.__init__` wrapper. When the actual Engine worker initializes, it creates the observer directory, hooks `SchedulerIOMixin._reply_tokenizer_rank0`, and records the real scheduler-outbound `DetokenizeMsg` fields before the original send: UID, sequence, token id, delta, cumulative count, terminal state/reason, service birth and worker birth. It rejects an event after that UID terminal state and writes a shutdown marker through `atexit`.

The v2 client captures raw normal SSE bytes before parsing. It rejects port 8095, a pause-enabled environment, and any `ft_dev` event. Binding rereads the raw bytes and SHA, requires `chatcmpl-{uid}`, API usage and finish to match that raw evidence, validates a contiguous observer token sidecar, and binds that UID to D0 prefill schedule plus route prefill and decode records. Route records are parsed through the existing route analyzer, including each validated NPZ SHA. It requires decode route token count to equal `completion_tokens - 1`, the ordinary scheduler shape where prefill samples the first output token and each later output token has one decode route input.

Missing API `prompt_tokens_details.cached_tokens` remains explicitly `missing`, never synthetic zero. The binding still uses real D0 new + cached totals against API prompt usage and records D0 cached separately, but marks API cache evidence as not independently verified. When the API field exists it must be a non-negative integer identical to D0 cached tokens.

CPU verification: `python -m pytest development/tests/test_r046c_t06_ordinary_v2.py -q`. Coverage includes mixed UID flow in the observer, no observer activation before Engine construction, terminal rejection, duplicate sequence/terminal-tail/UID sidecar failure, missing API cache usage, raw partial HTTP error preservation, raw-SSE replay, D0/route/NPZ checks, and the socket guard. No GPU or service was started.

Root owns later D07-repair integration, Linux FILEDRY, startup review, and any real T06 execution. This is a CPU implementation only, not T06 acceptance.
