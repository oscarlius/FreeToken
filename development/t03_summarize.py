"""Summarize live T03 evidence without changing probes or formal verdicts."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import statistics
import sys

ARMS = ('A_cut_on_p1', 'B_cut_off_p1', 'A_cut_on_p2', 'B_cut_off_p2', 'A_cut_on_p3', 'B_cut_off_p3')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def admitted_identity(admission, rid, trace):
    if (admission.get('rid') != rid or admission.get('card') != 'T03' or admission.get('trace') != str(trace)
            or admission.get('commit') != '23f2e2caa3395837c9474735ffc83321f3b9b5a1'
            or admission.get('code_version') != 'E2-base@23f2e2c'):
        raise ValueError('T03 admission rid/card/source/full commit/tag identity differs')


def proposed(results, reasons, cache_regressions):
    for side in ('A', 'B'):
        for key, count in (('snapshot_counts', 3), ('cold_segments', 3), ('cold_ttft_s', 3), ('hot_ttft_s', 12)):
            if len(results[key][side]) != count:
                raise ValueError(f'T03 requires exactly {count} {key} observations for {side}')
        if len(reasons[side]) != 3:
            raise ValueError('T03 requires three actual cold reason lists per side')
    a, b = results['snapshot_counts']['A'], results['snapshot_counts']['B']
    if cache_regressions or any(right < left for left, right in zip(a, b)):
        return 'not_met'
    delta = results['delta_cold_s']
    b_single = results['cold_segments']['B'] == [1, 1, 1]
    if abs(delta) <= .5 or (b_single and statistics.mean(results['cold_ttft_s']['B']) >= 5):
        return 'rejected'
    if (2 <= delta <= 3.5 and abs(results['delta_hot_s']) <= .15
            and results['cold_segments']['A'] == [2, 2, 2] and b_single
            and all(value.count('anchor_cap') == 1 for value in reasons['A'])
            and all(value.count('anchor_cap') == 0 for value in reasons['B'])):
        return 'kept'
    return 'pending_review'


def summarize(directory, batch):
    archives = [directory / name for name in ('runner.py', 'e2_runtime.py', 't16_runner.py')]
    if any(not path.is_file() for path in archives):
        raise ValueError('actual runner and interpreter dependencies must be archived')
    sys.path.insert(0, str(directory))
    specification = importlib.util.spec_from_file_location('ft_t03_archived_runner', archives[0])
    runner = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = runner
    specification.loader.exec_module(runner)
    for name in ('e2_runtime', 't16_runner'):
        if Path(sys.modules[name].__file__).resolve().parent != directory.resolve():
            raise ValueError(f'interpreter dependency is not the archived source: {name}')
    if directory.name not in {'E2-R001', 'E2-R008'}:
        raise ValueError('T03 requires leader-assigned E2-R001 or retry E2-R008')
    status = read(directory / f'status_batch{batch}.json')
    if (status.get('batch') != batch or status.get('gate') != 'T03' or status.get('rid') != directory.name
            or status.get('state') != 'complete_measurements_pending_review'):
        raise ValueError('T03 exact batch is not complete pending review')
    admission = read(directory / 'admission.json')
    commit = admission.get('commit')
    if (not isinstance(commit, str) or not re.fullmatch(r'[0-9a-f]{40}', commit)
            or commit != '23f2e2caa3395837c9474735ffc83321f3b9b5a1'
            or admission.get('code_version') != 'E2-base@23f2e2c' or tuple(runner.ARMS) != ARMS):
        raise ValueError('T03 admitted full baseline or exact six-arm identity differs')
    trace = runner.TRACE
    admitted_identity(admission, directory.name, trace)
    if sha(trace) != admission['trace_sha256']:
        raise ValueError('original trace no longer matches admitted source')
    expected = runner.trace_round_digests(trace)
    if admission.get('trace_round_digests') != {str(key): value for key, value in expected.items()}:
        raise ValueError('admitted digest map differs from the immutable trace')
    results = {key: {'A': [], 'B': []} for key in ('cold_ttft_s', 'hot_ttft_s', 'single_cold_ttft_s',
                'single_hot_ttft_s', 'cold_segments', 'snapshot_counts', 't1_mean_1_11_s', 't1_max_1_11_s')}
    reasons, warm_cache, first_shots, evidence = {'A': [], 'B': []}, {}, {}, {}
    for name in runner.ARMS:
        arm = directory / name
        if not (arm / 'tax.log').is_file() or not (arm / 'tax.log').stat().st_size:
            raise ValueError(f'actual probe transcript is missing: {name}')
        label = name[0]
        tax = runner.classify_tax(read(arm / 'tax.json'))
        if tax != read(arm / 'tax_classification.json'):
            raise ValueError(f'tax classification differs from raw: {name}')
        markers = read(arm / 'markers.json')
        telemetry = runner.validate_d0(arm, markers['P0'], markers['P1'], markers['P2'])
        if telemetry != read(arm / 'tax_metadata.json'):
            raise ValueError(f'tax segment metadata differs from live log: {name}')
        cold_rid = str(telemetry['tax_multi']['cold_rid'])
        segments = telemetry['tax_multi']['by_rid'][cold_rid]
        reasons[label].append([row['seg_reason'] for row in segments])
        results['cold_segments'][label].append(len(segments))
        results['cold_ttft_s'][label].append(tax['cold']['multi'])
        results['hot_ttft_s'][label].extend(tax['hot']['multi'])
        results['single_cold_ttft_s'][label].append(tax['cold']['single'])
        results['single_hot_ttft_s'][label].extend(tax['hot']['single'])
        count = runner.snapshot_count(arm)
        if read(arm / 'snapshot_count.json')['actual_successful_snapshots'] != count:
            raise ValueError(f'snapshot count differs from actual log: {name}')
        results['snapshot_counts'][label].append(count)
        replay_files = [arm / 'T1_replay.json', arm / 'T1_replay_pass2.json']
        maps = [runner.replay_by_sha(path, expected) for path in replay_files]
        if maps[0] != maps[1]:
            raise ValueError('two passes have different immutable inputs')
        replay_rows = [{row['round']: row for row in read(path)['rounds']} for path in replay_files]
        warm = replay_rows[1]
        warm_cache[name] = {str(number): warm[number]['cached_tokens'] for number in range(12)}
        ttfts = [warm[number]['ttft_any_s'] for number in range(1, 12)]
        results['t1_mean_1_11_s'][label].append(statistics.mean(ttfts))
        results['t1_max_1_11_s'][label].append(max(ttfts))
        first_shots[name] = replay_rows[0][0]
        evidence[name] = {path.name: sha(path) for path in arm.iterdir() if path.is_file()}
    regressions = []
    for number in range(1, 4):
        a, b = f'A_cut_on_p{number}', f'B_cut_off_p{number}'
        for row in range(12):
            if warm_cache[b][str(row)] < warm_cache[a][str(row)]:
                regressions.append({'pair': number, 'round': row,
                                    'A': warm_cache[a][str(row)], 'B': warm_cache[b][str(row)]})
    results['delta_cold_s'] = statistics.mean(results['cold_ttft_s']['A']) - statistics.mean(results['cold_ttft_s']['B'])
    results['delta_hot_s'] = statistics.mean(results['hot_ttft_s']['A']) - statistics.mean(results['hot_ttft_s']['B'])
    results['warm_cached_tokens'] = warm_cache
    baseline = directory.parent / 'E2-R000'
    baseline_files = [baseline / 'baseline_acceptance.json'] + [baseline / f'{side}_p{n}/tax.json'
                      for n in range(1, 4) for side in ('OFF', 'ON')]
    baseline_tax = {path.parent.name: runner.classify_tax(read(path)) for path in baseline_files[1:]}
    summary = {'schema': 't03_summary/v1', 'round_id': directory.name, 'results': results,
               'cold_seg_reasons': reasons, 'cache_regressions': regressions,
               'first_shots': first_shots, 'proposed_verdict': proposed(results, reasons, regressions),
               'snapshot_positive_coverage': any(results['snapshot_counts']['A'] + results['snapshot_counts']['B']),
               'baseline_checkpoint_tax': baseline_tax,
               'baseline_sha256': {str(path): sha(path) for path in baseline_files},
               'evidence_sha256': evidence, 'interpretation_sha256': {path.name: sha(path) for path in archives},
               'units': {'ttft_s': 's', 'snapshot_counts': 'actual successful copies'},
               'verdict': 'pending_review'}
    created = min((directory / name / 'ENV.txt').read_text().splitlines()[0] for name in runner.ARMS)
    metadata = {'schema': 'ft_round/v2', 'round_id': directory.name, 'epoch': 2, 'card': 'T03',
                'created_at': created, 'parent': 'E2-R000',
                'base': {'commit': admission['commit'], 'code_version': admission['code_version']},
                'serve': {'arms': {name: {'serve_cmd': f'{name}/SERVE_CMD.txt', 'serve_log': f'{name}/serve.log',
                           'serve_args': f'{name}/serve_args.txt', 'env': f'{name}/ENV.txt'} for name in runner.ARMS}},
                'results': results, 'first_shots': first_shots, 'verdict': 'pending_review',
                'proposed_verdict': None, 'verdict_history': [], 'retractions': []}
    return summary, metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--round', type=Path)
    parser.add_argument('--batch', type=int)
    parser.add_argument('--summary-out', type=Path)
    parser.add_argument('--metadata-out', type=Path)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        admission = {'rid': 'E2-R001', 'card': 'T03', 'trace': str(Path('/trace.json')),
                     'commit': '23f2e2caa3395837c9474735ffc83321f3b9b5a1', 'code_version': 'E2-base@23f2e2c'}
        admitted_identity(admission, 'E2-R001', Path('/trace.json'))
        for key, value in (('rid', 'E2-R002'), ('card', 'T04'), ('trace', '/wrong.json')):
            try:
                admitted_identity({**admission, key: value}, 'E2-R001', Path('/trace.json'))
            except ValueError:
                pass
            else:
                raise AssertionError(f'admission {key} mismatch accepted')
        result = {'snapshot_counts': {'A': [0] * 3, 'B': [0] * 3}, 'delta_cold_s': 2.8,
                  'delta_hot_s': .05, 'cold_segments': {'A': [2] * 3, 'B': [1] * 3},
                  'cold_ttft_s': {'A': [5.8] * 3, 'B': [3.0] * 3},
                  'hot_ttft_s': {'A': [3.05] * 12, 'B': [3.0] * 12}}
        reasons = {'A': [['anchor_cap', 'layer_major_whole']] * 3, 'B': [['layer_major_whole']] * 3}
        assert proposed(result, reasons, []) == 'kept'
        assert proposed(result, reasons, [{'pair': 1}]) == 'not_met'
        result['delta_cold_s'] = .1
        assert proposed(result, reasons, []) == 'rejected'
        result['snapshot_counts']['B'] = [0, 0]
        try:
            proposed(result, reasons, [])
        except ValueError:
            pass
        else:
            raise AssertionError('truncated snapshot pairs accepted')
        print('T03 SUMMARIZE SELFTEST PASS: card thresholds and cache regression priority')
        return
    if any(value is None for value in (args.round, args.batch, args.summary_out, args.metadata_out)):
        parser.error('round, batch and two new output paths are required')
    if args.summary_out.exists() or args.metadata_out.exists():
        parser.error('output paths already exist')
    summary, metadata = summarize(args.round, args.batch)
    # Serialize both before opening either output.
    payloads = [(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
                for path, value in ((args.summary_out, summary), (args.metadata_out, metadata))]
    for path, value in payloads:
        with path.open('x', encoding='utf-8') as stream:
            stream.write(value)


if __name__ == '__main__':
    main()
