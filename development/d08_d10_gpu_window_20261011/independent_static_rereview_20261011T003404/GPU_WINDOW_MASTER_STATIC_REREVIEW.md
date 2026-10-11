# GPU window master static rereview

**Verdict: `APPROVED_STATIC_SCOPE`.** This review performed no GPU, remote CPU, service, HTTP, or test action.

`hybrid_service.require_master_context` now rejects an imported/direct use before `idle`, GPU lock acquisition, or `Popen`, unless the actual `gpu_window.py` entry is `__main__`; it binds the master SHA, one `window_started` and `481_stopped` event, live master PID/start ticks, and the shared restoration reserve. `gpu_window.py` records that identity and deadline before dispatch.

Under the stated independent-arm policy, an eta error may permit D08 only after eta cleanup proves safe; any cleanup failure raises before later work. Runtime correctness, measurements, cleanup, terminal evidence, and restoration remain separate post-run gates.

