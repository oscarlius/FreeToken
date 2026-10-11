"""Freeze the D16 native workload reader after its reviewed observer parent."""
from __future__ import annotations

import hashlib
from pathlib import Path

import d16_batch_observer_sync_cpu as sync


PARENT = "8994a465cfb5a141832478a65ced3b57579905e3"
# The first authorized 8994a465 -> 3d95cd5 transfer is retained as a failed
# immutable stage.  A repair must fast-forward from that remote head.
SYNC_PARENT = "13db9dcf0663134739f812b9ac7a1d3e9e7c09a4"
INVOKER_SOURCE = Path(__file__).read_bytes()
INVOKER_SOURCE_SHA256 = hashlib.sha256(INVOKER_SOURCE).hexdigest()


def main() -> None:
    # The delegated freezer derives its isolated stage suffix from ``__file__``.
    # Point it at this immutable invoker so the report path is bound to this wrapper,
    # while preserving its existing bundle, source-inventory, import, and sealing logic.
    # PARENT remains the reviewed provenance baseline; SYNC_PARENT is only the
    # already-synced remote fast-forward parent after its retained failed stage.
    sync.PARENT = SYNC_PARENT
    sync.__file__ = __file__
    sync.main()


if __name__ == "__main__":
    main()
