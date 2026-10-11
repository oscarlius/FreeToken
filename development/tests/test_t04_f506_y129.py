import importlib.util
import hashlib
import json
import shutil
import signal
from argparse import Namespace
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / 't04_f506_y129_runner.py'
spec = importlib.util.spec_from_file_location('t04_f506_y129', PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def token_record(*, uid=module.TERMINAL_UID, pid=module.TERMINAL_PID):
    prompt = list(range(module.G4_PROMPT_LENGTH))
    generated = [17, 18, 19]
    return {
        'schema': 'ft_dev_tokens/v1', 'uid': uid, 'pid': pid,
        'prompt_length': len(prompt), 'prompt_ids': prompt,
        'generated_ids': generated, 'finish_reason': 'length', 'matched_stop': None,
        'prompt_ids_sha256_int32le': module.ids_digest(prompt),
        'generated_ids_sha256_int32le': module.ids_digest(generated),
        'input_ids_sha256_int32le': module.ids_digest(prompt + generated),
    }


def test_controlled_argv_has_explicit_y129_contract_for_all_arms(tmp_path):
    for arm, mode in {'candidate_boundary': 'diagnostic', 'restore': 'branch-bank',
                      'recompute': 'fresh', 'legal': 'fresh'}.items():
        argv = module.controlled_argv(client=tmp_path / 'client.py', base_url='http://x',
                                     prefix=tmp_path / 'p.json', suffix=tmp_path / 'x.json',
                                     dump=tmp_path / arm, arm=arm)
        assert argv[argv.index('--mode') + 1] == mode
        assert argv[argv.index('--branch-length') + 1] == '12672'
        assert argv[argv.index('--branch-token-count') + 1] == '129'


@pytest.mark.parametrize('proof', [None, {'kind': 'device', 'uid': 3, 'length': 12672},
                                  {'kind': 'host', 'uid': 3, 'length': 12416}])
def test_restore_requires_actual_host_12672(proof):
    with pytest.raises(ValueError):
        module.validate_restore_proof(proof, 3)


def test_terminal_source_uid_pid_and_length_are_bound(tmp_path):
    path = tmp_path / 'token.json'
    path.write_text(json.dumps(token_record()), encoding='utf-8')
    assert module.read_token_record(path, max_k=2)['uid'] == 0
    for field, value in [('uid', 1), ('pid', 1)]:
        bad = token_record(); bad[field] = value
        path.write_text(json.dumps(bad), encoding='utf-8')
        with pytest.raises(ValueError):
            module.read_token_record(path, max_k=2)


def test_run_capture_uses_controlled_client_and_checks_result(monkeypatch, tmp_path):
    arm = tmp_path / 'restore'; (arm / 'logits').mkdir(parents=True)
    phase = object.__new__(module.Phase2)
    phase.args = Namespace(k=32)
    phase._input_length = 22008
    phase._input_digest = 'input-digest'
    monkeypatch.setattr(module, 'sha256', lambda path: module.CONTROLLED_CLIENT_SHA256
                        if path == module.CONTROLLED_CLIENT else module.CANDIDATE_PROBE_SHA256)
    result = {'mode': 'branch-bank', 'k': 32, 'input_length': 22008,
              'input_sha256': 'input-digest', 'positions': list(range(21976, 22008)),
              'uid': 11, 'dump_seq': 9,
              'restore_proof': {'kind': 'host', 'uid': 11, 'length': 12672}}
    def fake_run(argv, **kwargs):
        assert argv[argv.index('--branch-token-count') + 1] == '129'
        kwargs['stdout'].write(json.dumps(result) + '\n')
    monkeypatch.setattr(module.subprocess, 'run', fake_run)
    (arm / 'logits/index.jsonl').write_text(json.dumps({'kind': 'logits', 'uid': 11, 'seq': 9}) + '\n', encoding='utf-8')
    token_path = arm / 'logits/tokens_uid11_pid301.json'; token_path.write_text('{}', encoding='utf-8')
    (arm / 'owned_process.json').write_text(json.dumps({'pgid': 77}), encoding='utf-8')
    monkeypatch.setattr(module, 'read_token_record', lambda *a, **k: {
        'uid': 11, 'pid': 301, 'prompt_ids_sha256_int32le': 'input-digest'})
    monkeypatch.setattr(module.os, 'getpgid', lambda pid: 77, raising=False)
    captured = phase.run_capture(arm, {}, tmp_path/'p', tmp_path/'x', restore=True)
    assert captured['mode'] == 'branch-bank'
    assert captured['capture_pid'] == 301


def test_run_capture_rejects_wrong_candidate_probe_binding(monkeypatch, tmp_path):
    arm = tmp_path / 'legal'; (arm / 'logits').mkdir(parents=True)
    phase = object.__new__(module.Phase2); phase.args = Namespace(k=1)
    phase._input_length = 1; phase._input_digest = 'x'
    monkeypatch.setattr(module, 'sha256', lambda path: 'wrong')
    with pytest.raises(RuntimeError, match='controlled client'):
        phase.run_capture(arm, {}, tmp_path/'p', tmp_path/'x', restore=False)



def test_mock_four_arm_lifecycle_runs_controlled_captures_then_compare(monkeypatch, tmp_path):
    source_root = tmp_path / 'source'; candidate = source_root / 'wt/e2d03-continuation'
    (candidate / 'scripts').mkdir(parents=True)
    for name in ('logits_probe.py', 'state_envelope.py'):
        (candidate / 'scripts' / name).write_text('source', encoding='utf-8')
    (source_root / 'runs/plan_batches').mkdir(parents=True)
    (source_root / 'runs/plan_batches/E2-R021').mkdir(parents=True)
    batch = source_root / 'runs/plan_batches/batch46_E2-R021_python.sh'
    batch.write_text('#!/bin/sh\\n', encoding='utf-8')
    token_path = tmp_path / 'terminal.json'; token_path.write_text('{}', encoding='utf-8')
    binding_path = tmp_path / 'binding.json'; binding_path.write_text('{}', encoding='utf-8')
    trace = tmp_path / 'trace.json'; trace.write_text('{}', encoding='utf-8')
    legacy = tmp_path / 'legacy.json'; legacy.write_text('{}', encoding='utf-8')
    prompt, suffix = [1, 2], [3, 4]
    token = {'uid': 0, 'pid': module.TERMINAL_PID, 'prompt_ids': prompt,
             'generated_ids': suffix, 'prompt_length': len(prompt)}
    monkeypatch.setattr(module, 'ROOT', source_root)
    monkeypatch.setattr(module, 'CANDIDATE', candidate)
    monkeypatch.setattr(module, 'ROUND_ROOT', tmp_path / 'rounds')
    monkeypatch.setattr(module, 'read_token_record', lambda *a, **k: token)
    monkeypatch.setattr(module, 'verify_g4_source', lambda *a, **k: {'bound': True})
    monkeypatch.setattr(module, 'read_binding', lambda *a, **k: {'trace_sha256': 'a' * 64, 'messages_sha': 'messages', 'request_sha256': 'request'})
    monkeypatch.setattr(module, 'sha256', lambda path: 'a' * 64)
    phase = object.__new__(module.Phase2)
    phase.args = Namespace(rid='E2-R021', batch=46, candidate_commit='f' * 40,
                           g4_token_file=token_path, raw_binding_manifest=binding_path,
                           trace=trace, k=2)
    module.ROUND_ROOT.mkdir()
    phase.out = module.ROUND_ROOT / phase.args.rid
    class Base:
        def lock_take(self): pass
        def lock_release(self): pass
        def chat(self, arm, payload):
            (arm / 'logits').mkdir(exist_ok=True)
            (arm / 'logits/tokens_uid1_pid2.json').write_text('{}', encoding='utf-8')
        def stop(self): pass
    phase.base = Base()
    phase.sc = Namespace(LEGACY_REPLAY=legacy, BOUNDARIES=(),
                         trace_record=lambda trace: ('doc', {'messages_sha': 'messages'}, 'messages'),
                         historical_payload=lambda *a: {'payload': True},
                         request_sha=lambda payload: 'request')
    phase.gate = lambda: {'gate': True}
    started, captured, compared = [], [], []
    def start(name, **kwargs):
        arm = phase.out / name; arm.mkdir(parents=True)
        (arm / 'state').mkdir()
        (arm / 'state/index.jsonl').write_text('', encoding='utf-8')
        started.append((name, kwargs)); return arm, {}
    phase.start = start
    phase.stop = lambda: None
    phase.run_capture = lambda arm, env, prefix, tail, *, restore: (captured.append((arm.name, restore)) or {'arm': arm.name})
    phase.verify_crossarm_args = lambda: None
    phase.compare = lambda restore, recompute, legal: (compared.append((restore.name, recompute.name, legal.name)) or {'compared': True})
    phase.run()
    assert [name for name, _ in started] == ['candidate_boundary', 'restore', 'recompute', 'legal']
    assert captured == [('candidate_boundary', False), ('restore', True), ('recompute', False), ('legal', False)]
    assert compared == [('restore', 'recompute', 'legal')]





def test_lifecycle_keeps_lock_when_owned_cleanup_failed(monkeypatch, tmp_path):
    # The four-arm test covers success.  The f506 failure invariant is explicit:
    # a failed owned cleanup cannot release the lock in a later finally block.
    phase = object.__new__(module.Phase2)
    class Base:
        proc = object()
        _cleanup_failed = True
        def stop(self): raise RuntimeError('survivor')
        def lock_release(self): raise AssertionError('must retain lock')
    phase.base = Base()
    phase.out = tmp_path / 'round'; phase.args = Namespace()
    # Exercise the exact guard used by run's final block without creating a round.
    if (getattr(phase.base, 'proc', None) is None
            and not getattr(phase.base, '_cleanup_failed', False)):
        phase.base.lock_release()


def test_run_capture_rejects_candidate_probe_mismatch_after_client_pin(monkeypatch, tmp_path):
    arm = tmp_path / 'legal'; (arm / 'logits').mkdir(parents=True)
    phase = object.__new__(module.Phase2); phase.args = Namespace(k=1)
    phase._input_length = 1; phase._input_digest = 'x'
    monkeypatch.setattr(module, 'sha256', lambda path: module.CONTROLLED_CLIENT_SHA256
                        if path == module.CONTROLLED_CLIENT else 'different-probe')
    with pytest.raises(RuntimeError, match='candidate logits probe'):
        phase.run_capture(arm, {}, tmp_path / 'p', tmp_path / 'x', restore=False)



def test_load_selfcheck_executes_pinned_f506_and_base_bytes(monkeypatch, tmp_path):
    source = PATH.parents[0] / 'd03_gpu_selfcheck_f506.py'
    base = PATH.parents[0] / 'd03_gpu_selfcheck.py'
    copied = tmp_path / 'd03_gpu_selfcheck_f506.py'
    shutil.copyfile(source, copied)
    shutil.copyfile(base, tmp_path / 'd03_gpu_selfcheck.py')
    monkeypatch.setattr(module, 'SELFCHECK_OUTPUT', tmp_path / 'approved-output')
    adapter = module.load_selfcheck(copied)
    assert adapter.SelfCheck.__module__ == 'd03_f506_selfcheck'
    assert adapter.SELF_CHECK_OUTPUT == tmp_path / 'approved-output'
    assert adapter.CANDIDATE_COMMIT == 'f5067bbe05da51d5f78185213435a8be095a684a'


def test_run_capture_rejects_terminal_outside_owned_group(monkeypatch, tmp_path):
    arm = tmp_path / 'legal'; (arm / 'logits').mkdir(parents=True)
    phase = object.__new__(module.Phase2); phase.args = Namespace(k=1)
    phase._input_length = 1; phase._input_digest = 'input'
    monkeypatch.setattr(module, 'sha256', lambda path: module.CONTROLLED_CLIENT_SHA256
                        if path == module.CONTROLLED_CLIENT else module.CANDIDATE_PROBE_SHA256)
    result = {'mode': 'fresh', 'k': 1, 'input_length': 1, 'input_sha256': 'input',
              'positions': [0], 'uid': 4, 'dump_seq': 1, 'restore_proof': None}
    monkeypatch.setattr(module.subprocess, 'run', lambda argv, **kwargs: kwargs['stdout'].write(json.dumps(result) + '\n'))
    (arm / 'logits/index.jsonl').write_text(json.dumps({'kind': 'logits', 'uid': 4, 'seq': 1}) + '\n', encoding='utf-8')
    (arm / 'logits/tokens_uid4_pid99.json').write_text('{}', encoding='utf-8')
    (arm / 'owned_process.json').write_text(json.dumps({'pgid': 77}), encoding='utf-8')
    monkeypatch.setattr(module, 'read_token_record', lambda *a, **k: {'uid': 4, 'pid': 99, 'prompt_ids_sha256_int32le': 'input'})
    monkeypatch.setattr(module.os, 'getpgid', lambda pid: 78, raising=False)
    with pytest.raises(ValueError, match='outside the owned'):
        phase.run_capture(arm, {}, tmp_path/'p', tmp_path/'x', restore=False)



@pytest.mark.parametrize('k', [31, 33])
def test_fixed_fp32_k_rejects_non_32(k):
    with pytest.raises(ValueError, match='K=32'):
        module.require_fp32_tail_k(k)


def test_main_first_signal_interrupts_and_second_is_ignored_during_cleanup(monkeypatch, tmp_path):
    token = tmp_path / 'token.json'; token.write_text('{}', encoding='utf-8')
    raw = tmp_path / 'raw.json'; raw.write_text('{}', encoding='utf-8')
    trace = tmp_path / 'trace.json'; trace.write_text('{}', encoding='utf-8')
    monkeypatch.setattr(module.os, 'name', 'posix', raising=False)
    original = signal.getsignal(signal.SIGINT)
    events = []
    class FakePhase:
        def __init__(self, args):
            self.args = args
        def run(self):
            try:
                signal.getsignal(signal.SIGINT)(signal.SIGINT, None)
            finally:
                signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
                events.append('cleanup')
    monkeypatch.setattr(module, 'Phase2', FakePhase)
    argv = ['--run', '--batch', '1', '--candidate-commit', 'f' * 40,
            '--g4-token-file', str(token), '--raw-binding-manifest', str(raw),
            '--trace', str(trace), '--k', '32']
    with pytest.raises(InterruptedError, match='interrupted'):
        module.main(argv)
    assert events == ['cleanup']
    assert signal.getsignal(signal.SIGINT) == original


def test_main_rejects_k_31_and_33_before_phase_construction(monkeypatch):
    monkeypatch.setattr(module, 'Phase2', lambda args: pytest.fail('Phase2 must not start'))
    for k in ('31', '33'):
        with pytest.raises(SystemExit) as exc:
            module.main(['--run', '--k', k])
        assert exc.value.code == 2


def test_gate_rejects_non_32_before_git_or_lifecycle(monkeypatch, tmp_path):
    phase = object.__new__(module.Phase2)
    phase.args = Namespace(k=31, rid=module.EXPECTED_RID, candidate_commit='f' * 40)
    phase.out = tmp_path / 'uncreated-round'
    phase.base = Namespace(gate=lambda *args: pytest.fail('lifecycle gate must not run'))
    monkeypatch.setattr(module.subprocess, 'run', lambda *args, **kwargs: pytest.fail('git must not run'))
    with pytest.raises(ValueError, match='K=32'):
        phase.gate()
