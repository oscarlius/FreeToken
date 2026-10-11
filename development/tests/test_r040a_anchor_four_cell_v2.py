import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import socket
from types import SimpleNamespace
import urllib.request

import pytest

HERE = Path(__file__).parents[1]
PROBE = HERE.parent / 'scripts/ft_probe_ckpt_tax.py'
CANDIDATE = '0aa23431e5b800797543bdecbf35a01045131d7d'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


m = load('anchor_v2_test', HERE / 'r040a_anchor_four_cell_v2.py')
v1 = load('anchor_v1_retained_test', HERE / 'r040a_anchor_four_cell_v1.py')


class Response:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def __iter__(self):
        return iter([b'data: {"choices":[{"delta":{"content":"ok"}}]}\n'])


def denied(*_args, **_kwargs):
    pytest.fail('CPU preparation crossed a process/network boundary')


def owner_fixture(monkeypatch, tmp_path, *, dry):
    rounds = tmp_path / 'ft_rounds'
    rounds.mkdir()
    monkeypatch.setattr(m, 'ROUNDS', rounds)
    monkeypatch.setattr(m, 'LOCK', tmp_path / 'gpu.lock')
    directory = rounds / ('.dryrun_R040a_fixture' if dry else 'E2-R040a')
    directory.mkdir()
    with socket.socket() as guard:
        guard.bind(('127.0.0.1', 0))
        port = guard.getsockname()[1]
    assert port != 8095
    controller = {'pid': os.getpid(), 'start_ticks': 73,
                  'execution_id': f'{os.getpid()}:73'}
    state = {'services': {}, 'stops': [], 'status': [], 'commands': []}

    def command(argv):
        state['commands'].append(argv)
        if argv[0] == 'nvidia-smi':
            return '4'
        if argv[0] == 'git' and argv[-3:] == ['describe', '--tags', '--exact-match']:
            return 'E2-base.1@0aa23431'
        pytest.fail('unexpected pre-Popen command: ' + repr(argv))

    monkeypatch.setattr(m, 'command', command)

    def process_identity(pid):
        return controller if pid == os.getpid() else state['services'].get(pid)

    lifecycle = SimpleNamespace(process_identity=process_identity,
                                owned_group_alive=lambda pid: pid in state['services'])
    owner = SimpleNamespace(options=SimpleNamespace(rid='E2-R040a', gate='T20', run=True, batch=71),
                            directory=directory, proc=None, port=port, token=None, lock_inode=None,
                            _r040a_file_dry_run=dry, _r040a_private_lifecycle=lifecycle)
    owner.gate = lambda wt, candidate: str(wt / 'python/freetoken/__init__.py')
    owner.compiled_extensions = lambda wt: {'native': {'path': '/fixture/native.so', 'sha256': 'a' * 64}}
    owner.environment = lambda *_: {
        'PYTHONPATH': '/fixture/python', 'PYTHONUNBUFFERED': '1', 'VIRTUAL_ENV': '/fixture/venv',
        'PATH': '/fixture/bin', 'LD_LIBRARY_PATH': '/fixture/lib', 'CUDA_VISIBLE_DEVICES': '2',
        'FT_DEV_D0': '1', 'FT_T17_OBSERVATIONS': 'must-be-removed',
        'UNRELATED_SECRET': 'must-not-persist'}
    owner.ready = denied
    owner.parser = denied
    owner.set_status = lambda **kw: state['status'].append(kw)

    def stop():
        state['stops'].append(owner.proc.pid)
        state['services'].pop(owner.proc.pid, None)
        owner.proc = None

    owner.stop = stop
    if not dry:
        token = {'owner': 'E2-R040a', 'batch': 71, **controller}
        owner.token = json.dumps(token, sort_keys=True)
        m.LOCK.write_text(owner.token, encoding='utf-8')
        owner.lock_inode = m.LOCK.stat().st_ino
        owner.lock_device = m.LOCK.stat().st_dev
    return owner, state


