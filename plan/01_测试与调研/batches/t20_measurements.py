"""T20 measurement components; the enclosing batch owns admission and service.

Importing this module does not launch processes or connect to a service.
It is not a standalone launcher. The full measurement function composes the
existing D16 collectors; formal startup and independent acceptance stay outside.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import shlex
import subprocess
import statistics
import time

from t08_runner import quality_summary, replay_summary
from t00_runner import classify_tax, finite_positive, validate_cold
from t16_runner import FT, LOCK, MODEL, PY, ROOT, ROUNDS, SCR, command, events, rows, write_new

SHARED = Path('/data2/_shared')
SOURCE_HASHES = {
    SHARED / 'evaluator.py': '39f10fa8ddab2c1b076862eb827d903be945243bb2e2422ec448e8560646e330',
    SHARED / 'benchmark_client.py': 'bebedf0b74ab234620d7206d8da58b72565f78c7407f56a2055f98dd3e5bc62a',
    SHARED / 'test_prompts_60.json': 'bde77ab02bb11539f6ee69861dc441ea3670ed6796d4d27226af1f89f74f9cad',
    SCR / 'agent_trace.py': '423feeb37bead3cacd2b066dc142a00cfb814f713ee1fcd766a456f64ce2cf17',
    SCR / 'probe_ft_cold32k.py': 'b97190f589f7383972f0799ec0855bfd76e0f0b928e13ebc3696644d970de88b',
    SCR / 'ft_perf_decomp.py': '949a18a521c8243cdd42d1deed0ab12544bc16e8e076b0dbb1251ac3dfb872cd',
    SCR / 'ft_probe_ckpt_tax.py': 'a67471a9d123c0c183f34d65066b86a35ce80e0832bc02f4ecfccc09b8c0a0c0',
    SHARED / 'runs/ft_rounds/E1-R003-v2/trace.json': '055ea005aadcbda32625f585a01f10e63d46cd1b87a88be769ec19144d68f899',
    SHARED / 'runs/ft_rounds/E1-R003-v2/trace_rev.json': '097b7a039e730d356985f47bc9fd747c86f4658fc6b89f1dec3243c0771b5e24',
    SHARED / 'runs/ft_rounds/E2-R009-regrade/E2-R009.regraded.jsonl': 'dd66f3d0ad5f32a1638c70bf92f37063e8087dc181ebf0e24849bc2cf6a8e5e6',
    SHARED / 'runs/ft_rounds/E2-R009/P1/agent_coldfirst.json': '4d6ff73440f469e96c950c6bc348f92f3a5f7cb402bd6ab443c13ec633993768',
    SHARED / 'runs/ft_rounds/E2-R009/P1/agent_warm.json': '79bab0c338ba44da6f0984861ac80589e941918c124bc8661654cd6e87c877d7',
    SHARED / 'runs/ft_rounds/E2-R009/P1/agent_edit.json': '2fee8f8aeae9b58be326821c1212ba35441a2e499aec94c0709b5a9b86649f8d',
    SHARED / 'runs/ft_rounds/E2-R000/PRODUCTION/prod32-0.json': 'b7277d58de0df84cd4141bfa33c60bad5d92e3aae638e56262aeef85c7d1b519',
    SHARED / 'runs/ft_rounds/E2-R000/PRODUCTION/prod32-1.json': 'f354bab3c2080c98bc364cc1f1343c2e73f6e0cb7a3018608bbe9835dcfbb0eb',
    SHARED / 'runs/ft_rounds/E2-R000/PRODUCTION/prod32-2.json': '994b3c269e684d8027a46a9b27487a4cb6f0c71233a8c5293ce773bb377f48f1',
    SHARED / 'runs/ft_rounds/E2-R000/PRODUCTION/prod32-3.json': 'a899564350b8e8851c434cc02ced60129a16677522107e0d89042bf6c33ea073',
    SHARED / 'runs/ft_rounds/E2-R000/PRODUCTION/prod64-0.json': 'f7523b5f1f266ea362a7eb267c337d6809ee4580c3c0d47f8a4b1427f7132cb3',
    SHARED / 'runs/ft_rounds/E2-R000/PRODUCTION/prod64-1.json': 'ac7fc8bea0f2f31d479742f279777bf8f5c6bd8b89e143b3112f9e1297404692',
    SHARED / 'runs/ft_rounds/E2-R000/PRODUCTION/short.jsonl': 'e7f47db9a454984ba6b62b6d6084f37a5d3007cd43ffb2c5ef47c33ec1305c3e',
    SHARED / 'runs/ft_rounds/E2-R009/P1/s1a.json': 'e011e4f6b9848c71e3b03ee5aa9714422ee8051a2d4a4b2bb2a3f0f8e0530c55',
    SHARED / 'runs/ft_rounds/E2-R009/P1/s1b.json': 'db835ab3dfd007bd94e3b7fe5f2897f2fa21f5e6412590ca6e3ec14fded91d04',
}


def verify_sources():
    for path, expected in SOURCE_HASHES.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f'T20 measurement source differs: {path}')
    return {str(path): digest for path, digest in SOURCE_HASHES.items()}


@contextmanager
def production_service(runner, name, *, candidate_commit, checkpoint=True):
    """Service scope used after the full batch's formal admission and lock take.

    Reuses the common Runner's preflight/readiness/owned cleanup. This is not an
    admission function: the outer batch must verify the accepted T17/T16 proofs.
    """
    if (runner.options.rid != 'E2-R040' or runner.options.gate != 'T20'
            or not runner.options.run or runner.directory != ROUNDS / 'E2-R040'
            or runner.proc is not None):
        raise ValueError('T20 service requires its actual running batch scope')
    if (not runner.token or not LOCK.exists()
            or LOCK.read_text() != runner.token or LOCK.stat().st_ino != runner.lock_inode):
        raise RuntimeError('T20 service requires the enclosing batch owned GPU lock')
    lock = json.loads(runner.token)
    if lock.get('owner') != 'E2-R040' or lock.get('pid') != os.getpid() or lock.get('card') != 'T20':
        raise RuntimeError('T20 lock identity differs from the actual caller')
    if type(checkpoint) is not bool or len(candidate_commit) != 40:
        raise ValueError('full candidate commit and boolean checkpoint setting required')
    wt = ROOT / 'wt/e2base1-ordinary-rewind'
    source = runner.gate(wt, candidate_commit)
    tag = command(['git', '-C', str(wt), 'describe', '--tags', '--exact-match'])
    if tag != 'E2-base.1@' + candidate_commit[:8]:
        raise ValueError('T20 requires the exact admitted candidate tag')
    gpu = command(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'])
    if not gpu or any(int(value) > 100 for value in gpu.splitlines()):
        raise RuntimeError('T20 requires all GPUs <=100 MiB before each service')
    verify_sources()
    arm = runner.directory / name
    if arm.parent != runner.directory or arm.name in ('', '.', '..'):
        raise ValueError('T20 arm must be a direct child of its round')
    arm.mkdir(exist_ok=False)
    env = runner.environment(wt, arm, False)
    for key in list(env):
        if key.startswith(('FT_T17_', 'FT_D16_', 'FT_DEV_', 'FT_D3_', 'FT_D0_')):
            env.pop(key)
    env['CUDA_VISIBLE_DEVICES'] = '0'
    argv = ['taskset', '-c', '1,3-47', FT, 'serve', '--model-path',
            str(ROOT / 'models/Qwen3.8-Flash-Next-NVFP4-overlay'),
            '--served-model-name', MODEL, '--host', '0.0.0.0', '--port', '8095',
            '--memory-ratio', '0.88', '--moe-cache-auto', '--moe-prefill-hit-d2d',
            '--ple-backend', 'pinned', '--moe-strategy', 'offload',
            '--quant-backend', 'moe.nvfp4=triton', '--max-running-requests', '2',
            '--cuda-graph-max-bs', '2', '--kv-reserve-tokens', '73728',
            '--max-seq-len-override', '73728', '--max-prefill-length', '4096',
            '--enable-cache-report', '--tool-call-parser', 'qwen3_coder',
            '--reasoning-parser', 'qwen3', '--prefill-layer-major']
    if checkpoint:
        argv.append('--enable-special-token-ckpt')
    selected = ('PYTHONPATH', 'PYTHONUNBUFFERED', 'VIRTUAL_ENV', 'PATH',
                'LD_LIBRARY_PATH', 'CUDA_VISIBLE_DEVICES')
    (arm / 'SERVE_CMD.txt').write_text('env ' + ' '.join(
        key + '=' + shlex.quote(env[key]) for key in selected) + ' ' + shlex.join(argv) + '\n')
    write_new(arm / 'source.json', {'commit': candidate_commit, 'code_version': tag,
                                  'import': source, 'checkpoint': checkpoint})
    write_new(arm / 'compiled_extensions.json', runner.compiled_extensions(wt))
    with (arm / 'serve.log').open('x') as log:
        runner.proc = subprocess.Popen(argv, env=env, cwd=wt, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
        try:
            runner.set_status(state='loading', arm=name, service_pid=runner.proc.pid)
            if os.getpgid(runner.proc.pid) != runner.proc.pid or os.getsid(runner.proc.pid) != runner.proc.pid:
                raise RuntimeError('T20 service process-group ownership differs')
            runner.ready(arm)
            parsed = runner.parser(str(arm / 'serve.log'))
            expected = {'prefill_layer_major': 'True', 'max_extend_tokens': '4096',
                        'special_token_ckpt': str(checkpoint), 'max_seq_len_override': '73728',
                        'kv_reserve_tokens': '73728', 'max_running_req': '2',
                        'cuda_graph_max_bs': '2', 'memory_ratio': '0.88',
                        'moe_cache_auto': 'True', 'moe_prefill_hit_d2d': 'True',
                        'moe_strategy': repr('offload'), 'ple_backend': repr('pinned'),
                        'quant_backend': repr('moe.nvfp4=triton'),
                        '_unique_suffix': repr('.pid=' + str(runner.proc.pid))}
            for key, value in expected.items():
                if parsed.get(key) != value:
                    raise ValueError(f'T20 production argument differs: {key}')
            affinity = sorted(os.sched_getaffinity(runner.proc.pid))
            if set(affinity) != {1, *range(3, 48)}:
                raise ValueError('T20 production CPU affinity differs')
            write_new(arm / 'args_preprobe_checked.json', expected)
            write_new(arm / 'affinity.json', {'actual': affinity})
            runner.set_status(state='probing', arm=name, service_pid=runner.proc.pid)
            yield arm, env, wt
            if runner.proc.poll() is not None:
                raise RuntimeError('T20 service exited before live verification')
            if list(arm.glob('d0*')) or any(token in (arm / 'serve.log').read_text() for token in
                    ('GDN bank:', 'D0 seg:', 'D0 prefill', 'D0 instrumentation enabled')):
                raise RuntimeError('T20 production D0 diagnostic leakage')
        finally:
            runner.stop()


def run_performance(*, arm, env, wt, rid, service, mode):
    """Measure one existing production service, or one independent tax process.

    The outer batch launches production once and tax OFF/ON three times each.
    This component never launches a model service or acquires a GPU lock.
    """
    if rid != 'E2-R040' or mode not in ('production', 'tax'):
        raise ValueError('invalid T20 performance identity or mode')
    arm, wt = Path(arm), Path(wt)
    sources = verify_sources()

    def run(argv, label):
        verify_sources()
        if service is None or service.poll() is not None:
            raise RuntimeError('T20 owned service is not live')
        output = arm / f'{label}.stdout'
        with output.open('x') as stdout, (arm / f'{label}.stderr').open('x') as stderr:
            # Each performance client finishes within the 30-minute stop bound.
            subprocess.run(argv, env=dict(env, PYTHONUNBUFFERED='1'), cwd=wt,
                           stdout=stdout, stderr=stderr, check=True, timeout=1800)
        if service.poll() is not None:
            raise RuntimeError('T20 service exited during performance measurement')
        return output

    def cold(label, target):
        cold_id = f'{rid}-{arm.name}-{label}'
        raw = ROOT / 'runs/cold32k_20261002' / f'{cold_id}.json'
        if raw.exists():
            raise ValueError('T20 cold probe output already exists; do not overwrite')
        start = len(events(arm / 'serve.log'))
        output = run([PY, str(SCR / 'probe_ft_cold32k.py'), cold_id,
                      str(target), '128', 'nothink'], label)
        value = json.loads(output.read_text())
        record = validate_cold(value, cold_id, target)
        raw_bytes = raw.read_bytes()
        if value['diag']['out_path'] != str(raw) or json.loads(raw_bytes) != record:
            raise ValueError('T20 original probe stdout/raw disagree')
        with (arm / f'{label}.json').open('xb') as copied:
            copied.write(raw_bytes)
        digest = hashlib.sha256(raw_bytes).hexdigest()
        if hashlib.sha256((arm / f'{label}.json').read_bytes()).hexdigest() != digest:
            raise ValueError('T20 copied cold probe digest differs')
        write_new(arm / f'{label}.source.json', {'path': str(raw),
                  'source_sha256': digest, 'destination_sha256': digest})
        end = len(events(arm / 'serve.log'))
        if end <= start:
            raise ValueError('T20 cold probe has no new prefill event')
        write_new(arm / f'{label}.prefill_range.json', {'start': start, 'end': end})
        return record

    if mode == 'production':
        cold32 = [cold(f'prod32-{i}', 32052) for i in range(4)]
        run([PY, str(SCR / 'ft_perf_decomp.py'), 'run', '--fixture', 'short',
             '--repeat', '3', '--out', str(arm / 'short.jsonl')], 'short')
        short = rows(arm / 'short.jsonl')
        if len(short) != 3 or any(not r['expect_ok'] or r['prompt_tokens'] != 23
                or r['cached_tokens'] != 0 or not r['completion_text']
                or not finite_positive(r['decode_tps']) or not finite_positive(r['ttft_s'])
                for r in short):
            raise ValueError('T20 historical short fixture invalid')
        result = {'cold32': cold32, 'first_shot': cold32[0], 'short': short,
                  'cold64': [cold(f'prod64-{i}', 65412) for i in range(2)]}
        historical_arm = SHARED / 'runs/ft_rounds/E2-R000/PRODUCTION'
        old32_paths = [historical_arm / f'prod32-{i}.json' for i in range(4)]
        old64_paths = [historical_arm / f'prod64-{i}.json' for i in range(2)]
        old_short_path = historical_arm / 'short.jsonl'
        old32 = [json.loads(path.read_text()) for path in old32_paths]
        old64 = [json.loads(path.read_text()) for path in old64_paths]
        old_short = rows(old_short_path)
        r009_paths = [SHARED / 'runs/ft_rounds/E2-R009/P1' / f'{label}.json'
                      for label in ('s1a', 's1b')]
        r009 = [json.loads(path.read_text())['record'] for path in r009_paths]
        if len(old_short) != 3:
            raise ValueError('T20 retained short baseline requires three samples')
        comparisons = []
        for reference, label, metric, measured, retained, paths in (
                ('T00', 'cold32', 'ttft_s', cold32[1:], old32[1:], old32_paths[1:]),
                ('T00', 'cold32', 'decode_tps', cold32[1:], old32[1:], old32_paths[1:]),
                ('T00', 'short', 'decode_tps', short, old_short, [old_short_path]),
                ('T00', 'cold64', 'ttft_s', result['cold64'], old64, old64_paths),
                ('T00', 'cold64', 'decode_tps', result['cold64'], old64, old64_paths),
                ('E2-R009', 'cold32', 'ttft_s', cold32[1:], r009, r009_paths),
                ('E2-R009', 'cold32', 'decode_tps', cold32[1:], r009, r009_paths)):
            if not all(finite_positive(row.get(metric)) for row in measured + retained):
                raise ValueError('T20 performance comparison contains non-positive/non-finite data')
            current_median = statistics.median(row[metric] for row in measured)
            historical_median = statistics.median(row[metric] for row in retained)
            contract = ('prompt_tokens', 'completion_tokens', 'cached_tokens')
            current_load = {tuple(row.get(key) for key in contract) for row in measured}
            historical_load = {tuple(row.get(key) for key in contract) for row in retained}
            same_load = current_load == historical_load
            relative = (current_median - historical_median) / historical_median
            within = abs(relative) <= .07 or math.isclose(abs(relative), .07, rel_tol=0, abs_tol=1e-12)
            comparisons.append({'reference': reference, 'workload': label, 'metric': metric,
                                'current_values': [row[metric] for row in measured],
                                'historical_values': [row[metric] for row in retained],
                                'current_median': current_median, 'historical_median': historical_median,
                                'relative_delta': relative, 'absolute_relative_delta': abs(relative),
                                'limit': .07, 'same_token_load': same_load,
                                'current_token_load': sorted(current_load),
                                'historical_token_load': sorted(historical_load),
                                'within_7_percent': within if same_load else None,
                                'source_sha256': {str(path): sources[str(path)] for path in paths},
                                'configuration_note': 'T00 window=73728; E2-R009 window=49152; '
                                                      'cross-round observation, not a controlled experiment'})
        result['historical_comparison'] = {
            'metrics': comparisons, 'first_shot_excluded_from_cold32_medians': True,
            'historical_first_shot': old32[0],
            'historical_first_shot_sha256': sources[str(old32_paths[0])],
            'oom_review_pending': True, 'admitted': False}
    else:
        run([PY, str(SCR / 'ft_probe_ckpt_tax.py'), str(arm / 'tax.json'),
             f'{rid}-{arm.name}'], 'tax')
        result = {'tax': classify_tax(json.loads((arm / 'tax.json').read_text()))}
    result.update(source_sha256=sources, admitted=False)
    write_new(arm / 'performance_measurements.json', result)
    return result


def run_baseline_measurements(runner, *, candidate_commit):
    """T20 items 1-4 and 6-7; D16 item 5 remains the outer batch's obligation."""
    result = {'admitted': False, 'd16_suite': 'not_run'}
    with production_service(runner, 'PRODUCTION', candidate_commit=candidate_commit) as (arm, env, wt):
        args = dict(arm=arm, env=env, wt=wt, rid='E2-R040', service=runner.proc)
        result['production'] = run_performance(**args, mode='production')
        result['quality_replays'] = run_quality_and_replays(**args)
    result['tax'] = {}
    for checkpoint, prefix in ((False, 'OFF'), (True, 'ON')):
        for index in range(1, 4):
            name = f'{prefix}_p{index}'
            with production_service(runner, name, candidate_commit=candidate_commit,
                                    checkpoint=checkpoint) as (arm, env, wt):
                result['tax'][name] = run_performance(
                    arm=arm, env=env, wt=wt, rid='E2-R040', service=runner.proc, mode='tax')
    write_new(runner.directory / 'baseline_measurements.json', result)
    return result


