# T06 ordinary v3: worker-received input binding

v3 is new and v2 remains frozen. It adds no product patch and changes no original message, send, or scheduler behavior.

`UserMsg` is defined in `development/e2base1/python/freetoken/message/backend.py:73-78`; the actual Engine-worker receive path is `Scheduler._process_one_msg` in `scheduler/scheduler.py:588-647`, which validates the received object then calls `PrefillManager.add_one_req`. It is not an `io.py` admission hook.

The v3 startup wrapper installs only after actual `Engine.__init__` in the worker. It observes `UserMsg.input_ids` before the original scheduler method runs and records one immutable v3 receipt per UID: full worker-received token count, canonical SHA-256 of ASCII JSON integer list (`json.dumps(ids, separators=(',', ':'))`), source location, timestamp, service birth and worker birth. The same worker records outbound `DetokenizeMsg` token sequence. Parent/tokenizer processes create no observer directory.

The v3 binder rejects a missing/duplicate UID input receipt, a worker/API birth mismatch, malformed canonical hash, a payload-file SHA mismatch, actual input length unequal to API `prompt_tokens`, token UID mismatch, or D0/route total disagreement. API `cached_tokens` remains missing when absent; D0 cached evidence remains separate and is never substituted with zero. Payload SHA is explicitly only a source-file receipt; the worker-received `input_ids_sha256` is the authoritative token identity.

Each input receipt now names an `input-<uid>.json` file written with exclusive creation. It contains the exact canonical ASCII JSON integer array used for its SHA; the receipt binds file path, SHA and length. The binder rereads that file and rejects non-ASCII/noncanonical JSON, negative/non-integer values, length or digest drift. It also requires complete service/worker birth dictionaries (`pid`, `start_ticks`, `execution_id`, `pgid`, `session`), requires worker-input timestamp strictly before the first token timestamp, and type-checks all token fields.

Normal SSE reads are now chunked. If a read fails after bytes arrive, v3 writes precisely those partial bytes to the `.sse` file and raises `ordinary SSE read error; partial raw response preserved`; it does not claim a parsed or accepted SSE result.

CPU fixture tests cover actual hook simulation and unchanged original-message return, non-Engine lazy installation, serial/two-UID token chains, duplicate/missing UID receipt, forged payload hash, tampered original ids, missing birth, input-after-token rejection, canonical SHA, and partial-SSE preservation. They are policy/fixture proof only, not an end-to-end service acceptance. They use no service, GPU, 8095 port, or model import. v3 is needed only for current T06/R049 ordinary-SSE binding and is not a general reader.
