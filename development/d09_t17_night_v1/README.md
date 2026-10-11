# D09 T17 night same-structure package

This package binds candidate `c17b69a46cd512fbf3d127d3879bce92caae457b` to two exact message-boundary cells: `20282/1020` and `22558/197`. `prepare_exact_inputs.py` obtains the IDs through the pinned remote CPU tokenizer path. The runner schedules six services and eight exact-ID calls: cold A, cold B, and donor-then-target hot for each cell.

`--filedry` exercises the real orchestration, geometry judge, and comparison path with local synthetic process/transport only. `--run` is deliberately root-admission gated and is not part of CPU preparation. A PASS requires both cold stability and hot/cold sampled-token-ID plus full-text equality; it must not be interpreted as R067d PASS.