def review_fixture(tmp_path):
    seed = tmp_path / 'business_seed.txt'
    seed.write_bytes(('真实业务输入 ' * 5000).encode())
    seed.chmod(0o444)
    return {'candidate_commit': CANDIDATE,
            'sources': {str(Path(m.__file__).resolve()): m.sha(m.__file__), str(PROBE): m.PROBE_SHA},
            'anchor_four_cell': {'state': 'queued_bound_supplement',
                'probe_path': str(PROBE), 'probe_sha256': m.PROBE_SHA,
                'input_binding': {'path': str(seed), 'sha256': m.sha(seed)}}}


def test_actual_collector_file_branch_writes_six_services_and_sixty_requests(monkeypatch, tmp_path):
    owner, state = owner_fixture(monkeypatch, tmp_path, dry=True)
    review = review_fixture(tmp_path)
    owner.directory.chmod(0o555)
    monkeypatch.setattr(m.subprocess, 'Popen', denied)
    monkeypatch.setattr(urllib.request, 'urlopen', denied)
    result = m.collect_anchor_four_cell(owner, review)
    assert result['kind'] == 'CPU_FILE_PROBE' and result['not_measurement'] is True
    assert result['state'] == 'cpu_file_probe_completed' and result['planned_services'] == 6
    assert [arm['arm'] for arm in result['arms']] == [f'{mode}_p{p}' for p in range(1, 4) for mode in ('OFF', 'ON')]
    assert owner.proc is None and not state['stops'] and not state['status']
    assert [argv[0] for argv in state['commands']] == ['git', 'nvidia-smi'] * 6
    assert not m.LOCK.exists() and not (m.ROUNDS / 'E2-R040a').exists()
    assert owner.directory.stat().st_mode & 0o200
    bound = owner.directory / 'anchor_seed.txt'
    assert bound.read_bytes() == Path(review['anchor_four_cell']['input_binding']['path']).read_bytes()
    assert not bound.stat().st_mode & 0o222
    required = ('source.json', 'compiled_extensions.json', 'ENV.txt', 'SERVE_CMD.txt',
                'environment.json', 'serve.log', 'args_preprobe_checked.json', 'affinity.json',
                'owned_process.json', 'tax.json', 'request_binding.json')
    for arm in result['arms']:
        directory = owner.directory / arm['arm']
        assert all((directory / name).is_file() for name in required)
        assert directory.stat().st_mode & 0o200 and (directory / 'requests').stat().st_mode & 0o200
        assert len(list((directory / 'requests').glob('*.json'))) == 10
        assert not any(key in arm for key in ('service_pid', 'service_start_ticks', 'independent_processes'))
        assert all('ttft_s' not in request for request in arm['requests'])
        assert json.loads((directory / 'tax.json').read_text())['kind'] == 'CPU_FILE_PROBE'
        assert json.loads((directory / 'args_preprobe_checked.json').read_text())['not_measurement'] is True
        assert json.loads((directory / 'owned_process.json').read_text())['service_started'] is False
        for name in ('ENV.txt', 'SERVE_CMD.txt', 'environment.json'):
            text = (directory / name).read_text()
            assert 'UNRELATED_SECRET' not in text and 'must-not-persist' not in text and 'FT_DEV_' not in text
        env = json.loads((directory / 'environment.json').read_text())
        assert set(env) == set(m.SAFE_ENV) and env['CUDA_VISIBLE_DEVICES'] == '0'


