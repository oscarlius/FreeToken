import hashlib
import importlib.util
import json
from pathlib import Path
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('bound_tax', ROOT/'r040a_anchor_four_cell_v1.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
PROBE = ROOT.parent/'scripts/ft_probe_ckpt_tax.py'


class Response:
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def __iter__(self): return iter([b'data: {"choices":[{"delta":{"content":"ok"}}]}\n'])


def test_real_historical_probe_binds_ten_wire_requests_and_preserves_repetitions(tmp_path):
    seed = tmp_path/'seed.txt'
    seed.write_text('实际输入' * 7000, encoding='utf-8')
    seed.chmod(0o444)
    arm = tmp_path/'OFF_p1'
    arm.mkdir()
    actual = []
    def opener(request, *, timeout):
        assert request.full_url == 'http://127.0.0.1:43210/v1/chat/completions'
        assert timeout == 900
        actual.append(request.data)
        return Response()
    result = m.run_bound_probe(probe_path=PROBE, seed_path=seed,
                              seed_sha256=m.sha(seed), arm=arm, checkpoint=False,
                              service_pid=1234, service_start_ticks=456, port=43210, opener=opener, sleep=lambda _: None)
    assert len(actual) == 10 and len(result['requests']) == 10
    assert [x['cell'] for x in result['requests']] == ['cold']*2 + ['warm']*8
    assert [x['shape'] for x in result['requests']] == ['single', 'multi']*5
    for record, wire in zip(result['requests'], actual):
        assert (arm/record['path']).read_bytes() == wire
        assert record['sha256'] == hashlib.sha256(wire).hexdigest()
        payload = json.loads(wire)
        assert payload['max_tokens'] == 4 and payload['temperature'] == 0
        assert len(payload['messages']) == (1 if record['shape'] == 'single' else 13)
    assert result['model_admitted'] is False and result['cache_hit_proved'] is False
    assert json.loads((arm/'tax.json').read_text())['reps'] == 5


def test_rejects_probe_or_seed_tamper_before_request(tmp_path):
    seed = tmp_path/'seed'; seed.write_bytes(b'input'); seed.chmod(0o444)
    arm = tmp_path/'ON_p1'; arm.mkdir()
    probe = tmp_path/'probe.py'; probe.write_bytes(PROBE.read_bytes() + b'\n# changed\n')
    def denied(*_, **__): pytest.fail('invalid input must never connect')
    common = dict(seed_path=seed, arm=arm, checkpoint=True, service_pid=1, service_start_ticks=2,
                  port=43210, opener=denied)
    with pytest.raises(ValueError, match='probe SHA'):
        m.run_bound_probe(probe_path=probe, seed_sha256=m.sha(seed), **common)
    with pytest.raises(ValueError, match='input differs'):
        m.run_bound_probe(probe_path=PROBE, seed_sha256='0'*64, **common)
    assert not (arm/'requests').exists()


def test_bind_only_new_seed_and_reject_startup_sha_difference(tmp_path):
    source = tmp_path/'source'; source.write_bytes('业务输入'.encode())
    destination = tmp_path/'bound'
    with pytest.raises(ValueError, match='SHA differs'):
        m.bind_seed(source, destination, '0'*64)
    assert not destination.exists()
    binding = m.bind_seed(source, destination, m.sha(source))
    assert destination.read_bytes() == source.read_bytes()
    assert binding['sha256'] == m.sha(destination)
    with pytest.raises(ValueError, match='new destination'):
        m.bind_seed(source, destination, m.sha(source))


def test_collect_uses_six_distinct_production_scopes_and_only_anchor_requests(monkeypatch, tmp_path):
    source = tmp_path/'input.txt'; source.write_text('bound input '*4000)
    directory = tmp_path/'E2-R040a'; directory.mkdir()
    owner = SimpleNamespace(options=SimpleNamespace(rid='E2-R040a',gate='T20',run=True),
                            directory=directory,proc=None)
    review = {'candidate_commit':'0aa23431e5b800797543bdecbf35a01045131d7d',
              'anchor_four_cell':{'state':'queued_bound_supplement',
                    'probe_path':str(PROBE),'probe_sha256':m.PROBE_SHA,
                    'input_binding':{'path':str(source),'sha256':m.sha(source)}}}
    scopes=[]
    monkeypatch.setattr(m,'process_birth',lambda pid:(pid,1000+pid))
    @contextmanager
    def service(current,name,*,candidate_commit,probe_path,checkpoint):
        assert current is owner and candidate_commit==review['candidate_commit']
        assert probe_path==PROBE
        arm=directory/name;arm.mkdir()
        scopes.append((name,checkpoint));owner.proc=SimpleNamespace(pid=100+len(scopes))
        try:yield arm,{},tmp_path
        finally:owner.proc=None
    actual=m.run_bound_probe
    monkeypatch.setattr(m,'run_bound_probe',lambda **kw:actual(**kw,
                        opener=lambda *_,**__:Response(),sleep=lambda _:None))
    result=m.collect_anchor_four_cell(owner,review,service_scope=service)
    assert scopes==[(f'{mode}_p{p}',mode=='ON') for p in range(1,4) for mode in ('OFF','ON')]
    assert result['independent_processes']==6
    assert len(result['arms'])==6 and sum(len(x['requests']) for x in result['arms'])==60
    assert result['state']=='measured_pending_independent_raw_review'
    assert not result['model_admitted'] and owner.proc is None
    assert len({(x['service_pid'],x['service_start_ticks']) for x in result['arms']}) == 6


def test_production_scope_rejects_wrong_round_before_command_or_socket(monkeypatch, tmp_path):
    owner=SimpleNamespace(options=SimpleNamespace(rid='E2-R040',gate='T20',run=True),
                          directory=tmp_path,proc=None)
    monkeypatch.setattr(m,'command',lambda _:pytest.fail('must reject before command'))
    with pytest.raises(ValueError,match='actual running batch'):
        with m.production_service(owner,'OFF_p1',candidate_commit='0'*40,probe_path=PROBE):
            pytest.fail('must not enter service scope')
