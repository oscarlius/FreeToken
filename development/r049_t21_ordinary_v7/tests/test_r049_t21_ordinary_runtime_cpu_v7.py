"""Exercise the actual ordinary binder and spawn target without a model/GPU."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name.removesuffix('.py'), HERE / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def request_receipts(tmp_path):
    payload = tmp_path / 'payload.json'
    payload.write_text(json.dumps({'stream': True, 'stream_options': {'include_usage': True},
                                  'messages': [{'role': 'user', 'content': 'test'}]}))
    raw = tmp_path / 'api.sse'
    events = [
        {'id': 'chatcmpl-7', 'choices': [{'delta': {'content': 'ok'}, 'finish_reason': None}]},
        {'id': 'chatcmpl-7', 'choices': [{'delta': {}, 'finish_reason': 'stop'}],
         'usage': {'prompt_tokens': 2, 'completion_tokens': 2}},
    ]
    raw.write_bytes((''.join('data: ' + json.dumps(e) + '\n\n' for e in events)
                     + 'data: [DONE]\n\n').encode())
    api = tmp_path / 'api.json'
    clocks = tmp_path / 'api.events.jsonl'
    clock_rows = [{'monotonic_ns': mono, 'time_ns': wall, 'event': event}
                  for event, mono, wall in zip(events, (110, 1_000_000_110), (1000, 2000))]
    clocks.write_text(''.join(json.dumps(row)+'\n' for row in clock_rows))
    api.write_text(json.dumps({'schema': 'ft_r049_ordinary_sse_stream/v1', 'pause_enabled': False,
                              'payload_source': {'path': str(payload), 'sha256': digest(payload)},
                              'sse': str(raw), 'sse_sha256': digest(raw), 'uid': 7,
                              'usage': events[-1]['usage'], 'finish_reason': 'stop',
                              'events': str(clocks), 'events_sha256': digest(clocks),
                              'dispatch_monotonic_ns': 100,
                              'first_output_event': {'monotonic_ns': 110, 'time_ns': 1000},
                              'terminal_event': {'monotonic_ns': 1_000_000_110, 'time_ns': 2000}}))
    service = {'pid': 1, 'start_ticks': 13, 'execution_id': '1:13', 'pgid': 1, 'session': 1}
    worker = {'pid': 2, 'start_ticks': 14, 'execution_id': '2:14', 'pgid': 1, 'session': 1}
    ids = tmp_path / 'ids.json'
    ids.write_bytes(b'[10,11]')
    inputs = tmp_path / 'inputs.jsonl'
    inputs.write_text(json.dumps({'schema': 'ft_t06_ordinary_input/v3', 'uid': 7, 'input_tokens': 2,
                                 'canonical_encoding': 'utf8-json-int-array-separators=,:',
                                 'input_ids_path': str(ids), 'input_ids_sha256': digest(ids),
                                 'input_ids_file_sha256': digest(ids),
                                 'source': 'Scheduler._process_one_msg(UserMsg)', 'time_ns': 10,
                                 'service_birth': service, 'worker_birth': worker}) + '\n')
    tokens = tmp_path / 'tokens.jsonl'
    token_rows = [{'schema': 'ft_t06_ordinary_token/v3', 'uid': 7, 'request_seq': n,
                   'completion_tokens_delta': 1, 'completion_tokens_cumulative': n,
                   'next_token': 20 + n, 'finished': n == 2,
                   'finish_reason': 'stop' if n == 2 else None, 'time_ns': 10 + n,
                   'service_birth': service, 'worker_birth': worker} for n in (1, 2)]
    tokens.write_text(''.join(json.dumps(row) + '\n' for row in token_rows))
    return payload, api, inputs, tokens, ids, raw


def bind_receipts(tmp_path, receipt):
    payload, api, inputs, tokens, _, _ = receipt
    return load('r049_t21_ordinary_client_v7.py').bind(
        payload, api, tmp_path / 'absent-d0', tmp_path / 'absent-route',
        inputs, tokens, tmp_path / 'binding.json')


def test_production_binding_checks_actual_stream_ids_and_driver_shape(tmp_path):
    receipt = request_receipts(tmp_path)
    row = bind_receipts(tmp_path, receipt)
    assert row['schema'] == 'ft_r049_t21_ordinary_binding/v7'
    assert row['route'] is None and row['d0'] is None
    assert [r['next_token'] for r in row['token_sidecar']['events']] == [21, 22]
    assert row['api']['uid'] == 7
    assert row['payload_source']['sha256'] == digest(receipt[0])


@pytest.mark.parametrize('which', ['payload', 'ids', 'sse', 'early_terminal', 'clock'])
def test_production_binding_rejects_unbound_or_nonterminal_evidence(tmp_path, which):
    receipt = request_receipts(tmp_path)
    if which == 'payload':
        receipt[0].write_text('{}')
    elif which == 'ids':
        receipt[4].write_bytes(b'[10,12]')
    elif which == 'sse':
        receipt[5].write_bytes(receipt[5].read_bytes().replace(b'chatcmpl-7', b'chatcmpl-8'))
    elif which == 'clock':
        api = json.loads(receipt[1].read_text())
        api['first_output_event']['monotonic_ns'] = 5
        receipt[1].write_text(json.dumps(api))
    else:
        rows = [json.loads(x) for x in receipt[3].read_text().splitlines()]
        rows[0]['finished'] = True
        receipt[3].write_text(''.join(json.dumps(row) + '\n' for row in rows))
    with pytest.raises((RuntimeError, ValueError)):
        bind_receipts(tmp_path, receipt)


def write_module(root, relative, body):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    source = textwrap.dedent(body)
    compile(source, str(path), 'exec')
    path.write_text(source, encoding='utf-8')


@pytest.mark.skipif(sys.platform != 'linux', reason='real worker birth requires Linux /proc')
@pytest.mark.parametrize('shutdown_mode', ['interrupt', 'sigterm'])
def test_real_spawn_installs_both_observers_in_worker_only(tmp_path, shutdown_mode):
    fake = tmp_path / 'fake'
    for name in ['freetoken', 'freetoken/server', 'freetoken/message', 'freetoken/utils',
                 'flashlib', 'flashlib/kernels', 'equiv_suite']:
        write_module(fake, name + '/__init__.py', '')
    write_module(fake, 'torch.py', 'from contextlib import nullcontext\ndef inference_mode(): return nullcontext()\n')
    write_module(fake, 'flashlib/kernels/slot_cache.py', 'class Stat: ACTIVE = 0\n')
    write_module(fake, 'equiv_suite/service_capture.py', '''
        class ServiceCaptureAdapter: pass
        class ServiceCaptureError(RuntimeError): pass
        def install_from_env(engine): return None
    ''')
    write_module(fake, 'freetoken/server/launch.py', '''
        def _detach_process_group(): raise AssertionError('no shell detach in CPU fixture')
        def _report_startup_error(queue, error): queue.put(('error', str(error)))
    ''')
    write_module(fake, 'freetoken/gpu_select.py', 'def set_assigned_gpu(value): pass\n')
    write_module(fake, 'freetoken/utils/progress.py', 'def set_progress_sink(value): pass\n')
    write_module(fake, 'freetoken/utils/__init__.py', 'import logging\ndef init_logger(name): return logging.getLogger(name)\n')
    write_module(fake, 'freetoken/kvcache/__init__.py', '')
    write_module(fake, 'freetoken/kvcache/cache_status.py', 'def compute_cache_status_meta(engine): return {}\n')
    write_module(fake, 'freetoken/scheduler.py', '''
        from types import SimpleNamespace
        import json, os
        from pathlib import Path
        class Scalar:
            def item(self): return 0
        class Bank:
            def numel(self): return 4
            def element_size(self): return 4
        class Stats:
            def __init__(self, cache): self.cache = cache
            def sum(self, axis): return [self.cache.active]
        class MoE:
            decode_target = 'offload'
            def __init__(self):
                self.active = self.missing = self.fetched = 0
                self.lru_stats = Stats(self); self.banks = [(0, [Bank()])]
                self.policy_swap_bytes = Scalar()
            def _d0_decode_counts(self): return [self.missing], [self.fetched]
            def _d0_begin_decode(self, batch, *a, **kw): return ('begin', a, kw)
            def _d0_end_decode(self, *a, **kw):
                self.active += 2; self.missing += 1; self.fetched += 1
                return ('end', a, kw)
            def reset_stats(self, *a, **kw): return ('reset', a, kw)
            def apply_profile_adaptation(self, plan, proof, *a, **kw): return None
        class Engine:
            def __init__(self): self.moe_offload_cache = MoE()
        class TP:
            size = 1; rank = 0
            def is_primary(self): return True
        class UserMsg:
            uid = 7; input_ids = [10, 11]
        class DetokenizeMsg:
            uid = 7
            def __init__(self, token, finished):
                self.next_token = token; self.finished = finished
                self.finish_reason = 'stop' if finished else None
        class Scheduler:
            def __init__(self, args): self.engine = Engine(); self.gpus = []
            def sync_all_ranks(self): pass
            def _process_one_msg(self, msg, *a, **kw): return ('process', a, kw)
            def _reply_tokenizer_rank0(self, replies, *a, **kw): return ('reply', a, kw)
            def run_forever(self):
                assert self._process_one_msg(UserMsg(), 'p', keep=1) == ('process', ('p',), {'keep': 1})
                cache = self.engine.moe_offload_cache
                assert cache._d0_begin_decode(SimpleNamespace(reqs=[SimpleNamespace(uid=7)]), 'b', keep=2) == ('begin', ('b',), {'keep': 2})
                assert cache._d0_end_decode('e', keep=3) == ('end', ('e',), {'keep': 3})
                assert self._reply_tokenizer_rank0([DetokenizeMsg(21, False), DetokenizeMsg(22, True)], 'r', keep=4) == ('reply', ('r',), {'keep': 4})
                if os.environ['TEST_SHUTDOWN_MODE'] == 'sigterm':
                    __import__('os').kill(__import__('os').getpid(), __import__('signal').SIGTERM)
                else:
                    raise KeyboardInterrupt
            def shutdown(self):
                Path(os.environ['TEST_SHUTDOWN']).write_text('once')
    ''')
    launch = tmp_path / 'launch.py'
    launch.write_text(textwrap.dedent('''
        import json, multiprocessing as mp, os
        from pathlib import Path
        from types import SimpleNamespace
        import r049_t21_ordinary_d0_startup_v3 as target
        from freetoken.scheduler import MoE, TP
        if __name__ == '__main__':
            assert MoE._d0_begin_decode.__name__ == '_d0_begin_decode'
            ordinary = target.mods()[1]
            parent = ordinary.birth()
            os.environ['R046C_T06_SERVICE_BIRTH'] = json.dumps(parent)
            ctx = mp.get_context('spawn'); queue = ctx.Queue()
            args = SimpleNamespace(shell_mode=False, gpu_assigned=(), gpu=(), tp_info=TP(), silent_output=False)
            child = ctx.Process(target=target.worker_run_scheduler, args=(args, queue))
            child.start(); child.join(20)
            if child.is_alive(): child.terminate(); child.join(); raise AssertionError('spawn did not terminate')
            assert child.exitcode == 0, child.exitcode
            assert MoE._d0_begin_decode.__name__ == '_d0_begin_decode'
            Path(os.environ['TEST_PARENT']).write_text(json.dumps(parent))
    '''))
    env = os.environ.copy()
    env.update(CUDA_VISIBLE_DEVICES='', PYTHONDONTWRITEBYTECODE='1',
               PYTHONPATH=os.pathsep.join([str(fake), str(HERE), env.get('PYTHONPATH', '')]),
               FT_T21_DIAG_JOURNAL=str(tmp_path / 'd0.jsonl'),
               R046C_T06_OBSERVER_DIR=str(tmp_path / 'observer'),
               TEST_SHUTDOWN=str(tmp_path / 'shutdown'), TEST_PARENT=str(tmp_path / 'parent.json'),
               TEST_SHUTDOWN_MODE=shutdown_mode)
    subprocess.run([sys.executable, str(launch)], env=env, timeout=40, check=True)
    rows = [json.loads(row) for row in (tmp_path / 'd0.jsonl').read_text().splitlines()]
    inputs = [json.loads(row) for row in (tmp_path / 'observer/inputs.jsonl').read_text().splitlines()]
    tokens = [json.loads(row) for row in (tmp_path / 'observer/tokens.jsonl').read_text().splitlines()]
    parent = json.loads((tmp_path / 'parent.json').read_text())
    assert [r['kind'] for r in rows] == ['install', 'decode', 'terminal']
    assert rows[-1]['status'] == 'complete' and rows[1]['rids'] == [7]
    assert rows[1]['h2d_bytes'] == 16
    assert len(inputs) == 1 and len(tokens) == 2
    assert inputs[0]['service_birth'] == parent and parent['start_ticks'] > 0
    assert inputs[0]['worker_birth']['pid'] != parent['pid']
    assert inputs[0]['worker_birth']['start_ticks'] > 0
    assert {r['worker_birth']['execution_id'] for r in rows} == {inputs[0]['worker_birth']['execution_id']}
