# T17 HC diagnostic integration

This is a diagnostic-only integration for the retained original `FT_LM_CHUNK=4096` path. It does not change engine source, launch a service, reserve a round, or establish T17/E2-base.1 acceptance.

`t17_hc_startup.py` imports only `target_structure()` and `PARSER_SHA` from `t17_projection_startup.py`; importing does not execute projection startup. Before weights/Engine construction it validates HF PLE `[2]` maps to decoder `[1]`, requires `FT_T17_HC`, validates retained `t17_original_startup.py`, and installs `t17_hc_observe` on the inner Qwen4Exp model. Its CPU spawn proof schema is `ft_t17_hc_spawn/v1`, requires the exact-ID endpoint and wrappers, `hc_engine_init=init_hc`, `reply_wrapper=reply_hc`, and `cuda_initialized=false`.

The runner retains the real exact-ID lifecycle: an 8193-token warm donor with `max_tokens=2` is observed at `cached=4608`, `device=8193`, `extend=3585`; the warm hit uses the same 8257-token query at `cached=8192`, `max_tokens=128`; an independent cold service runs that query with cache zero and is observed at `cached=4608`, `device=8257`, `extend=3649`.

All nine roles must cover rows `4608..4671`. The runner reloads the CPU tensor files, compares uint8 bytes with signed-zero-aware counts, then retains the 128-token/text/raw validator plus four restore roles and suffix-8256 comparison.

`t17_hc_read.py` sends a frozen launch receipt through stdin to SSH host 9. It clears CUDA visibility, checks frozen source and actual launch receipts, terminal PID birth ticks, lock release, observer receipts/tensors, and re-evaluates measured validation. Its report schema is `ft_t17_hc_cpu/v1`; this CPU review is not acceptance.
