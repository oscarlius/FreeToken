"""External D10 branch observer.  It never modifies the candidate tree."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path


def install() -> None:
    """Install exactly one in-process observation of the enabled D10 branch."""
    from freetoken.engine.engine import Engine

    original = Engine._forward_d10_staggered_decode
    emitted = False

    def wrapped(self, *args, **kwargs):
        nonlocal emitted
        if not emitted:
            target = Path(os.environ["FT_D10_BRANCH_EVENT"])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps({
                "schema": "ft_d10_branch_event/v3",
                "method": "Engine._forward_d10_staggered_decode",
                "entered": True,
                "eligible_lanes": int(os.environ["FT_D10_ELIGIBLE_LANES"]),
                "candidate_commit": os.environ["FT_D10_CANDIDATE"],
                "service_pid": os.getpid(),
                "at_unix": time.time(),
            }, sort_keys=True) + "\n", encoding="utf-8")
            emitted = True
        return original(self, *args, **kwargs)

    Engine._forward_d10_staggered_decode = wrapped
