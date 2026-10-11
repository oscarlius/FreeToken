import importlib.util
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


DEVELOPMENT = Path(__file__).resolve().parents[1]
FROZEN_BASE_SHA256 = '51d8216e14417a6d922c44f3048082f985dfb59d8872dfc78ac0984f027fcd16'
LEGACY_BASE = DEVELOPMENT / 't16_legacy_base_runner.py'
FROZEN_BASE = LEGACY_BASE if LEGACY_BASE.is_file() else DEVELOPMENT.parent / 'plan/01_测试与调研/batches/t16_runner.py'
FULL_TAIL_BASE = DEVELOPMENT / 't16_full_tail_base_runner.py'
ADAPTER = DEVELOPMENT / 't16_candidate_runner_full_tail.py'


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if hashlib.sha256(FROZEN_BASE.read_bytes()).hexdigest() != FROZEN_BASE_SHA256:
    raise RuntimeError(f'frozen legacy base hash differs: {FROZEN_BASE}')


frozen = load_module('t16_frozen_base_for_full_tail_test', FROZEN_BASE)
runner = load_module('t16_full_tail_adapter_for_test', ADAPTER)


EVENTS = [
    (1, 14, 0),
    (1, 32064, 0),
    (1, 6675, 0),
    (1, 6400, 0),
    (1, 624, 0),
    (1, 19, 6656),
    (1, 48, 6976),
    (1, 19, 6656),
    (1, 48, 6976),
    (1, 19, 6656),
    (1, 48, 6976),
    (1, 19, 6656),
    (1, 48, 6976),
]


def write_arm(path, *, missing_event=False, h2d_offset=0):
    path.mkdir()
    events = EVENTS[:-1] if missing_event else EVENTS
    path.joinpath('serve.log').write_text(''.join(
        'Prefill batch, #new-seq: %d, #new-token: %d, #cached-token: %d\n' % event
        for event in events
    ))
    path.joinpath('d0_prefill.jsonl').write_text(''.join(
        json.dumps({
            'chunk': index,
            'h2d_bytes': 100 + index + h2d_offset,
            'd2d_bytes': 200 + index,
            'seg_reason': 'anchor_cap' if index == 3 else 'other',
            't_start': float(index),
            't_end': float(index + 1),
            'reqs': [{'rid': index, 'new_tokens': event[1], 'cached_tokens': event[2]}],
        }) + '\n'
        for index, event in enumerate(EVENTS)
    ))
    path.joinpath('prefill_seq.txt').write_text(''.join(
        '#new-seq: %d, #new-token: %d, #cached-token: %d\n' % event
        for event in EVENTS[1:]
    ))


def test_frozen_live_comparison_reproduces_r019_parent_tail_failure(tmp_path):
    parent, fresh = tmp_path / 'parent', tmp_path / 'new'
    write_arm(parent)
    write_arm(fresh)

    with pytest.raises(ValueError, match=r'old=13/12, new=13/13'):
        frozen.check_prefill(parent, fresh, True, False)

    assert runner.base['check_prefill'](parent, fresh, True, True) == {
        'h2d': 'SAME',
        'parent_rows': 13,
        'new_rows': 13,
        'all_prefill_events': 13,
        'tail_aligned': True,
        'parent_tail_aligned': True,
    }
    assert parent.joinpath('prefill_seq.txt').read_bytes() == fresh.joinpath('prefill_seq.txt').read_bytes()
    assert len(parent.joinpath('prefill_seq.txt').read_text().splitlines()) == 12


def test_full_tail_protocol_rejects_missing_event_missing_tail_or_transfer_mismatch(tmp_path):
    parent, fresh = tmp_path / 'parent', tmp_path / 'new'
    write_arm(parent)
    write_arm(fresh, missing_event=True)
    with pytest.raises(ValueError, match='full prefill event sequence differs'):
        runner.base['check_prefill'](parent, fresh, True, True)

    broken_tail = tmp_path / 'missing-tail-source'
    (broken_tail / 'python/freetoken/moe').mkdir(parents=True)
    (broken_tail / 'python/freetoken/moe/offload_cache.py').write_text('def end_prefill(self):\n    return None\n')
    assert not runner.base['has_d02_prefill_tail'](broken_tail)

    mismatch = tmp_path / 'mismatch'
    write_arm(mismatch, h2d_offset=1)
    with pytest.raises(ValueError, match='H2D/D2D DIFF at row 0'):
        runner.base['check_prefill'](parent, mismatch, True, True)