@pytest.mark.parametrize('checkpoint', [False, True])
def test_production_argv_retains_v1_ast_except_private_host_and_port(monkeypatch, tmp_path, checkpoint):
    owner, _ = owner_fixture(monkeypatch, tmp_path, dry=True)
    monkeypatch.setattr(m.subprocess, 'Popen', denied)
    monkeypatch.setattr(urllib.request, 'urlopen', denied)
    with m.production_service(owner, 'arm', candidate_commit=CANDIDATE, probe_path=PROBE,
                              checkpoint=checkpoint) as (arm, env, _):
        assert not any(key.startswith(('FT_T17_', 'FT_D16_', 'FT_DEV_', 'FT_D3_', 'FT_D0_')) for key in env)
    tree = ast.parse(Path(v1.__file__).read_text(encoding='utf-8'))
    service = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'production_service')
    argv = next(node.value for node in ast.walk(service) if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == 'argv' for target in node.targets))
    expected = eval(compile(ast.Expression(argv), 'v1-production-argv', 'eval'),
                    {'__builtins__': {'str': str}}, {'ROOT': m.ROOT, 'FT': m.FT, 'MODEL': m.MODEL})
    expected[expected.index('--host') + 1] = '127.0.0.1'
    expected[expected.index('--port') + 1] = str(owner.port)
    if checkpoint:
        expected.append('--enable-special-token-ckpt')
    actual = shlex.split((arm / 'SERVE_CMD.txt').read_text())
    assert actual[actual.index('taskset'):] == expected


def test_file_payloads_equal_retained_probe_wire_bytes(monkeypatch, tmp_path):
    seed = tmp_path / 'seed.txt'
    seed.write_bytes(('真实输入 ' * 7000).encode())
    seed.chmod(0o444)
    formal, dry = tmp_path / 'OFF_formal', tmp_path / 'OFF_dry'
    formal.mkdir()
    dry.mkdir()
    actual = []

    def opener(request, *, timeout):
        assert timeout == 900 and request.full_url == 'http://127.0.0.1:43210/v1/chat/completions'
        actual.append(request.data)
        return Response()

    result = v1.run_bound_probe(probe_path=PROBE, seed_path=seed, seed_sha256=m.sha(seed), arm=formal,
                               checkpoint=False, service_pid=123, service_start_ticks=456,
                               port=43210, opener=opener, sleep=lambda _: None)
    monkeypatch.setattr(urllib.request, 'urlopen', denied)
    dry_result = m.run_bound_probe(probe_path=PROBE, seed_path=seed, seed_sha256=m.sha(seed), arm=dry,
                                  checkpoint=False, port=43210, file_dry_run=True)
    assert len(actual) == 10 and [x['sha256'] for x in result['requests']] == [x['sha256'] for x in dry_result['requests']]
    for wire, request in zip(actual, dry_result['requests']):
        assert (dry / request['path']).read_bytes() == wire
        payload = json.loads(wire)
        assert payload['max_tokens'] == 4 and payload['temperature'] == 0
        assert len(payload['messages']) == (1 if request['shape'] == 'single' else 13)
    assert [request['cell'] for request in dry_result['requests']] == ['cold'] * 2 + ['warm'] * 8
    assert json.loads((formal / 'tax.json').read_text())['reps'] == 5
    assert 'single_median' not in json.loads((dry / 'tax.json').read_text())


@pytest.mark.parametrize('bad_port', [8095, 0, 1023, 65536, True, '43210'])
def test_forbidden_or_nonprivate_port_rejected_before_any_request(tmp_path, bad_port):
    with pytest.raises(ValueError, match='private port'):
        m.run_bound_probe(probe_path=PROBE, seed_path=tmp_path / 'absent', seed_sha256='0' * 64,
                          arm=tmp_path, checkpoint=False, port=bad_port, file_dry_run=True, opener=denied)
    assert not (tmp_path / 'requests').exists()


