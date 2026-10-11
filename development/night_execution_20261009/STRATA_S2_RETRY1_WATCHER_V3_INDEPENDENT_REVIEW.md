# Independent watcher review — D09 T16 to Strata S2 retry-1 v3

Remote review clock: `2026-10-10T00:52:18.144444+08:00`. Source SHA: `5eb7309c9ddee78785733f3f373769393b251d124062e4b641f9ab46c86d45b4`.

## Verdict

**NOT_ADMISSIBLE_WATCHER_SOURCE. Keep v3 waiting; do not permit it to advance.**

V1 and v2 watcher PIDs are absent. V3 `240144:165919121` is correctly waiting for the active D09 child `199552:165838035`; D09 is still `loading`, and no cleanup, preflight, root admission, or S2 driver receipt has been written.

V3 corrects the earlier symlink and owner-custody defects: it rejects present or dangling lock/production markers, requires nonempty owner evidence, and records owner PID/start-ticks/PGID, port, group absence, and port rebound in cleanup readback. It retains the bounded S2 review, full FILEdry equality, exact 3-service cap, and 11-call admission.

Two defects remain. The terminal status file is accepted only by its `state`; the watcher must bind its RID, batch, and child PID to the exact D09 object. Its port test binds `127.0.0.1` only, which does not rule out a stale listener on another IPv4 address or IPv6. It must retain an all-interface TCP no-LISTEN snapshot for the owner and tcpstore ports.

No terminal conclusion, product acceptance, GPU allocation, service, HTTP request, or mutation was performed in this review.