def test_adapter_refuses_a_declared_tree_without_the_terminal_tail_marker(monkeypatch, tmp_path):
    made = make_live_runner(monkeypatch, tmp_path, 'D06')
    made.directory.rmdir()
    monkeypatch.setitem(runner.base, 'has_d02_prefill_tail', lambda _: False)

    with pytest.raises(ValueError, match='both declared trees must publish the D02 final prefill segment'):
        made.execute()

    assert not made.directory.exists()


class FakeProcess:
    pid = 4242

    def poll(self):
        return None


def options(card):
    return SimpleNamespace(
        case=card,
        gate=None,
        rid='E2-R999-gate-' + card,
        batch=999,
        candidate_commit=runner.CASES[card]['new_commit'],
        run=True,
    )


def make_live_runner(monkeypatch, tmp_path, card):
    monkeypatch.setattr(runner, 'ROUNDS', tmp_path)
    monkeypatch.setattr(runner, 'ROOT', tmp_path / 'source')
    monkeypatch.setattr(runner, 'WRAPPERS', tmp_path)
    monkeypatch.setitem(runner.base, 'ROUNDS', tmp_path)
    monkeypatch.setitem(runner.base, 'ROOT', tmp_path / 'source')
    monkeypatch.setitem(runner.base, 'SCR', tmp_path / 'scripts')
    runner.base['SCR'].mkdir()
    monkeypatch.setitem(runner.base, 'PY', 'python')
    monkeypatch.setitem(runner.base, 'FT', 'ft')
    monkeypatch.setitem(runner.base, 'MODEL', 'model')
    monkeypatch.setitem(runner.base, 'command', lambda argv, **_: 'source' if argv[0] == 'git' else '0')
    monkeypatch.setattr(runner.base['runpy'], 'run_path', lambda _: {
        'parse': lambda _: {
            '_unique_suffix': repr('.pid=4242'),
            'model_path': repr('model'),
            'server_port': '8095',
            'special_token_ckpt': 'True',
        },
    })
    made = runner.CandidateRunner(options(card))
    made.directory.mkdir()
    made.status = made.directory / 'status.json'
    monkeypatch.setattr(made, 'gate', lambda *_: 'candidate source')
    monkeypatch.setattr(made, 'set_status', lambda **_: None)
    monkeypatch.setattr(made, 'stop', lambda: setattr(made, 'proc', None))
    monkeypatch.setitem(runner.base, 'has_d02_prefill_tail', lambda _: True)
    return made


def attach_mock_probe(monkeypatch, made):
    def popen(_argv, **kwargs):
        log = kwargs['stdout']
        log.write('Parsed arguments\n')
        log.write('Prefill batch, #new-seq: 1, #new-token: 14, #cached-token: 0\n')
        log.flush()
        return FakeProcess()

    def ready(arm):
        arm.joinpath('d0_prefill.jsonl').write_text(''.join(
            json.dumps({
                'chunk': index,
                'h2d_bytes': 100 + index,
                'd2d_bytes': 200 + index,
                'seg_reason': 'anchor_cap' if index == 3 else 'other',
                't_start': float(index),
                't_end': float(index + 1),
                'reqs': [{'rid': index, 'new_tokens': event[1], 'cached_tokens': event[2]}],
            }) + '\n'
            for index, event in enumerate(EVENTS)
        ))

    def probe(argv, **_kwargs):
        if str(argv[1]).endswith('cold_eq.py'):
            target = int(argv[4])
            Path(argv[3]).write_text(json.dumps({
                'text': 'same output',
                'events': 1,
                'record': {
                    'cold_id': argv[2],
                    'built_tokens': target,
                    'cached_tokens': 0,
                    'prompt_tokens': target,
                    'completion_tokens': 1,
                    'ttft_s': 0.1,
                },
            }))
        else:
            Path(argv[2]).write_text(json.dumps({'reps': 5, 'single': [1.0] * 5, 'multi': [1.0] * 5}))
            with made._live_log.open('a') as log:
                for event in EVENTS[1:]:
                    log.write('Prefill batch, #new-seq: %d, #new-token: %d, #cached-token: %d\n' % event)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runner.base['subprocess'], 'Popen', popen)
    monkeypatch.setattr(runner.base['subprocess'], 'run', probe)
    monkeypatch.setattr(made, 'ready', ready)


