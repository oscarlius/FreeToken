# R067e retry2 task-owned execution package

This package is inert until root admission. It preserves the parent 10-service/14-call plan, exact-ID binding, SpawnFactory/route behavior, Effects lifecycle, and cleanup contract. It changes only the cold expected donor digest to the Engine canonical label domain and materializes a task-owned startup adapter that writes the cold donor-at-P digest before invoking the Engine guard.

`retry2_execution.py` reads files and archived tensors on CPU only. It does not launch a service, obtain a GPU lock, call an API, or alter candidate/parent sources. `retry2_runner.py` delegates execution to the parent actual runner only after root admission; its `Retry2Effects` performs actual file materialization and requires the pre-guard receipt. A descriptor-only launch is insufficient.
