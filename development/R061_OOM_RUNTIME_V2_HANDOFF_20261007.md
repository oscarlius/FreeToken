# R061 v2 handoff

`r061_oom_fault_prepare_v2.py` supersedes only the v1 launcher.  V1 and all
earlier capsules remain immutable.  V2 refuses reservation and lock acquisition
unless the candidate worktree is clean at `608251f`, the native proof is 0444
with its fixed SHA, current three-input hashes match FILEDRY/review/pin, and
both review and pin are sealed `approved=true`, `verdict=PASS` documents.

FILEDRY uses the same v2 source/writer/argv environment, imports the candidate
under the required CPU guard, copies sources 0600, writes all formal output
probes, and binds an adjacent API/TCPStore pair with `MASTER_PORT`.  It stops
before Popen, listener, request, lock, batch, or formal RID.

The child delegates physical ordinary SSE/token/observer/restart proof to the
immutable v1 body only after v2 admission.  V2 forces the actual service argv
to 98304/.88 and carries the selected TCPStore pair.  Any body exception writes
`failed_harness.json` preserving raw files; it writes `owned_cleanup.json` only
when the lock is already absent, so a failed cleanup never claims release.