@pytest.mark.parametrize('card', ['D06', 'D07'])
def test_live_run_probe_uses_full_parent_tail_for_d06_and_d07(monkeypatch, tmp_path, card):
    made = make_live_runner(monkeypatch, tmp_path, card)
    attach_mock_probe(monkeypatch, made)
    parent = made.directory / 'parent'
    fresh = made.directory / 'new'

    made._live_log = parent / 'serve.log'
    made.run_arm('parent', tmp_path / 'parent-source', made.case['parent_commit'], True)
    made._live_log = fresh / 'serve.log'
    made.run_arm('new', tmp_path / 'new-source', made.case['new_commit'], True, compare_to=parent)

    assert runner.base['check_prefill'](parent, fresh, True, True)['parent_rows'] == 13
    assert parent.joinpath('prefill_seq.txt').read_bytes() == fresh.joinpath('prefill_seq.txt').read_bytes()
    assert len(parent.joinpath('prefill_seq.txt').read_text().splitlines()) == 12


@pytest.mark.parametrize('card', ['D01', 'D02', 'D03', 'D06', 'D07', 'D14'])
def test_live_run_probe_uses_source_coverage_for_every_card(monkeypatch, tmp_path, card):
    made = make_live_runner(monkeypatch, tmp_path, 'D06')
    made.options.gate = card
    attach_mock_probe(monkeypatch, made)
    arm = made.directory / 'arm'
    compared = made.directory / 'compared'
    made._live_log = compared / 'serve.log'
    made.run_arm('compared', tmp_path / 'source-a', made.case['parent_commit'], True)

    seen = []
    original = runner.base['check_prefill']
    monkeypatch.setitem(runner.base, 'check_prefill', lambda *_paths, **kwargs: seen.append(kwargs) or {'ok': True})
    made._live_log = arm / 'serve.log'
    made.run_arm('arm', tmp_path / 'source-b', made.case['new_commit'], True, compare_to=compared)

    assert seen == [{'tail_fix': True, 'parent_tail_fix': True}]
    monkeypatch.setitem(runner.base, 'check_prefill', original)


def test_archive_binds_the_verified_full_tail_base_bytes(monkeypatch, tmp_path):
    made = make_live_runner(monkeypatch, tmp_path, 'D06')
    made.directory.rmdir()
    wrapper = tmp_path / f'batch999_{made.options.rid}_python.sh'
    wrapper.write_text('owned wrapper')
    probe = runner.base['SCR'] / 'probe.py'
    probe.write_bytes(b'probe')
    monkeypatch.setitem(runner.base, 'TOOL_MD5', {
        'probe.py': runner.hashlib.md5(b'probe').hexdigest(),
    })
    monkeypatch.setitem(runner.base, 'command', lambda argv, **_: (
        made.case['parent_commit'] if argv[:4] == ['git', '-C', str(tmp_path / 'source/wt/e2d06'), 'show']
        else 'source'
    ))
    monkeypatch.setattr(made, 'compiled_extensions', lambda _: {'cpu': {'sha256': 'same'}})
    monkeypatch.setattr(made, 'lock_take', lambda: None)
    monkeypatch.setattr(made, 'lock_release', lambda: None)
    monkeypatch.setattr(made, 'stop', lambda: None)
    monkeypatch.setattr(made, 'run_arm', lambda name, *_args, **_kwargs: (made.directory / name).mkdir() or made.directory / name)
    monkeypatch.setattr(made, 'compare', lambda *_args: {'checked': True})

    made.execute()

    binding = json.loads((made.directory / 'candidate_binding.json').read_text())
    archived = (made.directory / 'base_runner_batch999.py').read_bytes()
    assert binding['base_runner_sha256'] == runner.BASE_SHA256
    assert binding['base_runner_filename'] == 't16_full_tail_base_runner.py'
    assert runner.hashlib.sha256(archived).hexdigest() == runner.BASE_SHA256
    assert archived == runner._base_source