@pytest.mark.parametrize('change', ['owner', 'batch', 'pid', 'start_ticks', 'execution_id', 'legacy_card_only', 'inode', 'device', 'token'])
def test_current_d07_lock_rejects_each_foreign_identity_before_gate(monkeypatch, tmp_path, change):
    owner, _ = owner_fixture(monkeypatch, tmp_path, dry=False)
    token = json.loads(owner.token)
    if change == 'legacy_card_only':
        token = {'owner': 'E2-R040a', 'card': 'T20', 'pid': os.getpid()}
    elif change in token:
        token[change] = 'foreign' if change in ('owner', 'execution_id') else token[change] + 1
    elif change == 'inode':
        owner.lock_inode += 1
    elif change == 'device':
        owner.lock_device += 1
    elif change == 'token':
        m.LOCK.write_text('replacement', encoding='utf-8')
    if change in token or change == 'legacy_card_only':
        owner.token = json.dumps(token)
        m.LOCK.write_text(owner.token, encoding='utf-8')
    owner.gate = denied
    monkeypatch.setattr(m.subprocess, 'Popen', denied)
    monkeypatch.setattr(urllib.request, 'urlopen', denied)
    with pytest.raises(RuntimeError, match='lock'):
        with m.production_service(owner, 'arm', candidate_commit=CANDIDATE, probe_path=PROBE):
            pytest.fail('foreign lock entered formal scope')
    assert not (owner.directory / 'arm').exists()


@pytest.mark.parametrize('change', ['formal_directory', 'not_sibling', 'wrong_prefix', 'token', 'inode', 'port', 'mode'])
def test_dry_scope_rejects_formal_or_locked_outputs(monkeypatch, tmp_path, change):
    owner, _ = owner_fixture(monkeypatch, tmp_path, dry=True)
    if change == 'formal_directory':
        owner.directory = m.ROUNDS / 'E2-R040a'
    elif change == 'not_sibling':
        owner.directory = tmp_path / '.dryrun_R040a_other'
    elif change == 'wrong_prefix':
        owner.directory = m.ROUNDS / 'dryrun_R040a_other'
    elif change == 'token':
        owner.token = 'foreign'
    elif change == 'inode':
        owner.lock_inode = 1
    elif change == 'port':
        owner.port = 8095
    monkeypatch.setattr(m.subprocess, 'Popen', denied)
    monkeypatch.setattr(urllib.request, 'urlopen', denied)
    with pytest.raises(ValueError):
        with m.production_service(owner, 'arm', candidate_commit=CANDIDATE, probe_path=PROBE,
                                  file_dry_run=False if change == 'mode' else None):
            pytest.fail('invalid dry scope entered')


def test_dry_foreign_lock_rejected_before_files_or_precheck(monkeypatch, tmp_path):
    owner, state = owner_fixture(monkeypatch, tmp_path, dry=True)
    review = review_fixture(tmp_path)
    m.LOCK.write_text('foreign owner')
    owner.gate = denied
    monkeypatch.setattr(m.subprocess, 'Popen', denied)
    monkeypatch.setattr(urllib.request, 'urlopen', denied)
    with pytest.raises(RuntimeError, match='foreign GPU lock'):
        m.collect_anchor_four_cell(owner, review)
    assert not state['commands'] and list(owner.directory.iterdir()) == []


@pytest.mark.parametrize('key', ['probe', 'collector', 'seed'])
def test_source_review_and_actual_seed_sha_checked_before_service(monkeypatch, tmp_path, key):
    owner, _ = owner_fixture(monkeypatch, tmp_path, dry=True)
    review = review_fixture(tmp_path)
    if key == 'seed':
        review['anchor_four_cell']['input_binding']['sha256'] = '0' * 64
    else:
        path = str(PROBE) if key == 'probe' else str(Path(m.__file__).resolve())
        review['sources'][path] = '0' * 64
    monkeypatch.setattr(m.subprocess, 'Popen', denied)
    monkeypatch.setattr(urllib.request, 'urlopen', denied)
    with pytest.raises(ValueError, match='SHA|source review'):
        m.collect_anchor_four_cell(owner, review)
    assert not list(owner.directory.glob('OFF_*'))


