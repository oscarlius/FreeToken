# R067e retry2 hash-domain CPU packet

Entry point: `retry2_hash_domain_packet.py`. Run it only in the FreeToken target venv with `CUDA_VISIBLE_DEVICES=''`; it reads archived hot dumps on CPU and renders an **unapproved** future retry2 plan.

The tool uses the exact Engine guard hash domain: `conv_states`, `recurrent_states`, then sorted PLE slot states labeled `slot_states/ple_conv` and `slot_states/ple_ngram_ctx`, each encoded as label, shape, dtype, and raw bytes. It preserves all four state families and fails closed; it does not relax the guard.

The plan retains the frozen 10-service/14-call scope. A donor mismatch is `failed_harness` before rewind, tail, or output; first valid product `not_met` stops remaining arms. Batch161 and D12 remain unchanged. The remaining harness attempt needs non-author review, root admission, and a separately authorized GPU run.

An external packet cannot capture a cold pool digest before the Engine guard throws. A future diagnostic needs a separately reviewed candidate Engine hook that emits the same canonical pre-guard digest; that candidate must receive a new source SHA and independent review.
