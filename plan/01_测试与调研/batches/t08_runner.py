"""T08 production-mouth S1 remeasurement runner (CPU self-test is safe locally)."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

from e2_runtime import CardRunner, PY, SCR, WT
from t16_runner import ROUNDS, TOOL_MD5, write_new


SHARED = Path('/data2/_shared')
TRACE = SHARED / 'runs/ft_rounds/E1-R003-v2/trace.json'
TRACE_REV = SHARED / 'runs/ft_rounds/E1-R003-v2/trace_rev.json'
HIST_S5A = SHARED / 'runs/ft_rounds/E1-R001b/pLM_s5A.json'
AFFINITY = {1, *range(3, 48)}
LAUNCH = ['numactl', '--interleave=all', 'taskset', '-c', '1,3-47']
ASSIGNED_RIDS = {'P1': 'E2-R009', 'P2': 'E2-R009-p64k'}


def assigned_round(rid, phase):
    return phase in ASSIGNED_RIDS and rid == ASSIGNED_RIDS[phase]


def finite_positive(value):
    return type(value) in (float, int) and math.isfinite(value) and value > 0


def expected_configuration(window):
    """Keys are ServerArgs fields, not spellings of the serve CLI flags."""
    return {'prefill_layer_major': 'True', 'max_extend_tokens': '4096',
            'special_token_ckpt': 'True', 'max_seq_len_override': str(window)}


def validate_configuration(parsed, window):
    expected = expected_configuration(window)
    for key, value in expected.items():
        if parsed.get(key) != value:
            raise ValueError(f'parsed arguments mismatch {key}: {parsed.get(key)!r}')
    return expected


def read_jsonl(path):
    values = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not values:
        raise ValueError(f'empty JSONL: {path}')
    return values


def last_json(path):
    """Read the final JSON value from an unchanged helper log, including pretty JSON."""
    text = path.read_text()
    decoder = json.JSONDecoder()
    candidates = []
    for match in re.finditer(r'[\[{]', text):
        try:
            value, end = decoder.raw_decode(text[match.start():])
        except json.JSONDecodeError:
            continue
        if not text[match.start() + end:].strip():
            candidates.append(value)
    if not candidates:
        raise ValueError(f'no terminal JSON value: {path}')
    return candidates[-1]


def cold_record(path, cold_id, target, maximum):
    value = json.loads(path.read_text())
    record = value.get('record')
    if not isinstance(record, dict) or record.get('cold_id') != cold_id:
        raise ValueError('cold output ID/schema differs')
    for key in ('prompt_tokens', 'cached_tokens', 'completion_tokens', 'built_tokens'):
        if type(record.get(key)) is not int:
            raise ValueError(f'cold output missing integer {key}')
    if (record['cached_tokens'] != 0 or record['built_tokens'] != target
            or abs(record['prompt_tokens'] - target) >= 2000
            or not 0 < record['completion_tokens'] <= maximum
            or not finite_positive(record.get('ttft_s')) or not finite_positive(record.get('decode_tps'))
            or not isinstance(value.get('text'), str) or not value['text']):
        raise ValueError(f'invalid cold record: {record}')
    return record, value['text']


def trace_round_digests(path):
    """Map each original trace-list position to its recorded digest.

    ``agent_trace replay`` writes its ``round`` as the list index it replayed,
    while an authoritative trace may carry its own ``record.round`` values in
    reverse order.  Validate the latter as a complete immutable source set,
    but never use it as the replay join key.
    """
    document = json.loads(path.read_text())
    result = {}
    source_rounds = set()
    rounds = document.get('rounds')
    if not isinstance(rounds, list) or len(rounds) != 12:
        raise ValueError('trace must have exactly twelve records')
    for index, entry in enumerate(rounds):
        record = entry.get('record') if isinstance(entry, dict) else None
        if not isinstance(record, dict) or type(record.get('round')) is not int:
            raise ValueError('trace round schema missing')
        digest = record.get('messages_sha')
        if (not isinstance(digest, str) or not digest
                or record['round'] in source_rounds or digest in result):
            raise ValueError('trace digest missing or duplicate')
        result[index] = digest
        source_rounds.add(record['round'])
    if source_rounds != set(range(12)):
        raise ValueError('trace must have immutable rounds 0..11')
    return result


def replay_summary(path, trace, edited=False):
    value = json.loads(path.read_text())
    meta, rounds = value.get('meta'), value.get('rounds')
    if not isinstance(meta, dict) or not isinstance(rounds, list) or len(rounds) != 12:
        raise ValueError('replay must have meta and exactly twelve records')
    params = meta.get('params') or {}
    if params.get('max_tokens') != 200 or params.get('dry_run') is not False:
        raise ValueError('replay did not use live 200-token contract')
    expected = trace_round_digests(trace)
    digests, edited_digests, ttft, seen_rounds = [], [], [], set()
    for record in rounds:
        required = ('round', 'messages_sha', 'trace_messages_sha', 'dry_run', 'error', 'ttft_any_s', 'cached_tokens', 'edit_applied')
        if not isinstance(record, dict) or any(key not in record for key in required):
            raise ValueError('replay record fields missing')
        if (record['dry_run'] is not False or record['error'] is not None or not finite_positive(record['ttft_any_s'])
                or type(record['cached_tokens']) is not int or record['cached_tokens'] < 0):
            raise ValueError('replay contains dry/error/invalid TTFT record')
        digest, trace_digest, round_number = record['messages_sha'], record['trace_messages_sha'], record['round']
        if (not isinstance(digest, str) or not digest or not isinstance(trace_digest, str) or not trace_digest
                or type(round_number) is not int or round_number in seen_rounds or trace_digest != expected.get(round_number)):
            raise ValueError('replay input digest missing')
        if record['edit_applied']:
            if digest != trace_digest:
                edited_digests.append(digest)
        elif digest != trace_digest:
            raise ValueError('unmodified replay input digest differs from trace')
        seen_rounds.add(round_number)
        digests.append(digest)
        ttft.append(record['ttft_any_s'])
    if seen_rounds != set(expected):
        raise ValueError('replay round set differs from source trace')
    if edited and not edited_digests:
        raise ValueError('edit-at-idx 10 produced no edited input digest')
    if not edited and edited_digests:
        raise ValueError('unrequested replay edit was applied')
    return {'input_sha': digests, 'edited_input_sha': edited_digests,
            'sum_ttft_s': sum(ttft), 'mean_ttft_s': sum(ttft) / len(ttft), 'max_ttft_s': max(ttft),
            'cached_tokens': sum(record['cached_tokens'] for record in rounds)}


def quality_summary(directory):
    paths = list(directory.glob('quality_results_*.jsonl'))
    if len(paths) != 1:
        raise ValueError('expected one benchmark quality JSONL artifact')
    rows = read_jsonl(paths[0])
    if len(rows) != 60:
        raise ValueError(f'quality benchmark requires 60 rows, got {len(rows)}')

    question_ids = set()
    model_ids = set()
    statuses = {'PASS': 0, 'FAIL': 0}
    categories = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('quality row must be an object')
        question_id = row.get('question_id')
        model_id = row.get('model_id')
        category = row.get('category')
        passed = row.get('passed')
        if not isinstance(question_id, str) or not question_id:
            raise ValueError('quality row missing question_id')
        if question_id in question_ids:
            raise ValueError(f'duplicate quality question_id: {question_id!r}')
        if not isinstance(model_id, str) or not model_id:
            raise ValueError('quality row missing model_id')
        if not isinstance(category, str) or not category:
            raise ValueError('quality row missing category')
        if type(passed) is not bool:
            raise ValueError('quality row passed must be a boolean')

        question_ids.add(question_id)
        model_ids.add(model_id)
        outcome = 'PASS' if passed else 'FAIL'
        statuses[outcome] += 1
        category_counts = categories.setdefault(category, {'PASS': 0, 'FAIL': 0})
        category_counts[outcome] += 1

    if len(model_ids) != 1:
        raise ValueError('quality rows must have one model_id')
    passed = statuses['PASS']
    return {'path': paths[0].name, 'total': len(rows), 'model_id': next(iter(model_ids)),
            'statuses': statuses, 'categories': categories, 'pass_rate': passed / len(rows)}


def soak_summary(directory):
    summary_path, requests_path = directory / 'soak_summary.json', directory / 'soak_requests.jsonl'
    summary = json.loads(summary_path.read_text())
    rows = read_jsonl(requests_path)
    failed = sum(row.get('status') != 'SUCCESS' for row in rows)
    if (summary.get('target_duration_s') != 1800 or summary.get('total_requests') != len(rows)
            or summary.get('failed_requests') != failed):
        raise ValueError('soak artifacts do not agree')
    return {'total_requests': len(rows), 'successful_requests': summary.get('successful_requests'),
            'errors': failed, 'actual_duration_s': summary.get('actual_duration_s')}


class ProductionRunner(CardRunner):
    def command(self, argv, arm, env, label, timeout, optional=False):
        log = arm / f'{label}.log'
        with log.open('x') as out:
            completed = subprocess.run(argv, env=env, cwd=WT, stdout=out, stderr=subprocess.STDOUT,
                                       timeout=timeout, check=False)
        if completed.returncode and not optional:
            raise RuntimeError(f'{label} rc={completed.returncode}')
        return completed.returncode, log

    def cold(self, arm, env, label, target, maximum, cold_id=None):
        cold_id = cold_id or f'{self.options.rid}-{label}'
        out = arm / f'{label}.json'
        self.command([PY, str(SCR / 'cold_eq.py'), cold_id, str(out), str(target), str(maximum)], arm, env, label, 1800)
        return cold_record(out, cold_id, target, maximum)

    def require_affinity(self):
        actual = set(os.sched_getaffinity(self.proc.pid))
        if actual != AFFINITY:
            raise RuntimeError(f'GATE-FAIL-TASKSET actual={sorted(actual)}')

    def require_configuration(self, arm, window):
        parsed = self.parser(str(arm / 'serve.log'))
        expected = validate_configuration(parsed, window)
        write_new(arm / 'args_preprobe_checked.json', expected)

    def p1(self):
        with self.service('P1', window=49152, launch=LAUNCH) as (arm, env):
            self.require_affinity()
            self.require_configuration(arm, 49152)
            values = {'first_shot': self.cold(arm, env, 'first-P1', 32052, 128)[0]}
            values['cold32k'] = [self.cold(arm, env, label, 32052, 128)[0] for label in ('s1a', 's1b')]
            values['short'] = self.cold(arm, env, 'short', 2000, 512)[0]
            det, det_text = self.cold(arm, env, 's5A', 32052, 128, cold_id='s5A')
            history = json.loads(HIST_S5A.read_text())
            old = history.get('record')
            old_input = tuple(old.get(key) for key in ('cold_id', 'built_tokens', 'prompt_tokens', 'cached_tokens')) if isinstance(old, dict) else None
            new_input = tuple(det.get(key) for key in ('cold_id', 'built_tokens', 'prompt_tokens', 'cached_tokens'))
            if old_input != new_input or det_text != history.get('text'):
                raise ValueError('DET BIT_EXACT_MATCH failed')
            write_new(arm / 'det_result.json', {'status': 'BIT_EXACT_MATCH', 'input': new_input,
                      'text_sha256': hashlib.sha256(det_text.encode()).hexdigest()})
            self.command([PY, str(SCR / 'conc_gap_test.py')], arm, env, 'stall_conc_gap', 1800)
            values['conc_gap'] = last_json(arm / 'stall_conc_gap.log')
            replay_specs = (('agent_coldfirst', TRACE_REV, False), ('agent_warm', TRACE, False), ('agent_edit', TRACE, True))
            values['agent'] = {}
            replay_env = dict(env, FT_REPLAY_MAX_TOKENS='200')
            for label, trace, edited in replay_specs:
                argv = [PY, str(SCR / 'agent_trace.py'), 'replay', '--trace', str(trace), '--out', str(arm / f'{label}.json'), '--fresh-note', f'{self.options.rid}-{label}']
                if edited:
                    argv += ['--edit-at-idx', '10']
                self.command(argv, arm, replay_env, label, 3600)
                values['agent'][label] = replay_summary(arm / f'{label}.json', trace, edited=edited)
            # D06 is a delivery dependency, not inferred from a file appearing on disk.
            values['two_decode'] = {'status': 'pending', 'dependency': 'D06 not admitted'}
            evaluator = SHARED / 'evaluator.py'
            values['evaluator_sha256'] = hashlib.sha256(evaluator.read_bytes()).hexdigest()
            quality_dir, soak_dir = arm / 'quality60', arm / 'soak'
            quality_dir.mkdir(); soak_dir.mkdir()
            quality_rc, _ = self.command([PY, str(SHARED / 'benchmark_client.py'), 'phase3', 'Qwen3.8-Flash-Next-NVFP4', str(SHARED / 'test_prompts_60.json')], arm, dict(env, FT_RUN_DIR=str(quality_dir)), 'quality60', 7200, optional=True)
            values['quality60'] = {'returncode': quality_rc}
            if quality_rc == 0:
                values['quality60'].update(quality_summary(quality_dir))
            soak_rc, _ = self.command([PY, str(SHARED / 'stability_soak_30m.py')], arm, dict(env, FT_RUN_DIR=str(soak_dir), SOAK_DURATION_SEC='1800'), 'soak', 2400, optional=True)
            values['soak'] = {'returncode': soak_rc}
            if soak_rc == 0:
                values['soak'].update(soak_summary(soak_dir))
                values['soak']['usable_number_gate'] = values['soak']['errors'] == 0
            write_new(arm / 'measurements.json', values)
        return arm

    def p2(self):
        with self.service('P2', window=73728, launch=LAUNCH) as (arm, env):
            self.require_affinity()
            self.require_configuration(arm, 73728)
            values = {'first_shot': self.cold(arm, env, 'first-P2', 32052, 128)[0],
                      'cold64k': [self.cold(arm, env, label, 65400, 128)[0] for label in ('k64a', 'k64b')],
                      'cold32k': [self.cold(arm, env, label, 32052, 128)[0] for label in ('k32a', 'k32b')]}
            write_new(arm / 'measurements.json', values)
        return arm

    def p1_binding(self, admitted):
        if not assigned_round(self.options.rid, 'P2'):
            raise ValueError('P2 must use the assigned E2-R009-p64k identity')
        parent_rid = ASSIGNED_RIDS['P1']
        parent = ROUNDS / parent_rid
        required = ('admission.json', 'measurement_summary.json', 't08_runner.py', 'e2_runtime.py')
        if not parent.is_dir() or any(not (parent / name).is_file() for name in required) or not (parent / 'P1/measurements.json').is_file():
            raise ValueError('P2 requires P1 result and source archive')
        parent_admission = json.loads((parent / 'admission.json').read_text())
        summary = json.loads((parent / 'measurement_summary.json').read_text())
        if (parent_admission.get('rid') != parent_rid or parent_admission.get('card') != 'T08'
                or parent_admission.get('commit') != admitted['commit'] or parent_admission.get('code_version') != admitted['code_version']
                or summary.get('phase') != 'P1' or summary.get('proposed_verdict') != 'measured'):
            raise ValueError('P1 admission/result is not compatible with P2')
        statuses = [json.loads(path.read_text()) for path in parent.glob('status_batch*.json')]
        if (len(statuses) != 1 or statuses[0].get('rid') != parent_rid or statuses[0].get('gate') != 'T08'
                or statuses[0].get('state') != 'complete_measurements_pending_review'):
            raise ValueError('P1 does not have one terminal completed measurement status')
        files = [parent / name for name in required] + [parent / 'P1/measurements.json']
        return {'parent_rid': parent_rid, 'parent_files_sha256': {path.relative_to(parent).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}}

    def execute(self):
        if hashlib.md5((SCR / 'cold_eq.py').read_bytes()).hexdigest() != TOOL_MD5['cold_eq.py']:
            raise ValueError('original cold probe differs')
        artifacts = (SCR / 'cold_eq.py', SCR / 'conc_gap_test.py', SCR / 'agent_trace.py',
                     SHARED / 'benchmark_client.py', SHARED / 'stability_soak_30m.py',
                     SHARED / 'evaluator.py', TRACE, TRACE_REV, HIST_S5A)
        hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in artifacts}
        with self.round_scope() as admitted:
            if admitted is None:
                print('T08 PREFLIGHT PASS', flush=True)
                return
            write_new(self.directory / 'probes_sha256.json', hashes)
            if self.options.phase == 'P2':
                write_new(self.directory / 'parent_p1_binding.json', self.p1_binding(admitted))
            arm = self.p1() if self.options.phase == 'P1' else self.p2()
            write_new(self.directory / 'measurement_summary.json', {'phase': self.options.phase, 'arm': arm.name,
                      'proposed_verdict': 'measured', 'code_version': admitted['code_version']})
            self.set_status(state='complete_measurements_pending_review')
            print('T08 MEASUREMENTS COMPLETE; independent closure remains pending', flush=True)


def self_test():
    assert assigned_round('E2-R009', 'P1') and assigned_round('E2-R009-p64k', 'P2')
    for rid in ('E2-R004', 'E2-R004-p64k', 'E2-R011', 'E2-R011-p64k', 'E2-R009-p64k'):
        assert not assigned_round(rid, 'P1')
    for rid in ('E2-R004-p64k', 'E2-R011-p64k', 'E2-R009'):
        assert not assigned_round(rid, 'P2')
    assert AFFINITY == {1, *range(3, 48)}
    # This is the ServerArgs rendering produced by --max-prefill-length 4096:
    # args.py declares its destination as max_extend_tokens.
    actual_parsed = {'prefill_layer_major': 'True', 'max_extend_tokens': '4096',
                     'special_token_ckpt': 'True', 'max_seq_len_override': '49152'}
    assert validate_configuration(actual_parsed, 49152) == actual_parsed
    for key, value in (('max_extend_tokens', '8192'), ('max_extend_tokens', None)):
        bad = dict(actual_parsed)
        if value is None:
            del bad[key]
        else:
            bad[key] = value
        try:
            validate_configuration(bad, 49152)
        except ValueError:
            pass
        else:
            raise AssertionError('wrong/missing actual max_extend_tokens accepted')
    p2 = dict(actual_parsed, max_seq_len_override='73728')
    assert validate_configuration(p2, 73728) == expected_configuration(73728)
    with __import__('tempfile').TemporaryDirectory() as temporary:
        root = Path(temporary)
        trace = root / 'trace.json'
        # The remote trace_rev preserves per-record source rounds but reverses
        # trace-list order.  Replay uses the list index, not record.round.
        trace.write_text(json.dumps({'rounds': [
            {'record': {'round': 11 - i, 'messages_sha': f'{i:016x}'}}
            for i in range(12)]}))
        replay = {'meta': {'params': {'max_tokens': 200, 'dry_run': False}}, 'rounds': [
            {'round': i, 'messages_sha': f'{i:016x}', 'trace_messages_sha': f'{i:016x}', 'dry_run': False, 'error': None,
             'ttft_any_s': 1.0, 'cached_tokens': 0, 'edit_applied': False} for i in reversed(range(12))]}
        path = root / 'replay.json'; path.write_text(json.dumps(replay))
        assert replay_summary(path, trace)['mean_ttft_s'] == 1.0
        replay['rounds'][0]['dry_run'] = True; path.write_text(json.dumps(replay))
        try:
            replay_summary(path, trace)
        except ValueError:
            pass
        else:
            raise AssertionError('dry replay accepted')
        replay['rounds'][0]['dry_run'] = False; replay['rounds'][0]['trace_messages_sha'] = 'wrong'; path.write_text(json.dumps(replay))
        try:
            replay_summary(path, trace)
        except ValueError:
            pass
        else:
            raise AssertionError('wrong trace replay accepted')
        replay['rounds'][0]['trace_messages_sha'] = replay['rounds'][0]['messages_sha']
        replay['rounds'][0]['round'], replay['rounds'][1]['round'] = replay['rounds'][1]['round'], replay['rounds'][0]['round']
        path.write_text(json.dumps(replay))
        try:
            replay_summary(path, trace)
        except ValueError:
            pass
        else:
            raise AssertionError('wrong trace-list replay index accepted')
        soak = root / 'soak'; soak.mkdir()
        (soak / 'soak_requests.jsonl').write_text('{"status":"SUCCESS"}\n{"status":"HTTP_500"}\n')
        (soak / 'soak_summary.json').write_text(json.dumps({'target_duration_s': 1800, 'total_requests': 2, 'successful_requests': 1, 'failed_requests': 1, 'actual_duration_s': 1800.0}))
        assert soak_summary(soak)['errors'] == 1
        quality = root / 'quality'; quality.mkdir()
        quality_path = quality / 'quality_results_model.jsonl'

        def write_quality_rows(rows):
            quality_path.write_text(''.join(json.dumps(row) + '\n' for row in rows))

        valid_quality = [
            {'model_id': 'model', 'question_id': f'question-{index}',
             'category': 'alpha' if index < 30 else 'beta', 'passed': index < 38}
            for index in range(60)
        ]
        write_quality_rows(valid_quality)
        quality_result = quality_summary(quality)
        assert quality_result['statuses'] == {'PASS': 38, 'FAIL': 22}
        assert quality_result['categories']['alpha'] == {'PASS': 30, 'FAIL': 0}
        assert quality_result['categories']['beta'] == {'PASS': 8, 'FAIL': 22}
        for bad_row, reason in (({'passed': True}, 'missing quality fields'),
                                ({**valid_quality[0], 'passed': 'true'}, 'non-boolean passed')):
            broken_quality = list(valid_quality)
            broken_quality[0] = bad_row
            write_quality_rows(broken_quality)
            try:
                quality_summary(quality)
            except ValueError:
                pass
            else:
                raise AssertionError(f'{reason} accepted')
        parent = root / 'E2-R009'; (parent / 'P1').mkdir(parents=True)
        (parent / 'admission.json').write_text(json.dumps({'rid': 'E2-R009', 'card': 'T08', 'commit': 'commit', 'code_version': 'tag'}))
        (parent / 'measurement_summary.json').write_text(json.dumps({'phase': 'P1', 'proposed_verdict': 'measured'}))
        (parent / 'P1/measurements.json').write_text('{}')
        (parent / 't08_runner.py').write_text('source'); (parent / 'e2_runtime.py').write_text('runtime')
        (parent / 'status_batch1.json').write_text(json.dumps({'rid': 'E2-R009', 'gate': 'T08', 'state': 'complete_measurements_pending_review'}))
        runner = object.__new__(ProductionRunner); runner.options = SimpleNamespace(rid='E2-R009-p64k')
        with patch(__name__ + '.ROUNDS', root):
            assert runner.p1_binding({'commit': 'commit', 'code_version': 'tag'})['parent_rid'] == 'E2-R009'
            for wrong in ('E2-R004-p64k', 'E2-R011-p64k'):
                runner.options.rid = wrong
                try:
                    runner.p1_binding({'commit': 'commit', 'code_version': 'tag'})
                except ValueError:
                    pass
                else:
                    raise AssertionError('unassigned P2 identity accepted')
            runner.options.rid = 'E2-R009-p64k'
            (parent / 'status_batch1.json').write_text(json.dumps({'state': 'failed'}))
            try:
                runner.p1_binding({'commit': 'commit', 'code_version': 'tag'})
            except ValueError:
                pass
            else:
                raise AssertionError('incomplete P1 accepted')
    print('T08 SELFTEST PASS: affinity, source-bound replay/P1, quality boolean schema, and soak rejection')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rid')
    parser.add_argument('--batch', type=int)
    parser.add_argument('--phase', choices=('P1', 'P2'))
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    options = parser.parse_args()
    if options.self_test:
        self_test(); return
    if sys.platform != 'linux' or options.batch is None or not assigned_round(options.rid, options.phase):
        parser.error('Linux host, assigned phase-specific E2-R ID, and batch are required')
    options.gate, options.runner_file = 'T08', __file__
    runner = ProductionRunner(options)
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda signum, frame: (_ for _ in ()).throw(InterruptedError(f'signal {signum}')))
    runner.execute()


if __name__ == '__main__':
    main()
