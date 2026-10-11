"""Read-only T00 measurement summarizer; writes only explicitly new JSON outputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import statistics


REASONS = {'anchor_cap', 'token_budget', 'layer_major_whole', 'continuation', 'other'}
EXPECTED_ARMS = ('PRODUCTION', 'D0', 'OFF_p1', 'ON_p1', 'OFF_p2', 'ON_p2', 'OFF_p3', 'ON_p3')
PREFILL_EVENT = re.compile(r'#new-seq: (\d+), #new-token: (\d+), #cached-token: (\d+)')


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text())


def write_exclusive(path, value):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')


def median(values):
    if not values or not all(finite(value) for value in values):
        raise ValueError('missing/non-finite measurement')
    return statistics.median(values)


def cold_record(arm, label, target):
    raw_path, stdout_path, source_path = arm / f'{label}.json', arm / f'{label}.stdout.json', arm / f'{label}.source.json'
    if not all(path.is_file() for path in (raw_path, stdout_path, source_path)):
        raise ValueError(f'missing raw/stdout/source cold proof: {label}')
    record, stdout, source = read_json(raw_path), read_json(stdout_path), read_json(source_path)
    if not isinstance(record, dict) or stdout.get('record') != record or not isinstance(stdout.get('diag'), dict):
        raise ValueError(f'cold raw/stdout record disagreement: {label}')
    diagnostic = stdout['diag']
    raw_sha = sha(raw_path)
    if source.get('destination_sha256') != raw_sha or source.get('source_sha256') != raw_sha:
        raise ValueError(f'cold source digest does not bind raw copy: {label}')
    original = Path(source.get('path', ''))
    if not original.is_file() or sha(original) != raw_sha:
        raise ValueError(f'cold original source is absent/different: {label}')
    if (record.get('cold_id') != 'e2r000-' + label or record.get('cached_tokens') != 0
            or type(record.get('prompt_tokens')) is not int or abs(record['prompt_tokens'] - target) >= 2000
            or type(record.get('completion_tokens')) is not int or not 1 < record['completion_tokens'] <= 128
            or not all(finite(record.get(key)) and record[key] > 0 for key in ('ttft_s', 'decode_tps'))
            or diagnostic.get('built_tokens') != target or diagnostic.get('enable_thinking') is not False
            or type(diagnostic.get('content_events')) is not int or diagnostic['content_events'] < 2
            or diagnostic.get('cache_ok') is not True or diagnostic.get('prompt_len_ok') is not True
            or diagnostic.get('decode_ok') is not True):
        raise ValueError(f'invalid cold sample: {label}')
    return record


def source_evidence(arm):
    names = ('SERVE_CMD.txt', 'ENV.txt', 'serve.log', 'measurements.json')
    paths = [arm / name for name in names if (arm / name).is_file()]
    paths += sorted(arm.glob('*.source.json')) + sorted(arm.glob('*.stdout.json'))
    paths += sorted(arm.glob('*.prefill_range.json')) + sorted(arm.glob('*.json'))
    unique = {path.relative_to(arm).as_posix(): sha(path) for path in paths}
    return unique


def compare(metric, current, historical):
    values = historical.get('values') if historical else None
    if not values:
        return {'status': 'not_met', 'reason': 'historical artifact unavailable', 'historical_sources': []}
    prior = median(values)
    relative = abs(current - prior) / prior
    return {'status': 'pass' if relative <= .07 else 'not_met', 'historical_median': prior,
            'absolute_delta': current - prior, 'relative_absolute_delta': relative,
            'limit': .07, 'historical_sources': historical['sources'], 'historical_sha256': historical['sha256']}


def prefill_events(arm):
    values = [tuple(map(int, match)) for match in PREFILL_EVENT.findall((arm / 'serve.log').read_text())]
    if not values:
        raise ValueError('D0 serve log has no prefill events')
    return values


def validate_d0_rows(arm):
    rows = [read_json_line(line) for line in (arm / 'd0_prefill.jsonl').read_text().splitlines() if line]
    events = prefill_events(arm)
    if not rows or len(rows) != len(events):
        raise ValueError('missing D0 telemetry')
    for index, (row, expected) in enumerate(zip(rows, events)):
        reqs = row.get('reqs')
        actual = (len(reqs) if isinstance(reqs, list) else -1,
                  sum(request.get('new_tokens', -1) for request in reqs) if isinstance(reqs, list) else -1,
                  sum(request.get('cached_tokens', -1) for request in reqs) if isinstance(reqs, list) else -1)
        if (row.get('chunk') != index or actual != expected or row.get('seg_reason') not in REASONS or not isinstance(reqs, list) or not reqs
                or not all(type(row.get(key)) is int and row[key] >= 0 for key in ('h2d_bytes', 'd2d_bytes'))
                or not all(finite(row.get(key)) for key in ('t_start', 't_end')) or row['t_end'] < row['t_start']):
            raise ValueError(f'invalid D0 row {index}')
        for request in reqs:
            if (set(('rid', 'new_tokens', 'cached_tokens')) - request.keys() or type(request['rid']) is not int or type(request['new_tokens']) is not int
                    or type(request['cached_tokens']) is not int or request['new_tokens'] < 0 or request['cached_tokens'] < 0):
                raise ValueError(f'invalid D0 request row {index}')
    return rows


def prefill_rows(arm, label, rows):
    range_doc = read_json(arm / f'{label}.prefill_range.json')
    start, end = range_doc.get('start'), range_doc.get('end')
    if type(start) is not int or type(end) is not int or not 0 <= start < end:
        raise ValueError(f'invalid prefill range: {label}')
    if end > len(rows):
        raise ValueError(f'prefill range exceeds telemetry: {label}')
    selected = rows[start:end]
    rids = {request['rid'] for row in selected for request in row['reqs']}
    if len(rids) != 1:
        raise ValueError(f'D0 cold range must contain one actual request: {label}')
    return {'start': start, 'end': end, 'h2d_bytes': sum(row['h2d_bytes'] for row in selected),
            'd2d_bytes': sum(row['d2d_bytes'] for row in selected),
            'seg_reasons': [row['seg_reason'] for row in selected], 'rids': list(rids),
            'new_tokens': sum(request['new_tokens'] for row in selected for request in row['reqs']),
            'cached_tokens': sum(request['cached_tokens'] for row in selected for request in row['reqs'])}


def read_json_line(line):
    return json.loads(line)


def historical_metrics(history_root):
    """Read only the declared primary E1 artifacts; probe64k.jsonl is excluded."""
    result = {}
    paths = {}
    for label in ('k32A', 'k32B', 'k64A', 'k64B'):
        path = history_root / 'E1-R001-64k' / f'{label}.json'
        if not path.is_file():
            return {}
        paths[path.as_posix()] = sha(path)
    records = {label: read_json(history_root / 'E1-R001-64k' / f'{label}.json').get('record') for label in ('k32A', 'k32B', 'k64A', 'k64B')}
    if not all(isinstance(record, dict) for record in records.values()):
        return {}
    group_paths = [history_root / '_e1/E1-R001/groupA.jsonl', history_root / '_e1/E1-R001/groupB.jsonl']
    if not all(path.is_file() for path in group_paths):
        return {}
    paths.update({path.as_posix(): sha(path) for path in group_paths})
    short = []
    for path in group_paths:
        short += [row for row in (read_json_line(line) for line in path.read_text().splitlines() if line)
                  if isinstance(row.get('label'), str) and row['label'].startswith('short')]
    if len(short) != 4:
        return {}
    def metric(values):
        if not all(finite(value) for value in values):
            return None
        return {'values': values, 'sources': list(paths), 'sha256': paths}
    return {'cold32_ttft_s': metric([records['k32A'].get('ttft_s'), records['k32B'].get('ttft_s')]),
            'cold32_decode_tps': metric([records['k32A'].get('decode_tps'), records['k32B'].get('decode_tps')]),
            'cold64_ttft_s': metric([records['k64A'].get('ttft_s'), records['k64B'].get('ttft_s')]),
            'cold64_decode_tps': metric([records['k64A'].get('decode_tps'), records['k64B'].get('decode_tps')]),
            'short_decode_tps': metric([row.get('decode_tps') for row in short])}


def tax_arm(arm):
    value = read_json(arm / 'tax.json')
    if value.get('reps') != 5:
        raise ValueError(f'tax reps != 5: {arm}')
    result = {}
    for kind in ('single', 'multi'):
        values = value.get(kind)
        if not isinstance(values, list) or len(values) != 5 or not all(finite(item) and item > 0 for item in values):
            raise ValueError(f'invalid tax {kind}: {arm}')
        result[kind] = {'cold_index0': values[0], 'hot_indices1to4': values[1:]}
    return result


def require_completion_arms(arms):
    if arms != list(EXPECTED_ARMS):
        raise ValueError('T00 completion arms are not exactly the eight required arms in card order')
    return EXPECTED_ARMS


def status_and_admission(round_dir):
    admissions = round_dir / 'admission.json'
    statuses = sorted(round_dir.glob('status_batch*.json'))
    complete = round_dir / 'measurements_complete.json'
    if not admissions.is_file() or len(statuses) != 1 or not complete.is_file():
        raise ValueError('missing T00 admission/status/completion artifact')
    admission, status, completion = read_json(admissions), read_json(statuses[0]), read_json(complete)
    if status.get('state') != 'complete_measurements_pending_review' or completion.get('state') != 'complete_measurements_pending_review':
        raise ValueError('T00 measurements are not complete pending review')
    expected = require_completion_arms(completion.get('arms'))
    required_arm_files = ('SERVE_CMD.txt', 'ENV.txt', 'serve.log', 'serve_args.txt', 'measurements.json')
    if any(not (round_dir / name).is_dir() or any(not (round_dir / name / file).is_file() for file in required_arm_files) for name in expected):
        raise ValueError('T00 completion arms are not exactly the eight required arms')
    return admission, status, completion


def validate_d0_cold_ranges(d0_rows, d0_cold):
    if (d0_rows[0]['start'] < 1 or d0_rows[0]['end'] > d0_rows[1]['start']
            or d0_rows[0]['rids'][0] == d0_rows[1]['rids'][0]
            or any(row['cached_tokens'] != 0 or row['new_tokens'] != record['prompt_tokens']
                   for row, record in zip(d0_rows, d0_cold))):
        raise ValueError('D0 cold ranges overlap, are reversed, or do not preserve a ready event')


def summarize(round_dir, history_root):
    admission, status, completion = status_and_admission(round_dir)
    production = round_dir / 'PRODUCTION'
    d0 = round_dir / 'D0'
    if not production.is_dir() or not d0.is_dir():
        raise ValueError('missing production/D0 arms')
    first = cold_record(production, 'prod32-0', 32052)
    cold32 = [cold_record(production, f'prod32-{index}', 32052) for index in range(4)]
    short_rows = [read_json_line(line) for line in (production / 'short.jsonl').read_text().splitlines() if line]
    if len(short_rows) != 3 or any(row.get('cached_tokens') != 0 or not finite(row.get('decode_tps')) for row in short_rows):
        raise ValueError('short fixture is incomplete/non-cold')
    cold64 = [cold_record(production, f'prod64-{index}', 65412) for index in range(2)]
    all_d0 = validate_d0_rows(d0)
    d0_rows = [prefill_rows(d0, f'd0-32-{index}', all_d0) for index in range(2)]
    d0_cold = [cold_record(d0, f'd0-32-{index}', 32052) for index in range(2)]
    validate_d0_cold_ranges(d0_rows, d0_cold)
    ready = all_d0[0]
    tax = {name: tax_arm(round_dir / name) for name in ('OFF_p1', 'OFF_p2', 'OFF_p3', 'ON_p1', 'ON_p2', 'ON_p3')}
    cold32_metrics = {'ttft_s': median([row['ttft_s'] for row in cold32[1:]]),
                      'decode_tps': median([row['decode_tps'] for row in cold32[1:]])}
    results = {
        'cold32_later3_median': cold32_metrics,
        'short_later3_median': {'decode_tps': median([row['decode_tps'] for row in short_rows])},
        'cold64_later2_median': {'ttft_s': median([row['ttft_s'] for row in cold64]),
                                  'decode_tps': median([row['decode_tps'] for row in cold64])},
    }
    telemetry = {
        'd0_cold32_ranges': d0_rows,
        'd0_ready_record': {'h2d_bytes': ready.get('h2d_bytes'), 'd2d_bytes': ready.get('d2d_bytes'),
                            'seg_reason': ready.get('seg_reason')},
        'checkpoint_tax': tax,
    }
    history = historical_metrics(history_root)
    comparisons = {
        'cold32_ttft_s': compare('cold32_ttft_s', cold32_metrics['ttft_s'], history.get('cold32_ttft_s')),
        'cold32_decode_tps': compare('cold32_decode_tps', cold32_metrics['decode_tps'], history.get('cold32_decode_tps')),
        'short_decode_tps': compare('short_decode_tps', results['short_later3_median']['decode_tps'], history.get('short_decode_tps')),
        'cold64_ttft_s': compare('cold64_ttft_s', results['cold64_later2_median']['ttft_s'], history.get('cold64_ttft_s')),
        'cold64_decode_tps': compare('cold64_decode_tps', results['cold64_later2_median']['decode_tps'], history.get('cold64_decode_tps')),
    }
    arms = [round_dir / name for name in EXPECTED_ARMS]
    return {'schema': 't00_summary/v1', 'round_id': round_dir.name,
            'units': {'ttft_s': 's', 'decode_tps': 'tokens/s', 'h2d_bytes': 'bytes', 'd2d_bytes': 'bytes'},
            'results': results, 'historical_comparison': comparisons,
            'first_shots': {'production_cold32': first},
            'inputs': {'cold32': cold32, 'short': short_rows, 'cold64': cold64}, 'telemetry': telemetry,
            'admission': admission, 'status': status, 'completion': completion,
            'evidence_sha256': {arm.name: source_evidence(arm) for arm in arms},
            'source_sha256': {path.name: sha(path) for path in (round_dir / 'admission.json', status_path(round_dir), round_dir / 'measurements_complete.json')},
            'verdict': 'pending_review', 'proposed_verdict': None}


def status_path(round_dir):
    return next(round_dir.glob('status_batch*.json'))


def initial_metadata(summary):
    admission = summary['admission']
    root = Path(summary['_round'])
    arms = EXPECTED_ARMS
    created = min((root / name / 'ENV.txt').read_text().splitlines()[0] for name in arms)
    return {'schema': 'ft_round/v2', 'round_id': summary['round_id'], 'epoch': 2, 'card': 'T00', 'created_at': created,
            'base': {'commit': admission.get('commit'), 'code_version': admission.get('code_version')},
            'serve': {'arms': {name: {'serve_cmd': f'{name}/SERVE_CMD.txt', 'serve_log': f'{name}/serve.log',
                                       'serve_args': f'{name}/serve_args.txt', 'env': f'{name}/ENV.txt'} for name in arms}},
            'results': summary['results'], 'first_shots': summary['first_shots'], 'verdict': 'pending_review',
            'proposed_verdict': None, 'verdict_history': [], 'retractions': []}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('round_dir', type=Path, nargs='?')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--metadata-out', type=Path)
    parser.add_argument('--history-root', type=Path, default=Path('/data2/_shared/runs/ft_rounds'))
    parser.add_argument('--self-test', action='store_true')
    options = parser.parse_args()
    if options.self_test:
        self_test(); return
    if options.round_dir is None or options.out is None:
        parser.error('round_dir and --out are required')
    if options.out.exists() or options.metadata_out and options.metadata_out.exists():
        parser.error('output paths must be new')
    summary = summarize(options.round_dir, options.history_root)
    if options.metadata_out:
        summary['_round'] = str(options.round_dir)
        metadata = initial_metadata(summary)
        del summary['_round']
    write_exclusive(options.out, summary)
    if options.metadata_out:
        write_exclusive(options.metadata_out, metadata)


def self_test():
    assert median([1, 3, 2]) == 2
    assert tax_arm_from_value({'reps': 5, 'single': [1, 2, 3, 4, 5], 'multi': [2, 3, 4, 5, 6]})['multi']['cold_index0'] == 2
    try:
        tax_arm_from_value({'reps': 5, 'single': [1] * 5, 'multi': [1] * 4})
    except ValueError:
        pass
    else:
        raise AssertionError('truncated hot tax accepted')
    comparison = compare('cold64_ttft_s', 20, {'values': [14.080, 12.426], 'sources': ['fixture'], 'sha256': {'fixture': 'x'}})
    assert comparison['status'] == 'not_met' and comparison['relative_absolute_delta'] > .07
    assert require_completion_arms(list(EXPECTED_ARMS)) == EXPECTED_ARMS
    try:
        require_completion_arms(list(EXPECTED_ARMS[:-1]) + ['OFF_p3'])
    except ValueError:
        pass
    else:
        raise AssertionError('duplicate completion arm accepted')
    with __import__('tempfile').TemporaryDirectory() as temporary:
        arm = Path(temporary) / 'arm'; arm.mkdir()
        record = {'cold_id': 'e2r000-case', 'cached_tokens': 0, 'prompt_tokens': 32000, 'completion_tokens': 128,
                  'ttft_s': 6.0, 'decode_tps': 38.0}
        original = arm / 'original.json'; original.write_text(json.dumps(record))
        (arm / 'case.json').write_text(json.dumps(record))
        digest = sha(original)
        (arm / 'case.stdout.json').write_text(json.dumps({'record': record, 'diag': {'built_tokens': 32052,
            'enable_thinking': False, 'content_events': 2, 'cache_ok': True, 'prompt_len_ok': True, 'decode_ok': True}}))
        (arm / 'case.source.json').write_text(json.dumps({'path': str(original), 'source_sha256': digest, 'destination_sha256': digest}))
        assert cold_record(arm, 'case', 32052)['cold_id'] == 'e2r000-case'
        try:
            cold_record(arm, 'case', 65412)
        except ValueError:
            pass
        else:
            raise AssertionError('wrong cold target accepted')
        (arm / 'case.source.json').write_text(json.dumps({'path': str(original), 'source_sha256': 'bad', 'destination_sha256': digest}))
        try:
            cold_record(arm, 'case', 32052)
        except ValueError:
            pass
        else:
            raise AssertionError('unbound raw cold record accepted')
        rows = [{'chunk': 0, 'h2d_bytes': 1, 'd2d_bytes': 0, 'seg_reason': 'other', 't_start': 0., 't_end': 1., 'reqs': [{'rid': 0, 'new_tokens': 1, 'cached_tokens': 0}]},
                {'chunk': 1, 'h2d_bytes': 2, 'd2d_bytes': 1, 'seg_reason': 'anchor_cap', 't_start': 1., 't_end': 2., 'reqs': [{'rid': 1, 'new_tokens': 10, 'cached_tokens': 0}]},
                {'chunk': 2, 'h2d_bytes': 3, 'd2d_bytes': 1, 'seg_reason': 'other', 't_start': 2., 't_end': 3., 'reqs': [{'rid': 2, 'new_tokens': 10, 'cached_tokens': 0}]}]
        (arm / 'd0_prefill.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
        (arm / 'serve.log').write_text(''.join(f'#new-seq: {len(row["reqs"])}, #new-token: {sum(q["new_tokens"] for q in row["reqs"])}, #cached-token: {sum(q["cached_tokens"] for q in row["reqs"])}\n' for row in rows))
        (arm / 'd0-32-0.prefill_range.json').write_text('{"start":1,"end":2}')
        assert prefill_rows(arm, 'd0-32-0', validate_d0_rows(arm))['h2d_bytes'] == 2
        ranges = [{'start': 1, 'end': 2, 'rids': [1], 'new_tokens': 10, 'cached_tokens': 0},
                  {'start': 2, 'end': 3, 'rids': [2], 'new_tokens': 10, 'cached_tokens': 0}]
        validate_d0_cold_ranges(ranges, [{'prompt_tokens': 10}, {'prompt_tokens': 10}])
        try:
            validate_d0_cold_ranges(list(reversed(ranges)), [{'prompt_tokens': 10}, {'prompt_tokens': 10}])
        except ValueError:
            pass
        else:
            raise AssertionError('reversed D0 ranges accepted')
        (arm / 'serve.log').write_text('#new-seq: 1, #new-token: 99, #cached-token: 0\n' * 3)
        try:
            validate_d0_rows(arm)
        except ValueError:
            pass
        else:
            raise AssertionError('D0 log mismatch accepted')
        (arm / 'serve.log').write_text(''.join(f'#new-seq: {len(row["reqs"])}, #new-token: {sum(q["new_tokens"] for q in row["reqs"])}, #cached-token: {sum(q["cached_tokens"] for q in row["reqs"])}\n' for row in rows))
        rows[1]['chunk'] = 9; (arm / 'd0_prefill.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
        try:
            validate_d0_rows(arm)
        except ValueError:
            pass
        else:
            raise AssertionError('invalid all-D0 schema accepted')
    print('T00 SUMMARIZE SELFTEST PASS: raw-proof, D0 alignment/ranges, exact arms, cold/hot tax, 7pct no-relaxation')


def tax_arm_from_value(value):
    """CPU-testable form of tax-arm parsing."""
    if value.get('reps') != 5:
        raise ValueError('checkpoint probe must contain five pairs')
    result = {}
    for kind in ('single', 'multi'):
        values = value.get(kind)
        if not isinstance(values, list) or len(values) != 5 or not all(finite(item) and item > 0 for item in values):
            raise ValueError('invalid checkpoint tax')
        result[kind] = {'cold_index0': values[0], 'hot_indices1to4': values[1:]}
    return result


if __name__ == '__main__':
    main()
