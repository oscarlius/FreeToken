"""CPU integration boundaries for the actual ordinary R049 workload runner."""
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import threading
import sys
import pytest

HERE = Path(__file__).parent

def load(name):
    spec = importlib.util.spec_from_file_location(name.removesuffix('.py'), HERE/name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def encoded_sha(value):
    return hashlib.sha256(json.dumps(value, separators=(',', ':')).encode()).hexdigest()

def actual_record(tmp_path):
    fixture = load('test_r049_t21_ordinary_runtime_cpu_v10.py')
    receipt = fixture.request_receipts(tmp_path)
    bound = fixture.bind_receipts(tmp_path, receipt)
    adapter = load('r049_t21_ordinary_adapter_v9.py')
    record = adapter.ordinary_binding(bound)
    response = {'content_text': 'ok', 'reasoning_text': '', 'tool_calls': []}
    record.update(actual_input_binding=bound, response=response,
                  full_response_sha256=encoded_sha(response), model_output_sha256=encoded_sha(response),
                  ttft_s=1.0, decode_tps=2.0)
    return record

def test_runner_consumes_actual_seven_argument_binding_and_denies_ack(tmp_path):
    runner = load('r049_t21_ordinary_prepare_v14.py')
    record = actual_record(tmp_path)
    assert runner.ordinary_record_binding(record)['uid'] == 7
    with pytest.raises(RuntimeError):
        runner.ordinary_record_binding({'actual_input_binding': {'ft_dev': {'uid': 7}}})

def test_stream_timing_uses_usage_count_not_number_of_chunks(monkeypatch, tmp_path):
    adapter = load('r049_t21_ordinary_adapter_v9.py')
    payload = tmp_path/'payload.json'
    payload.write_text(json.dumps({'stream': True, 'stream_options': {'include_usage': True}}))
    rows = [
        {'id': 'chatcmpl-7', 'choices': [{'delta': {'content': 'output'}, 'finish_reason': None}]},
        {'id': 'chatcmpl-7', 'choices': [{'delta': {}, 'finish_reason': 'length'}],
         'usage': {'prompt_tokens': 3, 'completion_tokens': 128}},
    ]
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def __iter__(self):
            return iter([('data: '+json.dumps(row)+'\n\n').encode() for row in rows] + [b'data: [DONE]\n\n'])
    monkeypatch.setattr(adapter.urllib.request, 'urlopen', lambda *args, **kwargs: Response())
    clock = iter([100, 110, 1_000_000_110, 1_000_000_120])
    monkeypatch.setattr(adapter.time, 'monotonic_ns', lambda: next(clock))
    api = tmp_path/'api.json'
    adapter.ordinary_stream_request('http://127.0.0.1:12340/v1', payload, api)
    timing = adapter.timing_from_sse(api)
    assert timing['decode_tps'] == 127
    assert timing['completion_tokens'] == 128
    assert timing['ttft_s'] == 1e-8
    assert timing['chunk_clock_origin'] == 'network_sse_chunk_not_backend_token'

@pytest.mark.parametrize('field', ['dispatch_monotonic_ns', 'first_output_event'])
def test_missing_stream_clocks_fail_closed(tmp_path, field):
    adapter = load('r049_t21_ordinary_adapter_v9.py')
    doc = {'dispatch_monotonic_ns': 1, 'first_output_event': {'monotonic_ns': 10},
           'terminal_event': {'monotonic_ns': 1_000_000_010}, 'usage': {'completion_tokens': 3}}
    doc.pop(field)
    path = tmp_path/'api.json'; path.write_text(json.dumps(doc))
    with pytest.raises(RuntimeError): adapter.timing_from_sse(path)

def test_equivalence_ignores_runtime_identity_but_detects_token_change(tmp_path):
    runner = load('r049_t21_ordinary_prepare_v14.py')
    record = actual_record(tmp_path)
    baseline_texts, baseline_bindings = {}, {}
    output = tmp_path/'cold.json'
    output.write_text(json.dumps({'schema': 'ft_t21_cold_ordinary/v1', 'record': record}))
    runner._checked_output(tmp_path, 'cold32k_1', output, record, None, baseline_texts, baseline_bindings)
    baseline = {'texts': baseline_texts, 'request_input_bindings': baseline_bindings}
    changed = {**record, 'uid': 99, 'evidence': {'path': 'different', 'pid': 100}, 'ttft_s': 8.0}
    runner._checked_output(tmp_path, 'cold32k_1', output, changed, baseline, {}, {})
    changed['token_ids_sha256'] = 'b'*64
    with pytest.raises(runner.T21NotMet):
        runner._checked_output(tmp_path, 'cold32k_1', output, changed, baseline, {}, {})
    assert (tmp_path/'not_met.json').is_file()

def test_completion_accounting_does_not_count_nested_evidence_twice(tmp_path):
    runner = load('r049_t21_ordinary_prepare_v14.py')
    record = actual_record(tmp_path)
    path = tmp_path/'cold.json'
    path.write_text(json.dumps({'schema': 'ft_t21_cold_ordinary/v1', 'record': record}))
    assert runner._output_tokens({'cold32k_1': path}) == 2

def test_generated_tool_id_is_retained_but_not_used_for_model_equivalence():
    adapter = load('r049_t21_ordinary_adapter_v9.py')
    left = {'content_text': '', 'reasoning_text': 'reason', 'tool_calls': [
        {'id': 'call_read_file_random_a', 'type': 'function', 'function': {'name': 'read_file', 'arguments': '{"path":"README.md"}'}}]}
    right = {**left, 'tool_calls': [{**left['tool_calls'][0], 'id': 'call_read_file_random_b'}]}
    assert left != right and adapter.model_output(left) == adapter.model_output(right)
    right['tool_calls'][0]['function'] = {'name': 'read_file', 'arguments': '{"path":"other.md"}'}
    assert adapter.model_output(left) != adapter.model_output(right)

def test_heldout_replay_uses_sealed_messages_and_distinct_role_directories(monkeypatch, tmp_path):
    runner = load('r049_t21_ordinary_prepare_v14.py')
    digest = 'a'*64
    originals = SimpleNamespace(
        tool_specs=lambda: None,
        build_payload=lambda messages, model, tools, thinking, max_tokens: {
            'messages': messages, 'max_tokens': max_tokens,
        },
    )
    monkeypatch.setattr(runner, '_load_original', lambda: originals)
    monkeypatch.setattr(runner, '_load_tokenizer', lambda path: object())
    monkeypatch.setattr(runner, '_wire_ids', lambda payload: [10, 11])
    monkeypatch.setattr(runner, 'require_seed', lambda role: (tmp_path/(role+'.txt'), digest))
    traces = {}
    for role in ('seed_45k', 'seed_real'):
        path = tmp_path/(role+'.source.json')
        path.write_text(json.dumps({'schema': 'ft_r046c_ordinary_seed_trace/v1',
            'meta': {'seed_raw_sha256': digest, 'window': 98304, 'completed_k': 1,
                     'termination': 'window_hit'},
            'rounds': [{'messages': [{'role': 'user', 'content': 'sealed-'+role}],
                       'record': {'actual_input_binding': {'worker_input': {
                           'input_ids_sha256': encoded_sha([10, 11]), 'input_tokens': 2}}}}]}))
        traces[role] = path
    monkeypatch.setattr(runner, 'HELDOUT', traces)
    seen = []
    def request(directory, name, base, payload, observer, original, planned_ids):
        directory.mkdir(exist_ok=True)
        with (directory/(name+'.payload.json')).open('x') as stream: json.dump(payload, stream)
        seen.append((directory.name, payload['messages'], observer))
        return {'uid': len(seen), 'response': {'content_text': 'ok'}}
    monkeypatch.setattr(runner, '_bound_ordinary_request', request)
    arm = tmp_path/'L1'; arm.mkdir()
    for role, trace in traces.items():
        runner._timed_agent_replay(12340, trace, arm/(role+'_replay.json'), {}, None)
    assert [entry[0] for entry in seen] == ['seed_45k', 'seed_real']
    assert [entry[1][0]['content'] for entry in seen] == ['sealed-seed_45k', 'sealed-seed_real']
    assert all(entry[2] == arm/'ordinary_observer' for entry in seen)

def test_file_dry_exercises_request_and_observer_writer_families(tmp_path):
    runner = load('r049_t21_ordinary_prepare_v14.py')
    result = runner.run_workloads(tmp_path, 12340, {'d0': False}, file_dry_run=True)
    assert result['cpu_file_probe'] is True
    assert (tmp_path/'seed_real/round-11.payload.json').is_file()
    assert (tmp_path/'seed_45k/round-11.api.sse').is_file()
    assert (tmp_path/'two_decode/streams/right.binding.json').is_file()
    assert (tmp_path/'ordinary_observer/input_ids.cpu_probe.json').is_file()

def test_production_cli_receives_serve_while_diagnostic_receives_ft_script(tmp_path):
    runner = load('r049_t21_ordinary_prepare_v14.py')
    stub = SimpleNamespace(clean_environment=lambda wt: {},
        serve_argv=lambda port: ['/venv/bin/ft', 'serve', '--port', str(port)])
    env, argv, _ = runner.service_files(stub, tmp_path/'L1', 12340, 'lru', tmp_path/'profile.strp', False)
    assert argv[argv.index('--')+1] == 'serve'
    env, argv, _ = runner.service_files(stub, tmp_path/'L_D0', 12340, 'lru', tmp_path/'profile.strp', True)
    assert argv[argv.index('--')+1] == '/venv/bin/ft'
    assert env['FT_DEV_D0'] == '1' and 'FT_DEV_PAUSE_ENDPOINT' not in env

def test_actual_config_accepts_only_declared_policy_and_process_metadata(tmp_path):
    runner = load('r049_t21_ordinary_prepare_v14.py')
    fields = {'server_port': '12340', 'memory_ratio': '0.88', 'kv_reserve_tokens': '98304',
        'max_seq_len_override': '98304', 'max_running_req': '2', 'prefill_layer_major': 'True',
        'max_extend_tokens': '4096', 'cuda_graph_max_bs': '2', '_unique_suffix': "'.pid=1'"}
    left, right = tmp_path/'L1', tmp_path/'P1'
    left.mkdir(); right.mkdir()
    runner.validate_actual_args(left, fields, 12340)
    runner.validate_actual_args(right, {**fields, 'server_port': '12342', '_unique_suffix': "'.pid=2'"}, 12342)
    (left/'ENV.json').write_text(json.dumps({'FT_DEV_EXPERT_POLICY': 'lru'}))
    (right/'ENV.json').write_text(json.dumps({'FT_DEV_EXPERT_POLICY': 'profile', 'FT_DEV_EXPERT_PROFILE': '/run/seed12k_only.strp'}))
    (right/'serve_args_diff.json').write_text(json.dumps(runner.arm_difference_declaration('profile', False)))
    runner.compare_actual_configuration(right, left)
    (right/'serve_args_actual_diff.json').unlink()
    actual = json.loads((right/'serve_args_actual.json').read_text())
    actual['parsed']['max_extend_tokens'] = '8192'
    (right/'serve_args_actual.json').write_text(json.dumps(actual))
    with pytest.raises(RuntimeError): runner.compare_actual_configuration(right, left)

@pytest.mark.parametrize('bad', [None, 'short', 'nonoverlap', 'sampling', 'eos'])
def test_two_ordinary_streams_bind_actual_inputs_and_tokens(monkeypatch, tmp_path, bad):
    adapter = load('r049_t21_ordinary_adapter_v9.py')
    fixture = load('test_r049_t21_ordinary_runtime_cpu_v10.py')
    all_inputs, all_tokens, origins, expected = [], [], {}, {}
    for index, name in enumerate(('left', 'right')):
        directory = tmp_path/name; directory.mkdir()
        payload, api, inputs, tokens, ids, raw = fixture.request_receipts(directory)
        uid = 7+index; count = 510 if bad == 'short' and index else 512
        payload_doc = json.loads(payload.read_text())
        payload_doc.update(max_tokens=512, ignore_eos=True)
        payload_doc.pop('stop', None)
        if bad == 'sampling':
            payload_doc['ignore_eos'] = False
        payload.write_text(json.dumps(payload_doc))
        actual_ids = [10, 11+index]
        ids.write_bytes(json.dumps(actual_ids, separators=(',', ':')).encode())
        input_row = json.loads(inputs.read_text())
        input_row.update(uid=uid, input_ids_sha256=fixture.digest(ids), input_ids_file_sha256=fixture.digest(ids))
        all_inputs.append(input_row)
        template = json.loads(tokens.read_text().splitlines()[0])
        for sequence in range(1, count+1):
            all_tokens.append({**template, 'uid': uid, 'request_seq': sequence,
                'completion_tokens_cumulative': sequence, 'next_token': 20+sequence,
                'finished': sequence == count, 'finish_reason': ('stop' if bad == 'eos' else 'length') if sequence == count else None,
                'time_ns': 10+sequence})
        events = [{'id': f'chatcmpl-{uid}', 'choices': [{'delta': {'content': name}, 'finish_reason': None}]},
                  {'id': f'chatcmpl-{uid}', 'choices': [{'delta': {}, 'finish_reason': 'stop' if bad == 'eos' else 'length'}],
                   'usage': {'prompt_tokens': 2, 'completion_tokens': count}}]
        raw.write_bytes((''.join('data: '+json.dumps(event)+'\n\n' for event in events)
                         +'data: [DONE]\n\n').encode())
        api_doc = json.loads(api.read_text())
        api_doc['payload_source'] = {'path': str(payload), 'sha256': fixture.digest(payload)}
        api_doc.update(uid=uid, usage=events[-1]['usage'], finish_reason='stop' if bad == 'eos' else 'length', sse_sha256=fixture.digest(raw),
            dispatch_monotonic_ns=100, first_output_event={'monotonic_ns': 1_100 if index == 0 else
                (3_000_000_000 if bad == 'nonoverlap' else 1_200), 'time_ns': 1000},
            terminal_event={'monotonic_ns': 4_000_000_000 if index else 2_000_000_000, 'time_ns': 2000})
        clocks = Path(api_doc['events'])
        clocks.write_text(''.join(json.dumps({'event': event, **stamp})+'\n' for event, stamp in zip(
            events, (api_doc['first_output_event'], api_doc['terminal_event']))))
        api_doc['events_sha256'] = fixture.digest(clocks)
        api.write_text(json.dumps(api_doc))
        origins[name] = (payload, api, raw)
        expected[name] = actual_ids
    inputs, tokens = tmp_path/'inputs.jsonl', tmp_path/'tokens.jsonl'
    inputs.write_text(''.join(json.dumps(row)+'\n' for row in all_inputs))
    tokens.write_text(''.join(json.dumps(row)+'\n' for row in all_tokens))
    barrier = threading.Barrier(2, timeout=10)
    def send(base, payload, api, timeout):
        barrier.wait()
        name = Path(payload).parent.name
        doc = json.loads(origins[name][1].read_text())
        raw = api.with_suffix('.sse'); raw.write_bytes(origins[name][2].read_bytes())
        doc.update(sse=str(raw), sse_sha256=fixture.digest(raw))
        api.write_text(json.dumps(doc))
    monkeypatch.setattr(adapter, 'ordinary_stream_request', send)
    original = SimpleNamespace(consume_stream=lambda events, t0: {
        'content_text': ''.join(choice.get('delta', {}).get('content', '') for event in events for choice in event.get('choices', [])),
        'reasoning_text': '', 'tool_calls': []})
    args = ('http://127.0.0.1:12340/v1', origins['left'][0], origins['right'][0],
            tmp_path/'streams', inputs, tokens, expected, original)
    if bad:
        with pytest.raises((RuntimeError, ValueError)): adapter.run_pair(*args)
    else:
        value = adapter.run_pair(*args)
        assert [row['uid'] for row in value['records']] == [7, 8]
        assert [row['completion_tokens'] for row in value['records']] == [512, 512]
        assert value['live_output_overlap_s'] > 0
        assert value['overlap_token_rate'] is None


def test_two_decode_payload_is_only_hard_length_workload():
    runner = load('r049_t21_ordinary_prepare_v14.py')
    original = SimpleNamespace(build_payload=lambda messages, model, tools, thinking, max_tokens: {
        'model': model, 'messages': messages, 'max_tokens': max_tokens, 'stop': 'wrong',
        'ignore_eos': False, 'stream': True, 'stream_options': {'include_usage': True}})
    payload = runner._two_decode_payload(original, [{'role': 'user', 'content': 'two'}])
    assert payload['max_tokens'] == 512 and payload['ignore_eos'] is True
    assert 'stop' not in payload


def test_child_failure_writes_terminal_and_exact_lock_release(monkeypatch, tmp_path):
    runner = load('r049_t21_ordinary_prepare_v14.py')
    runner.ROUNDS = tmp_path/'rounds'; runner.RID = 'E2-R049a-test'
    owner = {'pid': 11, 'start_ticks': 12}
    released = []
    d = SimpleNamespace(take_d07_gpu_lock=lambda rid, batch: owner,
                        release_d07_gpu_lock=lambda actual: released.append(actual))
    monkeypatch.setattr(runner.sys, 'platform', 'linux')
    monkeypatch.setattr(runner, 'require_section13_runtime_tooling', lambda: None)
    monkeypatch.setattr(runner, 'require_dry_run_receipt', lambda: {'path': 'dry'})
    monkeypatch.setattr(runner, 'load_d07', lambda: d)
    monkeypatch.setattr(runner, 'admission', lambda receipt: None)
    monkeypatch.setattr(runner, 'require_receipt', lambda d, batch, receipt: None)
    monkeypatch.setattr(runner, 'run_measurements', lambda batch: (_ for _ in ()).throw(RuntimeError('raw measurement failure')))
    with pytest.raises(RuntimeError, match='raw measurement failure'):
        runner.child(4, tmp_path/'launch.json')
    terminal = runner.ROUNDS/runner.RID
    failure = json.loads((terminal/'failed_harness.json').read_text())
    cleanup = json.loads((terminal/'owned_cleanup.json').read_text())
    assert failure['error'] == 'raw measurement failure'
    assert cleanup['owner'] == owner and cleanup['lock_release'] == 'released'
    assert released == [owner]


@pytest.mark.skipif(sys.platform != 'linux', reason='actual candidate CPU path is Linux-only')
def test_actual_candidate_api_tokenizemsg_and_scheduler_eos_boundary_cpu():
    """Actual e2d15 API normalization/TokenizeMsg and private scheduler drain, CPU only."""
    runner = load('r049_t21_ordinary_prepare_v14.py')
    if not runner.WT.is_dir() or not runner.MODEL_PATH.is_dir():
        pytest.skip('candidate worktree/tokenizer unavailable')
    original = SimpleNamespace(build_payload=lambda messages, model, tools, thinking, max_tokens: {
        'model': model, 'messages': messages, 'max_tokens': max_tokens,
        'temperature': 0, 'stream': True, 'stream_options': {'include_usage': True},
        'chat_template_kwargs': {'enable_thinking': False}})
    payload = runner._two_decode_payload(original, [{'role': 'user', 'content': 'CPU candidate boundary'}])
    ids, contract = runner._two_decode_candidate_contract(payload)
    assert ids and contract == {'max_tokens': 512, 'ignore_eos': True, 'stop_strs': [], 'token_count': len(ids)}

    import contextlib
    import torch
    import sys
    sys.path.insert(0, str(runner.WT/'python'))
    from freetoken.core import SamplingParams
    from freetoken.scheduler.scheduler import Scheduler

    class Req:
        uid = 9; table_idx = -1; output_len = 512; aborted = False
        def __init__(self, ignore_eos):
            self.input_ids = torch.tensor([100, 101], dtype=torch.int64)
            self.max_device_len = 2
            self.sampling_params = SamplingParams(max_tokens=512, ignore_eos=ignore_eos, stop_strs=[])
        def append_host(self, token): self.input_ids = torch.cat((self.input_ids, token))
    class Sync: 
        def synchronize(self): return None
    class Cache:
        def lazy_free_region(self): return contextlib.nullcontext()
    class Decode:
        def __init__(self): self.running_reqs=[]
        def remove_req(self, req): self.running_reqs.append(req)
    class Reporter:
        def report_batch(self, *args, **kwargs): return None
    def execute(ignore_eos):
        req = Req(ignore_eos)
        batch = SimpleNamespace(reqs=[req], is_prefill=False)
        received = []
        fake = SimpleNamespace(cache_manager=Cache(), finished_reqs=set(), eos_token_ids={42},
            toolcall_anchor_id=-1, d3_extra_anchor_ids=set(), decode_manager=Decode(),
            prefill_manager=SimpleNamespace(pending_list=[]), config=SimpleNamespace(page_size=1),
            status_reporter=Reporter(), _free_req_resources=lambda req: None,
            _kv_usage_pages=lambda: (0, 1), _mamba_slot_usage=lambda: None,
            _swa_token_usage=lambda: None, _gpu_mem_bytes=lambda: 0,
            send_result=lambda reply: received.extend(reply), _match_stop_str=lambda req: None)
        Scheduler._process_last_data(fake, (SimpleNamespace(batch=batch), (None, [torch.tensor(42)], Sync())))
        return received[0]
    assert execute(False).finish_reason == 'stop'
    assert execute(True).finish_reason == 'length'
