# Independent watcher review — D09 T16 to Strata S2 retry-1 v4

Remote review clock: `2026-10-10T00:54:10.773343+08:00`. Source SHA: `43af69804331133eaef360edeb128e76e8b9af58dff67e06b913c7709642def9`.

## Verdict

**NOT_ADMISSIBLE_DURABILITY_HARDENING_REQUIRED. Keep v4 waiting.**

V4 closes the functional W3–W7 gaps. It validates exact terminal status identity, requires regular source/owner/status evidence, checks all-interface TCP/TCP6 LISTEN state and wildcard port binds, rejects dangling cleanup/production markers, validates owner port shape, records owner identity and socket evidence, and fsyncs file content plus the coordination append. V3 is stopped; v4 `246860:165931524` waits for active D09 `199552:165838035`; D09 remains loading and no successor artifact exists.

Two durability/provenance controls remain. The packet runner, immutable R2 receipt, and independent review are read and hashed without `require_regular`, so their path types are unproved. New immutable files are fsynced before `chmod`, but their post-chmod metadata and parent-directory entries are not fsynced. Require all packet evidence to be ordinary non-symlink files; then fsync each file after chmod and its parent directory after new cleanup/preflight/admission/driver artifacts.

No D09 terminal claim, GPU allocation, service, HTTP request, or mutation occurred here.
