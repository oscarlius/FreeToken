# D15 WINDOW AB canonical closure

`E2-D15-WINDOW-AB-20261010` is sealed as **not_met**. The canonical round is `/data2/_shared/runs/ft_rounds/E2-D15-WINDOW-AB-20261010`: round SHA `b5910b478143662b046dd94db3fd253206bbd75b5fdbacea0b133606f9fbc17f`, manifest SHA `29b4cc0364a48af8ccbd2e871ad572af51ff549d52065a58f30112611e1d8536`, and read-only pin SHA `cf4eb4b85d9325f7d6abb81a1f924e28d395e40cc218991d3b98d1db73bc2044`.

The closure binds independent review `7468d001c90c4a9f6cab16721f6fa67dbdaa4e81be1ba13ed916d04f2c7f687e` and complete hardlinked maps for both raw runs. It preserves the original `failed_harness` carrier and the resumed `not_met` carrier. The resumed cold request reached a model CUDA OOM at 129024 prompt tokens, so no TTFT or decode completion is claimed.

Evidence records 2 services, 21 dispatched and 20 completed calls, exact A8 native equality, W98K/W128K actual slots 2700/2400, and a measured 4.200859186% pooled A decode decline. Historical cleanup is hash-bound to the completed window receipts; current production state was deliberately not queried.

`round_json_append.py ... check` passed after sealing. No GPU, service, HTTP/API, lock, or source/product operation occurred during this archive closure.
