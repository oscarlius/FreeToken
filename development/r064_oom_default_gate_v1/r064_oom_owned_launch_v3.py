#!/usr/bin/env python3
"""R060b: publish the exact owner identity before native T16 preflight."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
V3 = HERE / 'r064_oom_owned_launch_v2.py'
RID = 'E2-R064-gate-OOM'


def runtime():
    spec = importlib.util.spec_from_file_location('r060b_retained_v3', V3)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    # The retained writer/argv functions must identify this actual entry.
    module.__file__ = str(Path(__file__).resolve())
    module.RID = RID
    module.REVIEW = module.ROOT / 'runs/dev_OOM/reviews/E2-R064-gate-OOM-v1'
    module.dry_dir = lambda: module.ROUNDS / '.dryrun_R060c_v3_E2-R064-gate-OOM'
    original_sources = module.sources
    module.sources = lambda: {
        **original_sources(), str(V3): hashlib.sha256(V3.read_bytes()).hexdigest()
    }
    original_run = module.run_owned_runner

    def run_owned(runner, owner, d07):
        # Native Runner.gate accepts an existing lock only when token/inode
        # already match. Its later lock_take still verifies without reopening.
        runner.token = owner['lock_token']
        runner.lock_inode = owner['lock_inode']
        return original_run(runner, owner, d07)

    module.run_owned_runner = run_owned
    return module


if __name__ == '__main__':
    runtime().main()
