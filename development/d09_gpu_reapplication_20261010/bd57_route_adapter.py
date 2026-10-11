"""Task-owned bd57 exact-ID route adapter.

The only executable mode is a CPU route-registration probe.  It never starts
an HTTP listener; --serve fails closed until an independently sealed admission
selects a real lifecycle runner.
"""
from __future__ import annotations
import argparse, json, os

def install_route():
    import torch
    if torch.cuda.is_initialized():
        raise RuntimeError('CPU route probe must not initialize CUDA')
    from fastapi import HTTPException
    from pydantic import BaseModel
    from freetoken.server import api_server as api
    class Request(BaseModel):
        input_ids: list[int]
        max_tokens: int = 32
    @api.app.post('/internal/t17/exact-ids')
    async def exact_ids(request: Request):
        if not request.input_ids or request.max_tokens < 1:
            raise HTTPException(400, 'nonempty IDs and max_tokens required')
        raise HTTPException(503, 'CPU preflight adapter cannot generate')
    return {'route': '/internal/t17/exact-ids', 'app': type(api.app).__name__, 'cuda_initialized': torch.cuda.is_initialized()}

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--cpu-route-probe', action='store_true'); parser.add_argument('command', nargs='?')
    args=parser.parse_args()
    if args.cpu_route_probe:
        print(json.dumps(install_route(), sort_keys=True)); return
    raise SystemExit('refusing service start: CPU-only adapter requires sealed external admission')
if __name__ == '__main__': main()
