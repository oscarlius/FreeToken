"""CPU-only release/rollback recipe. Importing this module starts nothing."""
from pathlib import Path
import os
import re

ROOT = Path('/data2/FreeToken')
HOST = '172.16.108.9'
MODEL = 'Qwen3.8-Flash-Next-NVFP4'
MODES = {
    'release': (ROOT / 'wt/release-e2', '481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9', 98304, 4096),
    'rollback': (ROOT / 'src/FreeToken', '184c965964b5f79deaecf1b1e3e0eda3187c829d', 49152, 8192),
}


def environment(mode, parent=None):
    """Same copy/remove/set rule as d07_g3g4_prepare.clean_environment."""
    env = dict(os.environ if parent is None else parent)
    for key in list(env):
        if key.startswith('FT_') or key in ('PYTHONPATH', 'CUDA_VISIBLE_DEVICES'):
            env.pop(key)
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1',
               PYTHONPATH=str(MODES[mode][0] / 'python'),
               VIRTUAL_ENV=str(ROOT / 'venv'),
               PATH=str(ROOT / 'venv/bin') + ':' + env.get('PATH', ''),
               CUDA_VISIBLE_DEVICES='0', MASTER_PORT='8096')
    return env


def serve_argv(mode):
    _, _, window, chunk = MODES[mode]
    prefix = ['taskset', '-c', '1,3-47'] if mode == 'release' else [
        'numactl', '--cpunodebind=0,1', '--interleave=all']
    argv = prefix + [str(ROOT / 'venv/bin/ft'), 'serve',
        '--model-path', str(ROOT / 'models/Qwen3.8-Flash-Next-NVFP4-overlay'),
        '--served-model-name', MODEL, '--host', HOST, '--port', '8095',
        '--memory-ratio', '0.88', '--moe-cache-auto', '--moe-prefill-hit-d2d',
        '--ple-backend', 'pinned', '--moe-strategy', 'offload',
        '--quant-backend', 'moe.nvfp4=triton', '--max-running-requests', '2',
        '--cuda-graph-max-bs', '2', '--kv-reserve-tokens', str(window),
        '--max-seq-len-override', str(window), '--max-prefill-length', str(chunk),
        '--enable-cache-report', '--enable-special-token-ckpt',
        '--tool-call-parser', 'qwen3_coder', '--reasoning-parser', 'qwen3']
    if mode == 'release':
        argv += ['--prefill-layer-major', '--mamba-host-slots', '0']
    return argv


def environment_projection(env):
    """Only operational keys; never export arbitrary host secrets in a diff."""
    keys = {'PYTHONPATH', 'CUDA_VISIBLE_DEVICES', 'VIRTUAL_ENV', 'PATH', 'MASTER_PORT',
            'PYTHONUNBUFFERED', 'PYTHONDONTWRITEBYTECODE', 'LD_LIBRARY_PATH', 'CUDA_HOME', 'CUDA_PATH'}
    return {key: value for key, value in sorted(env.items())
            if (key in keys or key.startswith(('FT_', 'R056_')))
            and not re.search(r'PASSWORD|TOKEN|KEY|SECRET|CREDENTIAL|AUTH', key, re.I)}
