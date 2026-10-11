# Matched 8192 observer

This test-only startup observer wraps each existing Qwen4Exp decoder layer forward
call once and preserves its return value. When a child finishes at device_tokens
8192 it immediately copies only that layer's live GDN conv/recurrent state to CPU.
At the PLE layer it copies ple_conv. The ngram context is copied only by
post_commit after the original commit_ngram_context call returns, so it is the
outgoing context. wrap_ngram_commit preserves that original call and return.
It does not modify
the request, scheduler, state pool, or generation path.

GDN tensors are assembled by pool local_index order, not decoder order; the receipt
records decoder_layer_idx, gdn_layer_id and local_index for every row. After exactly
pool.num_linear_layers GDN slices and one PLE capture, it writes
one CPU tensor per four roles plus a receipt with actual UID, slot, layer ids,
cached/device/extend coordinates, shape, dtype and SHA-256. Missing/duplicate
layers, coordinate drift and replacement files reject finalize().

Use only in the matched FT_LM_CHUNK=7680 diagnostic. The launcher owns install,
finalize and artifact retention; the receipt is state evidence, not acceptance.
