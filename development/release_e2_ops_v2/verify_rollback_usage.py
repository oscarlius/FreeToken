"""Read-only CPU check of the rollback completion stream's usage contract."""
import argparse
import ast
import asyncio
import hashlib
import json
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace


def verify(worktree, commit):
    worktree = Path(worktree)
    head = subprocess.check_output(['git', '-C', str(worktree), 'rev-parse', 'HEAD'], text=True).strip()
    if head != commit:
        raise ValueError('Rollback source commit differs')
    source = worktree / 'python/freetoken/server/openai_api.py'
    blob = source.read_bytes()
    tree = ast.parse(blob)
    names = {'stream_completion_chunks', '_usage', '_reported_cached', '_sse'}
    nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
             and node.name in names]
    if {node.name for node in nodes} != names:
        raise ValueError('Rollback stream implementation was not found')
    module = ast.Module(body=[ast.ImportFrom(module='__future__',
        names=[ast.alias(name='annotations')], level=0), *nodes], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {'json': json, 'time': time}
    exec(compile(module, str(source), 'exec'), namespace)

    class State:
        config = SimpleNamespace(enable_cache_report=True)

        async def wait_for_ack(self, uid):
            assert uid == 41
            yield SimpleNamespace(error=None, prompt_tokens_delta=512,
                completion_tokens_delta=128, cached_tokens=0,
                incremental_output='cpu fixture', finished=True, finish_reason='length')

    async def collect(include_usage):
        req = SimpleNamespace(model='cpu-fixture',
            stream_options=SimpleNamespace(include_usage=include_usage))
        return [chunk async for chunk in namespace['stream_completion_chunks'](41, req, State())]

    with_usage = asyncio.run(collect(True))
    without_usage = asyncio.run(collect(False))
    decode = lambda chunks: [json.loads(chunk[6:]) for chunk in chunks
                              if chunk != b'data: [DONE]\n\n']
    included = [row['usage'] for row in decode(with_usage) if 'usage' in row]
    assert included == [{'prompt_tokens': 512, 'completion_tokens': 128, 'total_tokens': 640}]
    assert not any('usage' in row for row in decode(without_usage))
    assert with_usage[-1] == without_usage[-1] == b'data: [DONE]\n\n'
    return {'schema': 'ft_rollback_stream_usage_cpu/v1', 'read_only': True,
        'worktree': str(worktree), 'commit': head, 'source': str(source),
        'source_sha256': hashlib.sha256(blob).hexdigest(),
        'functions': {node.name: {'line': node.lineno, 'end_line': node.end_lineno} for node in nodes},
        'include_usage_true': included[0], 'include_usage_false': 'no usage event',
        'usage_gate': 'retained; official SDK collector requests include_usage=true',
        'evidence_scope': 'Source functions executed on CPU with simulated acknowledgements; no HTTP or model run',
        'GPU_started': False, 'service_started': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--worktree', type=Path, default=Path('/data2/FreeToken/src/FreeToken'))
    parser.add_argument('--commit', default='184c965964b5f79deaecf1b1e3e0eda3187c829d')
    args = parser.parse_args()
    print(json.dumps(verify(args.worktree, args.commit), indent=2))
