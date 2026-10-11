"""Spawn-safe `ft serve` startup wrapper for the D10 prototype."""
from __future__ import annotations

import os
import sys
import json


def install_probe() -> None:
    if not os.environ.get('FT_D10_BRANCH_EVENT'):
        if os.environ.get('FT_D10_CPU_PROBE') == '1':
            # CPU validation imports the identical worker hook but never calls
            # the observed engine method, so no event is emitted.
            os.environ['FT_D10_BRANCH_EVENT'] = '/tmp/ft_d10_v4_cpu_probe_unused.json'
        else:
            raise RuntimeError('D10 branch event path is required')
    from d10_branch_probe_v4 import install
    install()


def cpu_spawn_probe(queue) -> None:
    """Pickleable spawn target used only by the no-HTTP/no-GPU CPU check."""
    from freetoken.engine.engine import Engine
    queue.put({'probe_installed': bool(getattr(Engine, '_d10_v4_probe_installed', False)),
               'cuda_visible_devices': os.environ.get('CUDA_VISIBLE_DEVICES', '')})


# multiprocessing spawn imports this file as __mp_main__; installing here is
# what makes the observer reach the real Engine worker before Scheduler setup.
if __name__ in ('__main__', '__mp_main__'):
    install_probe()

if __name__ == '__main__':
    if sys.argv[1:] == ['--cpu-spawn-probe']:
        import multiprocessing
        context = multiprocessing.get_context('spawn'); queue = context.Queue()
        process = context.Process(target=cpu_spawn_probe, args=(queue,)); process.start()
        proof = queue.get(timeout=60); process.join(60)
        if process.exitcode != 0 or not proof['probe_installed']:
            raise RuntimeError('spawn worker did not retain D10 probe installation')
        print(json.dumps({'schema': 'ft_d10_startup_spawn_cpu/v4', 'gpu_started': False, 'http_started': False, 'proof': proof}, sort_keys=True))
        raise SystemExit(0)
    from freetoken.cli import main
    sys.argv = ['ft', 'serve', *sys.argv[1:]]
    main()