def run_full_measurements(runner, *, candidate_commit, realinputs, d16_wrapper,
                          d16_source_review, d16_source_review_sha256):
    """Finish actual T20 under the continuation runner's still-owned lock."""
    import d16_native_process_collection as native
    from equiv_suite.native_workloads import read_native_workloads
    if runner.options.rid != 'E2-R040' or runner.options.gate != 'T20' or not runner.options.run:
        raise ValueError('full T20 measurements require the actual running batch')
    native.verify_source_review(d16_wrapper, d16_source_review, d16_source_review_sha256)
    # Use bounded slices of the already sealed target-tokenizer inputs. Four
    # long full queries would exceed the native arm's 49,152-token KV capacity.
    chosen = []
    seen = set()
    for case in realinputs['cases']:
        ids = case['query'][-512:]
        if len(ids) != 512 or tuple(ids) in seen:
            continue
        seen.add(tuple(ids))
        chosen.append({'source_case': case['name'], 'source_input_ids_sha256': case['input_ids_sha256'],
                       'slice_start': len(case['query'])-512, 'slice_end': len(case['query']), 'input_ids': ids})
        if len(chosen) == 4:
            break
    if len(chosen) != 4:
        raise ValueError('T20 needs four distinct real-token content slices')
    long = next((case for case in realinputs['cases'] if 4096 < len(case['query']) <= 16384), None)
    if long is None:
        raise ValueError('T20 needs an existing bounded long-prefill real input')
    write_new(runner.directory/'d16_input_provenance.json', {'short': chosen,
        'long_source_case': long['name'], 'long_input_ids_sha256': long['input_ids_sha256'], 'admitted': False})
    result = {'schema': 'ft_t20_full_measurements/v1', 'admitted': False,
              'baseline': run_baseline_measurements(runner, candidate_commit=candidate_commit), 'd16': {}}
    common = dict(wrapper=d16_wrapper, source_review=d16_source_review,
                  source_review_sha256=d16_source_review_sha256)
    def envelope(label, inputs, slots, interleave=False):
        collection = native.collect_native_processes(runner, inputs, slots=slots, interleave=interleave, **common)
        reading = read_native_workloads(collection['root'], evidence_map=Path(collection['evidence_map']).name,
            evidence_map_sha256=collection['evidence_map_sha256'], slots=slots)
        write_new(Path(collection['root'])/'producer_measurement.json', reading)
        if reading.get('verdict') not in ('measurements_pass_pending_independent_review', 'batch_envelope_diagnostic'):
            raise RuntimeError('T20 ' + label + ' native measurements are unverified: ' + str(reading.get('reason')))
        return {'collection': collection, 'producer_measurement': reading, 'independent_review_pending': True}
    ids = [item['input_ids'] for item in chosen]
    result['d16']['batch2'] = envelope('batch2', ids[:2], 2)
    result['d16']['batch4'] = envelope('batch4', ids, 4)
    result['d16']['parking'] = native.collect_parking_processes(runner, ids[0], **common)
    result['d16']['cache'] = native.collect_cache_processes(runner, ids[0], **common)
    # The two freshly restarted cache-cold controls also cover S-cold stability.
    result['d16']['cold'] = {'source': 'native_cache/cold_0,cold_1',
                            'measurement_scope': 'two_fresh_cold_exact_id_controls', 'admitted': False}
    result['d16']['interleave'] = envelope('interleave', [ids[0], long['query']], 2, interleave=True)
    result['all_sections_measured'] = True
    result['independent_review_pending'] = True
    write_new(runner.directory/'full_t20_measurements.json', result)
    return result


