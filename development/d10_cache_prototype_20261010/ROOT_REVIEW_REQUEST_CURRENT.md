# C independent-startup review request

Use `CURRENT_MANIFEST.json`, `ROOT_ADMISSION_TEMPLATE.json`, `CPU_LIFECYCLE_RECEIPT.json`, and the source pins together. Launch only after an independent reviewer seals a concrete admission using remote runtime-derived `runner_source_sha256` and `candidate_proof`.

Command shape: `/data2/FreeToken/venv/bin/python /data2/FreeToken/development/d10_cache_prototype_20261010/d10_cache_prototype_consumer.py --run --admission <sealed-path>`; child argv is self-referential and controller-owned. Service argv remains FT syntax; taskset affinity is external. Budget is one service, four frozen profiles, eight total calls, max 256 tokens; terminate on the first failed profile and enforce the existing normal-workload cap. T16 transfer is default-off and requires independent review; this packet does not approve it.
