import ast
import importlib.util
import json
from pathlib import Path
import shlex
from types import SimpleNamespace
import time
import urllib.request

import pytest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('r040_private_test', ROOT / 'r040a_private_port_owner_v1.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Owner:
    def __init__(self, root, gpu):
        self.directory = root
        root.mkdir()
        self.worktree = root / 'worktree'
        self.worktree.mkdir()
        self.gpu = gpu
        self.options = SimpleNamespace(rid='E2-R040a')
        self.proc = None

    def environment(self, *_):
        return {'PATH': 'fixture', 'CUDA_VISIBLE_DEVICES': '0',
                'PYTHONPATH': str(self.worktree / 'python'), 'UNRELATED_SECRET': 'must-not-persist'}

    def compiled_extensions(self, *_):
        return {'native': {'sha256': 'a' * 64}}

    def startup_wrapper(self):
        return self.gpu.HERE / 'startup.py'

    def set_status(self, **_):
        pass


def gpu_fixture(tmp_path):
    tools = tmp_path / 'tools'
    tools.mkdir()
    for name in ('startup.py', 't17_d14_exact_ids.py'):
        p = tools / name
        p.write_text('# frozen CPU fixture\n')
        p.chmod(0o444)

    def command(argv, **_):
        return '4' if argv[0] == 'nvidia-smi' and '--query-gpu=memory.used' in argv else 'CPU_FIXTURE'

    def put(path, value):
        Path(path).write_text(json.dumps(value, sort_keys=True) + '\n')

    return SimpleNamespace(PY='python', ROOT=tmp_path / 'model-root', HERE=tools,
                           shlex=shlex, time=time, helper=SimpleNamespace(CANDIDATE='0aa23431'),
                           protocol={'command': command, 'strict_args': lambda *_: None}, put=put)


def lifecycle_fixture():
    birth = {'pid': 777, 'start_ticks': 12, 'pgid': 777, 'session': 777,
             'execution_id': '777:12', 'state': 'R'}
    state = {'alive': True, 'stopped': []}

    def stop(proc):
        state['stopped'].append(proc.pid)
        state['alive'] = False

    life = SimpleNamespace(process_identity=lambda _: birth if state['alive'] else None,
                           stop_owned_process=stop, owned_group_alive=lambda _: state['alive'])
    return life, birth, state


def make_owner(monkeypatch, tmp_path, *, file_dry_run=False):
    gpu = gpu_fixture(tmp_path)
    monkeypatch.setattr(m, '_private_gate', lambda self, wt, candidate: str(wt / 'python/freetoken/__init__.py'))
    life, birth, state = lifecycle_fixture()
    owner = m.install(Owner(tmp_path / 'round', gpu), gpu_module=gpu, lifecycle=life,
                      file_dry_run=file_dry_run)
    return owner, gpu, life, birth, state


@pytest.mark.parametrize('capacity,host_slots', [(2, 0), (4, 5)])
def test_service_argv_matches_retained_native_writer(monkeypatch, tmp_path, capacity, host_slots):
    owner, gpu, *_ = make_owner(monkeypatch, tmp_path, file_dry_run=True)
    gpu.subprocess = SimpleNamespace(Popen=lambda *_a, **_k: pytest.fail('dry started a service'), STDOUT=-2)
    monkeypatch.setattr(urllib.request, 'urlopen', lambda *_a, **_k: pytest.fail('dry sent a request'))
    owner.service('arm', lambda arm: arm, health_only=True,
                  max_running_requests=capacity, mamba_host_slots=host_slots)
    native = ast.parse((ROOT / 't17_d14_gpu.py').read_text(encoding='utf-8'))
    cls = next(node for node in native.body if isinstance(node, ast.ClassDef) and node.name == 'Run')
    service = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'service')
    assignment = next(node for node in ast.walk(service) if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == 'argv' for target in node.targets))
    expected = eval(compile(ast.Expression(assignment.value), 'native-argv', 'eval'),
                    {'__builtins__': {'str': str}},
                    {'ROOT': gpu.ROOT, 'PY': gpu.PY, 'wrapper': owner.startup_wrapper(),
                     'max_running_requests': capacity, 'mamba_host_slots': host_slots})
    expected[expected.index('--port') + 1] = str(owner.port)
    tokens = shlex.split((owner.directory / 'arm/SERVE_CMD.txt').read_text())
    assert tokens[tokens.index('numactl'):] == expected
    assert '--r040a-file-only' not in tokens and owner.port != 8095
    assert (owner.directory / 'arm/serve.log').is_file()
    assert json.loads((owner.directory / 'arm/owned_process.json').read_text())['not_measurement'] is True
    assert 'UNRELATED_SECRET' not in (owner.directory / 'arm/SERVE_CMD.txt').read_text()


def test_formal_and_dry_share_pre_popen_writes(monkeypatch, tmp_path):
    gpu = gpu_fixture(tmp_path)
    monkeypatch.setattr(m, '_private_gate', lambda self, wt, candidate: str(wt / 'python/freetoken/__init__.py'))
    life, *_ = lifecycle_fixture()
    dry = m.install(Owner(tmp_path / 'dry', gpu), gpu_module=gpu, lifecycle=life, file_dry_run=True)
    formal = m.install(Owner(tmp_path / 'formal', gpu), gpu_module=gpu, lifecycle=life)

    def popen(*_a, **_k):
        raise RuntimeError('Popen sentinel')

    gpu.subprocess = SimpleNamespace(Popen=popen, STDOUT=-2)
    dry.service('arm', lambda arm: arm, max_running_requests=4)
    with pytest.raises(RuntimeError, match='Popen sentinel'):
        formal.service('arm', lambda arm: arm, max_running_requests=4)
    def normalize(text, owner):
        escaped = json.dumps(str(owner.directory))[1:-1]
        return text.replace(escaped, 'ROUND').replace(str(owner.directory), 'ROUND').replace(str(owner.port), 'PORT')
    for name in ('environment.json', 'compiled_extensions.json', 'SERVE_CMD.txt', 'ENV.txt', 'serve.log'):
        a = normalize((dry.directory / 'arm' / name).read_text(), dry)
        b = normalize((formal.directory / 'arm' / name).read_text(), formal)
        assert a == b, name


