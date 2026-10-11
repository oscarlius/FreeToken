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
            os.environ.setdefault('FT_D10_METRICS_TRACE','/tmp/ft_d10_v4_cpu_trace_unused.jsonl')
        else:
            raise RuntimeError('D10 branch event path is required')
    from d10_branch_probe_v4 import install
    install()


def create_app():
    """The same app imported by ft serve; assert the real chat route."""
    from freetoken.server import api_server
    paths={(r.path,tuple(sorted(r.methods or ()))) for r in api_server.app.routes}
    if ('/v1/chat/completions',('POST',)) not in paths:
        raise RuntimeError('actual chat route absent')
    return api_server.app


def cpu_spawn_probe(queue):
    from freetoken.engine.engine import Engine
    from freetoken.kernel import _cpu_moe,_pinned_tensor
    import torch
    app=create_app()
    queue.put({'probe_installed':bool(getattr(Engine,'_d10_v4_probe_installed',False)),
               'route_present':any(r.path=='/v1/chat/completions' for r in app.routes),
               'cuda_initialized':torch.cuda.is_initialized(),
               'native_imports':[_cpu_moe.__file__,_pinned_tensor.__file__],
               'engine_source':__import__('inspect').getfile(Engine),
               'cuda_visible_devices':os.environ.get('CUDA_VISIBLE_DEVICES','')})


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
        if process.exitcode != 0 or not proof['probe_installed'] or not proof['route_present'] or proof['cuda_initialized']:
            raise RuntimeError('spawn worker did not retain D10 probe installation')
        print(json.dumps({'schema': 'ft_d10_startup_spawn_cpu/v4', 'gpu_started': False, 'http_started': False, 'proof': proof}, sort_keys=True))
        raise SystemExit(0)
    create_app()
    from freetoken.cli import main
    sys.argv = ['ft', 'serve', *sys.argv[1:]]
    main()