def run_quality_and_replays(*, arm, env, wt, rid, service):
    """Called only inside the admitted batch's owned, live production service."""
    if rid != 'E2-R040':
        raise ValueError('T20 measurements require assigned E2-R040 identity')
    if service is None or service.poll() is not None:
        raise RuntimeError('T20 owned service is not live')
    sources = verify_sources()
    arm, wt = Path(arm), Path(wt)

    def command(argv, label, request_env, timeout):
        verify_sources()
        if service.poll() is not None:
            raise RuntimeError('T20 service exited before measurement')
        log_path = arm / f'{label}.log'
        with log_path.open('x') as log:
            proc = subprocess.Popen(argv, env=dict(request_env, PYTHONUNBUFFERED='1'),
                                    cwd=wt, stdout=log, stderr=subprocess.STDOUT,
                                    start_new_session=True)
            started = last_output = time.monotonic()
            previous_size = 0
            try:
                while proc.poll() is None:
                    now = time.monotonic()
                    size = log_path.stat().st_size
                    if size != previous_size:
                        previous_size, last_output = size, now
                    if service.poll() is not None:
                        raise RuntimeError('T20 service exited during measurement')
                    if now - last_output >= 1800:
                        raise TimeoutError(f'T20 {label}: 30 minutes without output')
                    if now - started >= timeout:
                        raise subprocess.TimeoutExpired(argv, timeout)
                    time.sleep(1)
                if proc.returncode:
                    raise subprocess.CalledProcessError(proc.returncode, argv)
            finally:
                if proc.poll() is None:
                    # Only the child launched above owns this process group.
                    # The service belongs to the enclosing batch and is separate.
                    try:
                        os.killpg(proc.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(proc.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        proc.wait(timeout=10)
        if service.poll() is not None:
            raise RuntimeError('T20 service exited during measurement')

    quality_dir = arm / 'quality60'
    quality_dir.mkdir(exist_ok=False)
    command([PY, str(SHARED / 'benchmark_client.py'), 'phase3',
             'Qwen3.8-Flash-Next-NVFP4', str(SHARED / 'test_prompts_60.json')],
            'quality60', dict(env, FT_RUN_DIR=str(quality_dir)), 7200)
    quality = quality_summary(quality_dir)
    records = [json.loads(line) for line in next(quality_dir.glob('quality_results_*.jsonl')).read_text().splitlines() if line.strip()]
    for record in records:
        for field, path in (('evaluator_sha256', SHARED / 'evaluator.py'),
                            ('benchmark_client_sha256', SHARED / 'benchmark_client.py'),
                            ('corpus_sha256', SHARED / 'test_prompts_60.json')):
            if record.get(field) != sources[str(path)]:
                raise ValueError(f'T20 quality row source binding differs: {field}')
        if record.get('graded_status') == 'RUNTIME_ERROR':
            raise RuntimeError('T20 quality request failed; cannot keep partial measurement')
    quality['max_tokens'] = 768  # Literal budget in the SHA-pinned phase3 client.
    # Compare the retained canonical regrade, rather than its original 38/60.
    history_path = SHARED / 'runs/ft_rounds/E2-R009-regrade/E2-R009.regraded.jsonl'
    historical = [json.loads(line) for line in history_path.read_text().splitlines() if line.strip()]
    corpus = {q['id']: q for q in json.loads((SHARED / 'test_prompts_60.json').read_text())}
    previous = {row['question_id']: row for row in historical}
    current = {row['question_id']: row for row in records}
    if (len(historical) != 60 or len(corpus) != 60 or len(previous) != 60
            or set(previous) != set(corpus) or set(current) != set(corpus)):
        raise ValueError('T20 quality comparison requires the same sixty distinct questions')
    comparison = []
    for question_id, question in corpus.items():
        before, after = previous[question_id], current[question_id]
        question_sha = hashlib.sha256((json.dumps(question, ensure_ascii=False, indent=2,
                                                  allow_nan=False) + '\n').encode()).hexdigest()
        if (before.get('evaluator_sha256') != sources[str(SHARED / 'evaluator.py')]
                or before.get('question_sha256') != question_sha
                or before.get('category') != question['category']
                or after.get('category') != question['category']
                or before.get('model_id') != after.get('model_id')):
            raise ValueError('T20 historical question/evaluator/load binding differs')
        old_status, new_status = before.get('status'), after.get('graded_status')
        if (old_status not in ('PASS', 'ANSWER_FAIL', 'TRUNCATED')
                or new_status not in ('PASS', 'ANSWER_FAIL', 'TRUNCATED')
                or before.get('passed') is not (old_status == 'PASS')
                or after.get('passed') is not (new_status == 'PASS')):
            raise ValueError('T20 quality canonical status and passed flag disagree')
        comparison.append({'question_id': question_id, 'category': question['category'],
                           'historical_status': old_status, 'current_status': new_status,
                           'status_changed': old_status != new_status,
                           'response_equal': before['response'] == after['response'],
                           'thinking_equal': before['thinking'] == after['thinking'],
                           'finish_reason_equal': before['finish_reason'] == after['finish_reason'],
                           # Category identifies candidates; it does not prove a cache hit.
                           'continuation_related_candidate': question['category'] == 'long_multiturn'})
    historical_passed = sum(row['status'] == 'PASS' for row in historical)
    if historical_passed != 47:
        raise ValueError('T20 historical canonical baseline is not the retained 47/60')
    quality['historical_comparison'] = {
        'source': str(history_path), 'source_sha256': sources[str(history_path)],
        'historical_passed': historical_passed, 'current_passed': quality['statuses']['PASS'],
        'total': 60, 'questions': comparison,
        'changed_questions': [row['question_id'] for row in comparison if row['status_changed']],
        'multiturn_questions': [row for row in comparison if row['continuation_related_candidate']],
        'cache_hit_proven': False, 'admitted': False}
    trace = SHARED / 'runs/ft_rounds/E1-R003-v2/trace.json'
    reverse = trace.with_name('trace_rev.json')
    agent = {}
    for label, source, edited in (('agent_coldfirst', reverse, False),
                                  ('agent_warm', trace, False),
                                  ('agent_edit', trace, True)):
        output = arm / f'{label}.json'
        argv = [PY, str(SCR / 'agent_trace.py'), 'replay', '--trace', str(source),
                '--out', str(output), '--fresh-note', f'{rid}-{label}']
        if edited:
            argv += ['--edit-at-idx', '10']
        command(argv, label, dict(env, FT_REPLAY_MAX_TOKENS='200'), 3600)
        agent[label] = replay_summary(output, source, edited=edited)
        historical_path = SHARED / 'runs/ft_rounds/E2-R009/P1' / f'{label}.json'
        # Reuse the existing replay/load checks for both retained and new data.
        replay_summary(historical_path, source, edited=edited)
        before = json.loads(historical_path.read_text())
        after = json.loads(output.read_text())
        old_params, new_params = before['meta']['params'], after['meta']['params']
        for key in ('model', 'thinking', 'thinking_mode', 'max_tokens', 'temperature',
                    'rounds', 'edit_at_idx'):
            if key not in old_params or key not in new_params or old_params[key] != new_params[key]:
                raise ValueError(f'T20 historical replay parameter differs: {key}')
        previous_rounds = {row['round']: row for row in before['rounds']}
        changes = []
        for new in after['rounds']:
            old = previous_rounds[new['round']]
            if (old['messages_sha'] != new['messages_sha']
                    or old['trace_messages_sha'] != new['trace_messages_sha']
                    or old['edit_applied'] != new['edit_applied']):
                raise ValueError('T20 historical replay request bytes differ')
            fields = {}
            for field in ('text', 'parts', 'content_parts', 'tool_calls'):
                left, right = old[field], new[field]
                if field in ('parts', 'content_parts'):
                    left, right = ''.join(left), ''.join(right)
                limit = min(len(left), len(right))
                fork = next((i for i in range(limit) if left[i] != right[i]),
                            limit if len(left) != len(right) else None)
                fields[field] = {'equal': left == right, 'first_difference_index': fork,
                                 'index_unit': 'tool_call_list_index' if field == 'tool_calls'
                                               else 'unicode_character',
                                 'historical_length': len(left), 'current_length': len(right)}
            changes.append({'round': new['round'], 'fields': fields,
                            'finish_reason_equal': old['finish_reason'] == new['finish_reason']})
        agent[label]['historical_comparison'] = {
            'source': str(historical_path), 'source_sha256': sources[str(historical_path)],
            'rounds': changes, 'admitted': False,
            'changed_rounds': [row['round'] for row in changes
                               if not row['finish_reason_equal']
                               or any(not value['equal'] for value in row['fields'].values())],
            'scope': 'retained decoded output comparison; no token-ID or kernel equivalence claim'}
    result = {'quality60': quality, 'agent': agent, 'agent_max_tokens': 200,
              'source_sha256': sources, 'admitted': False}
    write_new(arm / 'quality_replay_measurements.json', result)
    return result