def test_formal_birth_parser_operation_and_stop(monkeypatch, tmp_path):
    owner, gpu, life, birth, state = make_owner(monkeypatch, tmp_path)
    gpu.subprocess = SimpleNamespace(Popen=lambda *_a, **_k: SimpleNamespace(pid=777), STDOUT=-2)
    owner.ready_health = lambda arm: gpu.put(arm / 'health.json', {'status': 'ok'})
    owner.parser = lambda _: {'_unique_suffix': repr('.pid=777'), 'server_port': str(owner.port), 'mamba_host_slots': '0'}
    result = owner.service('arm', lambda arm: json.loads((arm / 'owned_process.json').read_text()), health_only=True)
    assert result['birth'] == birth and result['port'] == owner.port
    assert state['stopped'] == [777] and owner.proc is None


def test_stop_refuses_reused_birth_and_preserves_lock(monkeypatch, tmp_path):
    owner, _, life, birth, state = make_owner(monkeypatch, tmp_path)
    owner.proc = SimpleNamespace(pid=777)
    owner.service_birth = birth
    life.process_identity = lambda _: {**birth, 'start_ticks': 13}
    with pytest.raises(RuntimeError, match='birth changed') as error:
        owner.stop()
    assert error.value.owned_cleanup_failed and owner.proc.pid == 777
    assert state['stopped'] == []


def test_cleanup_failure_retains_process_for_enclosing_owner(monkeypatch, tmp_path):
    owner, _, life, birth, _ = make_owner(monkeypatch, tmp_path)
    owner.proc = SimpleNamespace(pid=777)
    owner.service_birth = birth
    life.owned_group_alive = lambda _: True
    with pytest.raises(RuntimeError, match='group remains') as error:
        owner.stop()
    assert error.value.owned_cleanup_failed and error.value.owned_process is owner.proc


def test_private_readiness_never_uses_shared_endpoint(monkeypatch, tmp_path):
    import io
    import urllib.error
    owner, gpu, *_ = make_owner(monkeypatch, tmp_path)
    owner.proc = SimpleNamespace(poll=lambda: None)
    arm = owner.directory / 'arm'
    arm.mkdir()
    seen = []

    def answer(request, **_):
        url = request if isinstance(request, str) else request.full_url
        seen.append(url)
        value = {'status': 'ok'} if url.endswith('/health') else {'choices': [{'message': {'content': 'ok'}}]}
        return io.BytesIO(json.dumps(value).encode())

    gpu.urllib = SimpleNamespace(request=SimpleNamespace(urlopen=answer, Request=urllib.request.Request),
                                error=urllib.error)
    owner.ready(arm)
    assert seen == [owner.base_url + '/health', owner.base_url + '/v1/chat/completions']


def test_private_gate_reuses_reviewed_port_free_admission(monkeypatch, tmp_path):
    owner, _, *_ = make_owner(monkeypatch, tmp_path)
    tree = ast.parse((ROOT / 't16_private_port_base_runner.py').read_text(encoding='utf-8'))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Runner')
    gate = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'gate')
    attrs = {node.attr for node in ast.walk(gate) if isinstance(node, ast.Attribute)}
    assert not {'connect', 'connect_ex'} & attrs
    assert {'read_text', 'stat', 'environment'} <= attrs
    assert owner.port != 8095


def test_business_request_uses_owned_url_and_keeps_native_receipt_contract(monkeypatch, tmp_path):
    owner, gpu, *_ = make_owner(monkeypatch, tmp_path)
    arm = owner.directory / 'arm'
    (arm / 'inputs').mkdir(parents=True)
    seen = []
    gpu.ids_sha = lambda ids: 'a' * 64
    response = {'uid': 0}
    gpu.validate_response = lambda record, ids, cached, max_tokens: response
    gpu.helper.exact_id_request = lambda url, *_a, **_k: seen.append(url) or {'response': response}
    receipt = {'uid': 0, 'numel': 2, 'int32le_sha256': 'a' * 64,
               'sampling': {'temperature': 0, 'max_tokens': 128, 'ignore_eos': True}}
    (arm / 'inputs/0.json').write_text(json.dumps(receipt))
    assert owner.request(arm, 'query', [3, 4], 0, 128) is response
    assert seen == [owner.base_url]
    receipt['sampling']['ignore_eos'] = False
    (arm / 'inputs/0.json').write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='input receipt'):
        owner.request(arm, 'query', [3, 4], 0, 128)


def test_file_dry_business_request_fails_before_client(monkeypatch, tmp_path):
    owner, gpu, *_ = make_owner(monkeypatch, tmp_path, file_dry_run=True)
    gpu.helper.exact_id_request = lambda *_a, **_k: pytest.fail('dry sent a request')
    with pytest.raises(RuntimeError, match='cannot send'):
        owner.request(owner.directory, 'query', [3, 4], 0, 128)
