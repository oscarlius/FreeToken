#!/usr/bin/env python3
'''CPU-only admission record for rerunning T10 phase 1 on E2-base.1.'''
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

R017 = {
    'rid': 'E2-R017', 'batch': 44,
    'parent_commit': '23f2e2caa3395837c9474735ffc83321f3b9b5a1',
    'candidate_commit': 'c30ae0d7003c3bbbf56867ce74da797332fa7ed5',
    'round_sha256': 'f3198a83789480c6bf2e4a2d333f036a3a12e3fd055241e6a5e55c91d4660c37',
    'phase1_manifest_sha256': '31f1a9c190f2b529b8e4b2d2bc964af0b5cd5e084d4a16b05db797143c4df98e',
    'run_manifest_sha256': '10f57ef07f85c772e8d01063b47776fb2d4d8f84e9654ea5dca962f0bd257b94',
    'frontend_manifest_sha256': 'bf1f38901055e79e0b4ae48615f4ce1f58a4efc02a31f88ff644d857c6bc0356',
    'reverse_trace_sha256': '097b7a039e730d356985f47bc9fd747c86f4658fc6b89f1dec3243c0771b5e24',
    'forward_trace_sha256': '055ea005aadcbda32625f585a01f10e63d46cd1b87a88be769ec19144d68f899',
    'agent_trace_md5': 'f81acb79c3dbc89999f5f76de4c9a070',
    'runner_sha256': '13326d9ce238a5066a89cc35eb5bace1be08a9ab69767e432bd94582dfeac551',
    'logits_probe_sha256': '7ab4fd3a256c2fd3d510bd63d77b5181a648e5d8f8609ebf1a52b68f3a6c45e7',
}
ARMS = ('B1', 'B2', 'B3')
PHASES = ('cold', 'warm')
FLAGS = {'cuda_visible_devices': '0', 'mamba_host_slots': 0, 'max_extend_tokens': 4096,
         'prefill_layer_major': False, 'enable_cache_report': True, 'replay_max_tokens': 200,
         'model': 'Qwen3.8-Flash-Next-NVFP4', 'endpoint': 'http://127.0.0.1:8095/v1'}
TERMINAL_BINDING = {'prompt_ids', 'prompt_ids_sha256_int32le', 'generated_ids', 'uid', 'pid',
                    'pgid', 'http_finish_reason', 'engine_finish_reason'}


def _hex(value, size, name):
    if not isinstance(value, str) or re.fullmatch('[0-9a-f]{%d}' % size, value) is None:
        raise ValueError('%s has wrong digest shape' % name)


def proposal(e2_base_1_commit, frozen_bundle):
    '''Create a record with no launch, RID, batch, socket, or subprocess path.'''
    _hex(e2_base_1_commit, 40, 'E2-base.1 commit')
    if e2_base_1_commit == R017['candidate_commit']:
        raise ValueError('D14 replay cannot reuse the affected candidate')
    if not isinstance(frozen_bundle, dict) or not frozen_bundle:
        raise ValueError('frozen_bundle is required')
    for name, digest in frozen_bundle.items():
        if not isinstance(name, str) or not name.endswith(('.py', '.sh')):
            raise ValueError('bundle item must be a source file')
        _hex(digest, 64, 'bundle digest')
    return {
        'schema': 't10_d14_replay_admission/v1', 'execution': 'CPU-preparation-only',
        'source': {'code_version': 'E2-base.1', 'candidate_commit': e2_base_1_commit,
                   'replaces_candidate_commit': R017['candidate_commit'],
                   'frozen_bundle_sha256': dict(sorted(frozen_bundle.items()))},
        'parent_protocol': dict(R017), 'flags': dict(FLAGS),
        'inputs': {'canonical_rounds': 12, 'streams': {arm: list(PHASES) for arm in ARMS},
                   'terminal_records': 72, 'frontend_manifest_sha256': R017['frontend_manifest_sha256'],
                   'reverse_trace_sha256': R017['reverse_trace_sha256'],
                   'forward_trace_sha256': R017['forward_trace_sha256'],
                   'agent_trace_md5': R017['agent_trace_md5'],
                   'rule': 'copy sealed R017 raw traces and frontend prompt IDs byte-for-byte; never decode/re-encode'},
        'probes': {'terminal_binding': sorted(TERMINAL_BINDING),
                   'comparison': 'rederive each fork from all six streams; report cold/cold, warm/warm, cold/warm counts out of 36 and classify each fork by top-2 logit delta',
                   'phase2': 'for every actual fork, run two fresh prefix-warmed services and compare K=1 full FP32 logits'},
        'stop_conditions': ['E2-base.1 commit or frozen source SHA drifts',
                            'any prompt-ID row or trace binding differs from R017',
                            'arm parsed flags differ beyond PID',
                            'replay lacks an error-free non-dry 1..200-token terminal',
                            'terminal, semantic, process, or six-stream binding fails'],
    }


