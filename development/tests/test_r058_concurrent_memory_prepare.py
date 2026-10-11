import threading
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parents[1]))
import r058_concurrent_memory_prepare as prepare
from r058_concurrent_request import RequestSpec, decode_then_third, simultaneous


def spec(name, tokens):
    return RequestSpec(name, tokens, {'model': 'bound', 'messages': []})


def test_simultaneous_releases_both_callers():
    entered = []
    def send(item):
        entered.append(item.name)
        return item.name
    rows = simultaneous(spec('left', 87100), spec('right', 32064), send)
    assert [row['name'] for row in rows] == ['left', 'right']
    assert all(row['error'] is None for row in rows) and sorted(entered) == ['left', 'right']


def test_decode_trigger_waits_for_both_first_deltas_before_64k():
    phases = []
    release = threading.Event()
    def stream(item, first):
        phases.append(item.name + ':decode')
        first()
        assert release.wait(1)
        return item.name
    def send(item):
        phases.append(item.name + ':sent')
        assert phases.count('a:decode') == 1 and phases.count('b:decode') == 1
        release.set()
        return {'dispatch_ns': __import__('time').monotonic_ns(), 'name': item.name}
    rows = decode_then_third(spec('a', 32064), spec('b', 32064), spec('c', 65424), stream, send)
    assert [row['name'] for row in rows] == ['a', 'b', 'c']
    assert rows[-1]['error'] is None and phases[-1] == 'c:sent'


def test_decode_failure_before_token_aborts_without_third_send():
    sent = []
    def stream(_item, _first):
        raise ValueError('no token')
    with pytest.raises(RuntimeError, match='decode barrier'):
        decode_then_third(spec('a', 32064), spec('b', 32064), spec('c', 65424), stream,
                          lambda item: sent.append(item.name), timeout=.2)
    assert sent == []


def test_role_or_empty_sse_delta_does_not_unlock_decode():
    assert prepare._token_delta({'choices': [{'delta': {'role': 'assistant'}}]}) is False
    assert prepare._token_delta({'choices': [{'delta': {'content': ''}}]}) is False
    assert prepare._token_delta({'choices': [{'delta': {'reasoning_content': 'x'}}]}) is True


@pytest.mark.parametrize('lines', [[b'data: {bad}\n'], [b'data: {"choices":[{"delta":{"content":"x"},"finish_reason":"stop"}],"usage":{"prompt_tokens":32064}}\n']])
def test_sse_failure_preserves_incremental_raw_and_events(monkeypatch, tmp_path, lines):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def __iter__(self): return iter(lines)
    monkeypatch.setattr(prepare.urllib.request, 'urlopen', lambda *_a, **_k: Response())
    with pytest.raises(RuntimeError):
        prepare.sse_sender('http://unit', tmp_path, spec('x', 32064))
    assert (tmp_path/'stream.raw').exists() and (tmp_path/'events.jsonl').exists()


def _scenario_plan():
    values = {name: spec(name, tokens) for name, tokens in [('cold87_0',87100),('cold32_0',32064),('cold32_1',32064),('cold32_2',32064),('cold64_0',65424)]}
    return {'requests': values, 'scenarios': (('one','cold87_0','cold32_0'), ('two','cold32_1','cold32_2'), ('three','cold32_0','cold32_1','cold64_0'))}


def test_first_scenario_failure_never_starts_later_services(monkeypatch, tmp_path):
    started = []
    class Proc: pid=7
    class Life:
        def stop_owned_process(self, _): pass
        def owned_group_alive(self, _): return False
    class D:
        def dynamic_fixture_port(self): return 43111
        def load_owned_lifecycle(self): return Life()
    monkeypatch.setattr(prepare, 'prepare_r058_service', lambda _d, directory, _p, start: started.append(directory.name) or Proc())
    monkeypatch.setattr(prepare, 'sse_sender', lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError('first failed')))
    with pytest.raises(RuntimeError, match='simultaneous'):
        prepare.run_scenarios(D(), tmp_path, _scenario_plan())
    assert started == ['one'] and (tmp_path/'one'/'failure.json').exists()


def test_cleanup_failure_marks_error_for_outer_lock_preservation(monkeypatch, tmp_path):
    class Proc: pid=8
    class Life:
        def stop_owned_process(self, _): raise RuntimeError('cleanup failed')
        def owned_group_alive(self, _): return True
    class D:
        def dynamic_fixture_port(self): return 43112
        def load_owned_lifecycle(self): return Life()
    monkeypatch.setattr(prepare, 'prepare_r058_service', lambda *_a, **_k: Proc())
    monkeypatch.setattr(prepare, 'sse_sender', lambda *_a, **_k: {'dispatch_ns': 1, 'usage': {'prompt_tokens': 1}})
    with pytest.raises(RuntimeError) as failure:
        prepare.run_scenarios(D(), tmp_path, _scenario_plan())
    assert getattr(failure.value, 'owned_cleanup_failed', False) is True


def test_production_plan_binds_frozen_r056_tokens(monkeypatch):
    source = [
        ({'name': 'cold87_0', 'prompt_tokens': 87100}, {'seed': True}),
        ({'name': 'cold32_0', 'prompt_tokens': 32064}, {'n': 0}),
        ({'name': 'cold32_1', 'prompt_tokens': 32064}, {'n': 1}),
        ({'name': 'cold32_2', 'prompt_tokens': 32064}, {'n': 2}),
        ({'name': 'cold64_0', 'prompt_tokens': 65424}, {'n': 64}),
    ]
    class Frozen: 
        def payloads(self): return source
    monkeypatch.setattr(prepare, 'load_r056', lambda: Frozen())
    plan = prepare.production_plan()
    assert plan['window'] == 98304 and plan['memory_ratio'] == '0.88'
    assert plan['d0_enabled'] is plan['route_trace_enabled'] is plan['pause_endpoint_enabled'] is False
    assert plan['requests']['cold87_0'].payload == {'seed': True}


def test_production_plan_rejects_shortened_seed(monkeypatch):
    class Frozen:
        def payloads(self):
            return [({'name': name, 'prompt_tokens': tokens}, {}) for name, tokens in (
                ('cold87_0', 87099), ('cold32_0', 32064), ('cold32_1', 32064), ('cold32_2', 32064), ('cold64_0', 65424))]
    monkeypatch.setattr(prepare, 'load_r056', lambda: Frozen())
    with pytest.raises(RuntimeError, match='87K'):
        prepare.production_plan()


def test_observer_environment_has_no_development_switch(tmp_path):
    env = prepare.observer_environment(tmp_path / 'memory.jsonl')
    assert env == {'R058_MODEL_MEMORY': str(tmp_path / 'memory.jsonl'), 'R058_OBSERVE_REQUESTS': '1'}
    assert not any(key.startswith('FT_DEV') for key in env)
