# One-service D0 controller

Default inert. The root-sealed admission must pin this controller, the sealed allxy admission, and every listed source file. `--run` starts exactly one release-e2 98K service on `127.0.0.1:32103`, TCPStore `32203`, with `FT_DEV_D0=1` and the admitted private D0 base. It delegates only the admitted D0 X/Y phase to `allxy_runner` (four generation calls at concurrency two), has no warmup path, and uses one absolute 480-second budget for startup, calls, and cleanup.

The lock is released only after the inherited cleanup proves the owned process group absent, both ports reusable, and GPU idle. A failed cleanup retains the lock.
