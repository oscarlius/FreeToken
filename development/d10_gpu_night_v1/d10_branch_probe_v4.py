"""Spawn-safe, external observation of the D10 scheduler branch.

This module deliberately contains no timing or CUDA synchronization.  It is
imported by the startup wrapper in both the API parent and ``__mp_main__``.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path


def _birth() -> dict[str, int]:
    stat = Path('/proc/self/stat').read_text().split()
    return {'pid': os.getpid(), 'start_ticks': int(stat[21])}


def install() -> None:
    """Install once per interpreter; the engine worker gets its own wrapper."""
    from freetoken.engine.engine import Engine
    if getattr(Engine, '_d10_v4_probe_installed', False):
        return
    original = Engine._forward_d10_staggered_decode
    event = Path(os.environ['FT_D10_BRANCH_EVENT'])

    def observed(self, argbatch, *args, **kwargs):
        # ``argbatch`` is the actual Engine method argument, not an env claim.
        result = original(self, argbatch, *args, **kwargs)
        if not event.exists():
            reqs = getattr(argbatch, 'reqs', ())
            event.parent.mkdir(parents=True, exist_ok=True)
            event.write_text(json.dumps({
                'schema': 'ft_d10_branch_event/v4',
                'method': 'Engine._forward_d10_staggered_decode',
                'entered': True,
                'actual_batch_reqs': len(reqs),
                'actual_can_use_d10_staggered': bool(getattr(argbatch, 'can_use_d10_staggered', False)),
                'candidate_commit': os.environ['FT_D10_CANDIDATE'],
                'engine_birth': _birth(),
                'engine_pgid': os.getpgid(os.getpid()),
                'at_unix': time.time(),
            }, sort_keys=True) + '\n', encoding='utf-8')
        return result

    Engine._forward_d10_staggered_decode = observed
    Engine._d10_v4_probe_installed = True