def formal_service_fixture(monkeypatch, tmp_path):
    owner, state = owner_fixture(monkeypatch, tmp_path, dry=False)
    monkeypatch.setattr(m, 'command', lambda argv: '4' if argv[0] == 'nvidia-smi' else 'E2-base.1@0aa23431')
    monkeypatch.setattr(m.os, 'sched_getaffinity', lambda _: {1, *range(3, 48)}, raising=False)

    def popen(argv, **kw):
        assert kw['start_new_session'] is True
        pid = 10000 + len(state['stops'])
        state['services'][pid] = {'pid': pid, 'start_ticks': 100 + pid,
            'execution_id': f'{pid}:{100 + pid}', 'pgid': pid, 'session': pid, 'state': 'R'}
        return SimpleNamespace(pid=pid, poll=lambda: None)

    monkeypatch.setattr(m.subprocess, 'Popen', popen)

    def ready(arm):
        assert owner.service_birth == state['services'][owner.proc.pid]
        assert json.loads((arm / 'owned_process.json').read_text())['birth'] == owner.service_birth
        state['services'][owner.proc.pid] = {**owner.service_birth, 'state': 'S'}

    owner.ready = ready
    owner.parser = lambda _: {'prefill_layer_major': 'True', 'max_extend_tokens': '4096',
        'special_token_ckpt': 'False', 'max_seq_len_override': '73728', 'kv_reserve_tokens': '73728',
        'max_running_req': '2', 'cuda_graph_max_bs': '2', 'memory_ratio': '0.88', 'moe_cache_auto': 'True',
        'moe_prefill_hit_d2d': 'True', 'moe_strategy': repr('offload'), 'ple_backend': repr('pinned'),
        'quant_backend': repr('moe.nvfp4=triton'), 'server_port': str(owner.port),
        '_unique_suffix': repr('.pid=' + str(owner.proc.pid))}
    return owner, state


def test_formal_records_birth_before_readiness_and_stops_exact_group(monkeypatch, tmp_path):
    owner, state = formal_service_fixture(monkeypatch, tmp_path)
    monkeypatch.setattr(urllib.request, 'urlopen', denied)
    with m.production_service(owner, 'OFF_p1', candidate_commit=CANDIDATE, probe_path=PROBE, checkpoint=False):
        assert owner.proc.pid == 10000
    assert owner.proc is None and state['stops'] == [10000]
    assert m.LOCK.read_text() == owner.token


def test_formal_collector_keeps_six_processes_and_uses_owner_endpoint(monkeypatch, tmp_path):
    owner, state = formal_service_fixture(monkeypatch, tmp_path)
    review = review_fixture(tmp_path)
    parser = owner.parser
    owner.parser = lambda path: {**parser(path), 'special_token_ckpt': str(Path(path).parent.name.startswith('ON'))}
    wire = []

    def opener(request, *, timeout):
        assert request.full_url == f'http://127.0.0.1:{owner.port}/v1/chat/completions'
        assert timeout == 900
        wire.append(request.data)
        return Response()

    original = m.run_bound_probe
    monkeypatch.setattr(m, 'run_bound_probe', lambda **kw: original(**kw, opener=opener, sleep=lambda _: None))
    monkeypatch.setattr(urllib.request, 'urlopen', denied)
    result = m.collect_anchor_four_cell(owner, review)
    assert result['independent_processes'] == 6 and len(wire) == 60
    assert state['stops'] == list(range(10000, 10006)) and owner.proc is None
    assert len({(arm['service_pid'], arm['service_start_ticks']) for arm in result['arms']}) == 6
    assert result['state'] == 'measured_pending_independent_raw_review'
    assert 'kind' not in result and result['model_admitted'] is False
    assert all(arm['port'] == owner.port for arm in result['arms'])
    assert all(json.loads((owner.directory / arm['arm'] / 'tax.json').read_text())['reps'] == 5 for arm in result['arms'])


