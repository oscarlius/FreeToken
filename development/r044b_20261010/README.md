# R044b CPU admission packet

`prepare_r044b_cpu.py` replays the retained retry2 and R047 `serve.log` files before a new R044b round may be admitted. It maps the external `--max-prefill-length` name to the actual `ServerArgs.max_extend_tokens` field, preserves the old retry2 reviews unchanged, and carries forward the 5,824 physical-capture, 4,800 sampler-row, and 8 GiB caps.

Run it with the FreeToken venv and the two exact remote log paths. The root reviewer owns the independent startup review, terminal review, and any GPU work.
