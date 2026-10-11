import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location('r052_replay_tested', Path(__file__).parents[1] / 'r052_t11_replay.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Client:
    def __init__(self):
        self.payloads = []

    def messages_digest(self, messages):
        return hashlib.sha256(json.dumps(messages, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]

    def tool_specs(self):
        return [{'type': 'function', 'function': {'name': 'read_file'}}]

    def build_payload(self, messages, model, tools, thinking, max_tokens):
        return {'messages': messages, 'tools': tools, 'thinking': thinking, 'max_tokens': max_tokens}

    def post_events(self, url, payload, timeout):
        assert url.startswith('http://127.0.0.1:45678/')
        self.payloads.append(payload)
        yield {'id': 'chatcmpl-7', 'choices': [{'finish_reason': 'stop'}], 'usage': {
            'prompt_tokens': 13432, 'completion_tokens': 200,
            'prompt_tokens_details': {'cached_tokens': 13376}}}

    def consume_stream(self, events, _):
        event = list(events)[-1]
        return {'finish_reason': 'stop', 'usage': event['usage'], 'content_text': 'actual answer',
                'reasoning_text': 'actual reasoning', 'tool_calls': []}

    def assistant_message(self, response):
        return {'role': 'assistant', 'content': response['content_text']}


def test_replay_exactly_eight_original_snapshots_then_followup(monkeypatch, tmp_path):
    client = Client()
    rows = [{'messages': [{'role': 'user', 'content': str(i)}]} for i in range(12)]
    monkeypatch.setattr(m, 'TARGET_MESSAGES_SHA', client.messages_digest(rows[7]['messages']))
    trace = {'rounds': rows, 'tools': client.tool_specs(), 'meta': {'params': {'thinking': False}}}
    target = m.replay_to_target(45678, tmp_path, trace, client)
    assert len(client.payloads) == 8 and all(p['max_tokens'] == 200 for p in client.payloads)
    assert [p['messages'] for p in client.payloads] == [r['messages'] for r in rows[:8]]
    assert all(p['tools'] == trace['tools'] and p['thinking'] is False for p in client.payloads)
    assert target['trace_index'] == 7 and target['history_uid'] == 8 and target['uid'] == 7
    assert target['prompt_tokens'] == 13432 and target['completion_tokens'] == 200
    assert target['assistant_message']['reasoning_content'] == 'actual reasoning'
    messages = [*target['messages'], target['assistant_message'], {'role': 'user', 'content': '请继续。'}]
    follow = m.followup(client, 45678, messages, target)
    assert len(client.payloads) == 9 and client.payloads[-1]['max_tokens'] == 64
    assert client.payloads[-1]['tools'] == trace['tools'] and client.payloads[-1]['thinking'] is False
    assert follow['cached_tokens'] == 13376 and (tmp_path / 'replay_07.json').is_file()


def test_wrong_target_identity_rejected_before_target_request(monkeypatch, tmp_path):
    client = Client()
    monkeypatch.setattr(m, 'TARGET_MESSAGES_SHA', 'wrong')
    rows = [{'messages': [{'role': 'user', 'content': str(i)}]} for i in range(8)]
    with pytest.raises(RuntimeError, match='target message identity'):
        m.replay_to_target(45678, tmp_path, {'rounds': rows}, client)
    assert len(client.payloads) == 7


def test_missing_api_cache_detail_is_preserved_as_none():
    assert m.strict_usage({'prompt_tokens': 100, 'completion_tokens': 10}) == (100, 10, None)


@pytest.mark.parametrize('details', [[], {'cached_tokens': True}, {'cached_tokens': -1}])
def test_invalid_nested_cache_is_rejected(details):
    with pytest.raises(ValueError):
        m.strict_usage({'prompt_tokens': 100, 'completion_tokens': 10, 'prompt_tokens_details': details})


def test_trace_copy_only_after_registered_input_matches(monkeypatch, tmp_path):
    source = tmp_path / 'source.json'
    raw = json.dumps({'rounds': [{'messages': []}] * 8}).encode()
    source.write_bytes(raw)
    monkeypatch.setattr(m, 'TRACE_SHA', hashlib.sha256(raw).hexdigest())
    out = tmp_path / 'out'; out.mkdir()
    assert len(m.bind_trace(out, source)['rounds']) == 8
    assert (out / 'trace_input.json').read_bytes() == raw
    source.write_bytes(raw + b' ')
    other = tmp_path / 'other'; other.mkdir()
    with pytest.raises(RuntimeError, match='retained R011 input'):
        m.bind_trace(other, source)
    assert not (other / 'trace_input.json').exists()


def test_d0_count_zero_is_recorded_and_mismatch_rejected(tmp_path):
    (tmp_path / 'worker_shutdown.json').write_text(json.dumps({'schema':'ft_r052_worker_shutdown/v1','status':'complete','scheduler_run_started':True,'pid':9}))
    (tmp_path / 'd0_decode.json').write_text('{"anchor_snapshots_taken": 0}')
    (tmp_path / 'serve.log').write_text('D0 anchor_snapshots_taken=0\n')
    (tmp_path / 'd0_prefill.jsonl').write_text('{"chunk":0,"seg_reason":"other","reqs":[{"rid":7,"new_tokens":1,"cached_tokens":0}]}\n')
    (tmp_path / 'd0_decode_steps.jsonl').write_text('{"actual": true}\n')
    assert m.d0_evidence(tmp_path)['anchor_snapshots_taken'] == 0
    (tmp_path / 'serve.log').write_text('D0 anchor_snapshots_taken=1\n')
    with pytest.raises(RuntimeError, match='disagree'):
        m.d0_evidence(tmp_path)


def test_sse_id_binds_uid_without_ft_dev():
    assert m.stream_uid([{'id': 'chatcmpl-42'}]) == {'uid': 42, 'sse_id': 'chatcmpl-42', 'ft_dev_uid': None}


def test_different_sse_ids_and_ft_dev_mismatch_are_rejected():
    with pytest.raises(RuntimeError, match='different SSE ids'):
        m.stream_uid([{'id': 'chatcmpl-7'}, {'id': 'chatcmpl-8'}])
    with pytest.raises(RuntimeError, match='differ'):
        m.stream_uid([{'id': 'chatcmpl-7', 'ft_dev': {'uid': 8}}])


def test_d0_first_request_is_admission_across_real_token_budget_and_continuation_shapes(tmp_path):
    (tmp_path / 'worker_shutdown.json').write_text(json.dumps({'schema':'ft_r052_worker_shutdown/v1','status':'complete','scheduler_run_started':True,'pid':9}))
    (tmp_path / 'd0_decode.json').write_text('{"anchor_snapshots_taken": 0}')
    (tmp_path / 'serve.log').write_text('D0 anchor_snapshots_taken=0\n')
    (tmp_path / 'd0_decode_steps.jsonl').write_text('{"actual": true}\n')
    (tmp_path / 'd0_prefill.jsonl').write_text('\n'.join([
        '{"chunk":0,"seg_reason":"token_budget","reqs":[{"rid":8,"new_tokens":100,"cached_tokens":10}]}',
        '{"chunk":1,"seg_reason":"token_budget","reqs":[{"rid":8,"new_tokens":20,"cached_tokens":0}]}',
        '{"chunk":2,"seg_reason":"continuation","reqs":[{"rid":8,"new_tokens":4,"cached_tokens":0}]}',
        '{"chunk":3,"seg_reason":"anchor_cap","reqs":[{"rid":9,"new_tokens":50,"cached_tokens":0}]}',
    ]) + '\n')
    d0 = m.d0_evidence(tmp_path)
    target = {'uid': 8, 'prompt_tokens': 134, 'cached_tokens': None}
    follow = {'uid': 9, 'prompt_tokens': 50, 'cached_tokens': None}
    assert m.confirm_cache_evidence(target, follow, d0) == {'target_cached_tokens': 10, 'followup_cached_tokens': 0}
    assert target['d0_admission_cached_tokens'] == 10 and follow['d0_admission_cached_tokens'] == 0


def test_d0_missing_wrong_or_ambiguous_admission_and_api_mismatch_are_rejected():
    target = {'uid': 8, 'prompt_tokens': 2, 'cached_tokens': None}
    follow = {'uid': 9, 'prompt_tokens': 2, 'cached_tokens': 5}
    first = {'chunk': 0, 'new_tokens': 1, 'cached_tokens': 1}
    second = {'chunk': 1, 'new_tokens': 2, 'cached_tokens': 0}
    with pytest.raises(RuntimeError, match='missing'):
        m.confirm_cache_evidence(target, follow, {'prefill_requests': {8: [first]}})
    with pytest.raises(RuntimeError, match='continuation cache'):
        m.confirm_cache_evidence(target, follow, {'prefill_requests': {8: [first], 9: [second, {'chunk': 2, 'new_tokens': 0, 'cached_tokens': 1}]}})
    with pytest.raises(RuntimeError, match='API and D0'):
        m.confirm_cache_evidence(target, follow, {'prefill_requests': {8: [first], 9: [second]}})
    with pytest.raises(RuntimeError, match='share an SSE UID'):
        m.confirm_cache_evidence(target, {**follow, 'uid': 8}, {'prefill_requests': {8: [first]}})
    with pytest.raises(RuntimeError, match='prompt accounting'):
        m.confirm_cache_evidence(target, {**follow, 'cached_tokens': None, 'prompt_tokens': 3}, {'prefill_requests': {8: [first], 9: [second]}})


def test_service_uses_r011_host_restore_flags_and_d0(monkeypatch, tmp_path):
    proc = SimpleNamespace(pid=9, poll=lambda: None)
    seen = {}
    def popen(argv, **kwargs):
        seen.update(argv=argv, env=kwargs['env'])
        kwargs['stdout'].write('Parsed arguments\nServerArgs(server_port=45678)\n')
        kwargs['stdout'].flush()
        return proc
    lifecycle = SimpleNamespace(process_identity=lambda _: {'pgid': 9, 'session': 9},
                                stop_owned_process=lambda _: pytest.fail('ready service must remain owned'))
    gate = SimpleNamespace(
        VENV=Path('venv'),
        clean_environment=lambda _: {'PYTHONPATH':'candidate/python','VIRTUAL_ENV':'venv','CUDA_VISIBLE_DEVICES':'0'},
        serve_argv=lambda port: ['ft', 'serve', '--port', str(port), '--prefill-layer-major',
                                '--mamba-host-slots', '0', '--kv-reserve-tokens', '49152',
                                '--max-seq-len-override', '49152'],
        load_owned_lifecycle=lambda: lifecycle,
        write_new=lambda path, value: path.write_text(json.dumps(value)))
    class Health:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return b'{"status": "ok"}'
    monkeypatch.setattr(m.subprocess, 'Popen', popen)
    monkeypatch.setattr(m.urllib.request, 'urlopen', lambda *a, **k: Health())
    assert m.start_service(gate, tmp_path, tmp_path, 45678) is proc
    assert '--prefill-layer-major' not in seen['argv']
    assert seen['argv'][seen['argv'].index('--mamba-host-slots') + 1] == '32'
    assert seen['env']['FT_D3_TRACE'] == '1' and seen['env']['FT_DEV_D0'] == '1'
    assert not any('ROUTE_TRACE' in key for key in seen['env'])
    assert (tmp_path/'ENV.txt').read_text() and 'ServerArgs' in (tmp_path/'serve_args.txt').read_text()


def test_r011_reverse_trace_mapping_and_forward_input_rejection(monkeypatch, tmp_path):
    assert m.TRACE == Path('/data2/_shared/runs/ft_rounds/E1-R003-v2/trace_rev.json')
    assert m.TRACE_SHA == '097b7a039e730d356985f47bc9fd747c86f4658fc6b89f1dec3243c0771b5e24'
    assert m.TARGET_INDEX == 7 and m.TARGET_MESSAGES_SHA == 'e3a67ebe075b0126'
    rows = [{'messages': [{'role': 'user', 'content': str(i)}]} for i in range(8)]
    forward = json.dumps({'rounds': rows}).encode()
    reverse = json.dumps({'rounds': list(reversed(rows))}).encode()
    original = tmp_path / 'trace.json'; original.write_bytes(forward)
    retained = tmp_path / 'trace_rev.json'; retained.write_bytes(reverse)
    monkeypatch.setattr(m, 'TRACE_SHA', hashlib.sha256(reverse).hexdigest())
    accepted = tmp_path / 'accepted'; accepted.mkdir()
    trace = m.bind_trace(accepted, retained)
    client = Client()
    monkeypatch.setattr(m, 'TARGET_MESSAGES_SHA', client.messages_digest(trace['rounds'][7]['messages']))
    assert m.target_binding(trace, client) == {'trace_index': 7, 'history_uid': 8, 'messages_sha': client.messages_digest(rows[0]['messages'])}
    rejected = tmp_path / 'rejected'; rejected.mkdir()
    with pytest.raises(RuntimeError, match='retained R011 input'):
        m.bind_trace(rejected, original)
    assert not (rejected / 'trace_input.json').exists()
    with pytest.raises(RuntimeError, match='target message identity'):
        m.target_binding({'rounds': rows}, client)