def validate(record):
    if record.get('schema') != 't10_d14_replay_admission/v1' or record.get('execution') != 'CPU-preparation-only':
        raise ValueError('wrong admission boundary')
    source = record.get('source')
    if not isinstance(source, dict) or source.get('code_version') != 'E2-base.1':
        raise ValueError('must name E2-base.1')
    _hex(source.get('candidate_commit'), 40, 'E2-base.1 commit')
    if source.get('candidate_commit') == R017['candidate_commit'] or source.get('replaces_candidate_commit') != R017['candidate_commit']:
        raise ValueError('affected source replacement is wrong')
    bundle = source.get('frozen_bundle_sha256')
    if not isinstance(bundle, dict) or not bundle:
        raise ValueError('missing frozen source bundle')
    for name, digest in bundle.items():
        if not isinstance(name, str) or not name.endswith(('.py', '.sh')):
            raise ValueError('invalid bundle filename')
        _hex(digest, 64, 'bundle digest')
    if record.get('parent_protocol') != R017:
        raise ValueError('wrong R017 parent identity')
    if record.get('flags') != FLAGS:
        raise ValueError('R017 flags drifted')
    inputs = record.get('inputs')
    if not isinstance(inputs, dict) or inputs.get('canonical_rounds') != 12 or inputs.get('terminal_records') != 72:
        raise ValueError('wrong input/terminal count')
    if inputs.get('streams') != {arm: list(PHASES) for arm in ARMS}:
        raise ValueError('B1/B2/B3 cold/warm streams missing')
    if (inputs.get('frontend_manifest_sha256') != R017['frontend_manifest_sha256']
            or inputs.get('reverse_trace_sha256') != R017['reverse_trace_sha256']
            or inputs.get('forward_trace_sha256') != R017['forward_trace_sha256']
            or inputs.get('agent_trace_md5') != R017['agent_trace_md5']):
        raise ValueError('raw input provenance drifted')
    probes = record.get('probes')
    if not isinstance(probes, dict) or set(probes.get('terminal_binding', ())) != TERMINAL_BINDING:
        raise ValueError('terminal binding is incomplete')
    comparison = probes.get('comparison', '')
    if not all(piece in comparison for piece in ('cold/cold', 'warm/warm', 'cold/warm', 'out of 36', 'top-2')):
        raise ValueError('comparison contract incomplete')
    if 'two fresh prefix-warmed services' not in probes.get('phase2', ''):
        raise ValueError('phase2 fresh-process proof missing')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--e2-base-1-commit')
    parser.add_argument('--bundle-json', type=Path)
    parser.add_argument('--validate', type=Path)
    args = parser.parse_args()
    if args.validate:
        validate(json.loads(args.validate.read_text(encoding='utf-8')))
        print('T10_D14_CPU_ADMISSION_VALID')
        return
    if not args.e2_base_1_commit or args.bundle_json is None:
        parser.error('--e2-base-1-commit and --bundle-json are required')
    result = proposal(args.e2_base_1_commit, json.loads(args.bundle_json.read_text(encoding='utf-8')))
    validate(result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
