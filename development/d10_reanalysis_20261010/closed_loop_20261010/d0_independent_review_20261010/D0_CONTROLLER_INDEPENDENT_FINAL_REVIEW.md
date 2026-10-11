# D0 controller independent final review

**Status: conditional local approval; remote source synchronization required before launch.**

The reviewed local controller is `6a2e64f612d533b3df18b9ba360a5aff2193c6cf1aed0e0d9eaa18c107ca8bb3`; its seven CPU tests passed. It starts the owned process before readiness, bounds readiness at T+420 under one monotonic 480-second epoch, reserves one 60-second cleanup path, proves PID/PGID/session identity, and derives a read-only PID/start-tick bound admission. Readiness now requires both `status=ok` and `maintenance=serving`; the new test rejects `loading` despite status `ok`. The D0 endpoint has no `/v1` suffix.

Remote read-only verification found a different controller (`be7504150f924c08950cda92e5e0caf2cca116ddafc7a3f2dc8705ae53bb7188`) and tests (`0ab1bc2559abb59a97ebfe7052abb0598058b2cb7feed6cd3efebf0be873a449`), with only two remote tests. Therefore this is not remote launch approval. Synchronize the reviewed sources, verify hashes, and rerun the seven tests remotely before any launch.

See the sibling JSON for complete pins, checks, and scope.