@pytest.mark.parametrize('query,answer', [('git', 'wrong-tag'), ('nvidia-smi', '101'), ('nvidia-smi', '')])
def test_dry_retains_actual_tag_and_gpu_read_only_precheck(monkeypatch, tmp_path, query, answer):
    owner, _ = owner_fixture(monkeypatch, tmp_path, dry=True)
    original = m.command
    monkeypatch.setattr(m, 'command', lambda argv: answer if argv[0] == query else original(argv))
    monkeypatch.setattr(m.subprocess, 'Popen', denied)
    monkeypatch.setattr(urllib.request, 'urlopen', denied)
    with pytest.raises((RuntimeError, ValueError), match='tag|GPUs'):
        with m.production_service(owner, 'arm', candidate_commit=CANDIDATE, probe_path=PROBE):
            pytest.fail('dry bypassed actual precheck')
    assert not (owner.directory / 'arm').exists()


@pytest.mark.parametrize('key,value', [('server_port', '8095'), ('special_token_ckpt', 'True'),
                                     ('memory_ratio', '0.86'), ('kv_reserve_tokens', '49152')])
def test_formal_argument_mismatch_rejects_and_cleans_owned_process(monkeypatch, tmp_path, key, value):
    owner, state = formal_service_fixture(monkeypatch, tmp_path)
    original = owner.parser
    owner.parser = lambda path: {**original(path), key: value}
    with pytest.raises(ValueError, match=key):
        with m.production_service(owner, 'OFF_p1', candidate_commit=CANDIDATE, probe_path=PROBE, checkpoint=False):
            pytest.fail('changed production configuration entered probe scope')
    assert owner.proc is None and state['stops'] == [10000]


def test_pid_reuse_refuses_cleanup_and_marks_lock_preservation(monkeypatch, tmp_path):
    owner, state = formal_service_fixture(monkeypatch, tmp_path)
    with pytest.raises(RuntimeError, match='birth changed') as failure:
        with m.production_service(owner, 'OFF_p1', candidate_commit=CANDIDATE, probe_path=PROBE, checkpoint=False):
            state['services'][owner.proc.pid] = {**owner.service_birth, 'start_ticks': 999999}
    assert failure.value.owned_cleanup_failed and failure.value.owned_process is owner.proc
    assert not state['stops'] and m.LOCK.read_text() == owner.token


def test_readiness_failure_stops_only_recorded_owned_service(monkeypatch, tmp_path):
    owner, state = formal_service_fixture(monkeypatch, tmp_path)

    def failed_ready(arm):
        assert owner.service_birth['pid'] == owner.proc.pid
        raise RuntimeError('readiness fixture failed')

    owner.ready = failed_ready
    with pytest.raises(RuntimeError, match='readiness fixture failed'):
        with m.production_service(owner, 'OFF_p1', candidate_commit=CANDIDATE, probe_path=PROBE, checkpoint=False):
            pytest.fail('failed readiness yielded')
    assert owner.proc is None and state['stops'] == [10000]


def test_unrecordable_birth_marks_cleanup_uncertain_without_signalling(monkeypatch, tmp_path):
    owner, state = formal_service_fixture(monkeypatch, tmp_path)
    original = owner._r040a_private_lifecycle.process_identity
    owner._r040a_private_lifecycle.process_identity = lambda pid: original(pid) if pid == os.getpid() else None
    with pytest.raises(RuntimeError, match='birth unknown') as failure:
        with m.production_service(owner, 'OFF_p1', candidate_commit=CANDIDATE, probe_path=PROBE, checkpoint=False):
            pytest.fail('unrecorded birth yielded')
    assert failure.value.owned_cleanup_failed and owner.proc.pid == 10000
    assert not state['stops'] and m.LOCK.read_text() == owner.token


def test_residual_group_after_stop_marks_lock_preservation(monkeypatch, tmp_path):
    owner, state = formal_service_fixture(monkeypatch, tmp_path)
    owner._r040a_private_lifecycle.owned_group_alive = lambda _: True
    with pytest.raises(RuntimeError, match='group remains') as failure:
        with m.production_service(owner, 'OFF_p1', candidate_commit=CANDIDATE, probe_path=PROBE, checkpoint=False):
            pass
    assert failure.value.owned_cleanup_failed and state['stops'] == [10000]
    assert m.LOCK.read_text() == owner.token
