#!/usr/bin/env python3
"""T04 phase-2 D03 logits measurement; explicit --run only.

Consumes an immutable terminal-token record from the D03 boundary request.  It
never writes into the sealed E2-R002 phase-1 round.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import shlex
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path('/data2/FreeToken')
ROUND_ROOT = Path('/data2/_shared/runs/ft_rounds')
CANDIDATE = ROOT / 'wt/e1r003st'
G4_PROMPT_LENGTH = 21976
EXPECTED_RID = 'E2-R014'
PARENT_COMMIT = '23f2e2caa3395837c9474735ffc83321f3b9b5a1'
PY = str(ROOT / 'venv/bin/python')
FT = str(ROOT / 'venv/bin/ft')
MODEL = 'Qwen3.8-Flash-Next-NVFP4'
PORT = 8095


def load_selfcheck():
    """Load the uploaded D03 lifecycle implementation without copying its guards."""
    path = ROOT / 'runs/dev_D03/d03_gpu_selfcheck.py'
    spec = importlib.util.spec_from_file_location('d03_selfcheck_runtime', path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot load D03 selfcheck module: {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: object) -> None:
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')


def ids_digest(ids: list[int]) -> str:
    import struct
    return hashlib.sha256(struct.pack(f'<{len(ids)}i', *ids)).hexdigest()


def valid_ids(value: object, label: str) -> list[int]:
    if not isinstance(value, list) or not value or any(type(x) is not int or not 0 <= x <= 2**31 - 1 for x in value):
        raise ValueError(f'{label} must be a nonempty flat uint31 ID list')
    return value


def read_token_record(path: Path, *, max_k: int, expected_prompt_length: int | None = G4_PROMPT_LENGTH) -> dict:
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema') != 'ft_dev_tokens/v1':
        raise ValueError('terminal token record has an unsupported schema')
    prompt = valid_ids(data.get('prompt_ids'), 'terminal prompt_ids')
    generated = valid_ids(data.get('generated_ids'), 'terminal generated_ids')
    if not 1 <= max_k <= 64 or len(generated) < max_k:
        raise ValueError('terminal record lacks the requested 1..64 generated-token prefix')
    if expected_prompt_length is not None and len(prompt) != expected_prompt_length:
        raise ValueError(f'terminal prompt length differs from expected {expected_prompt_length}')
    if data.get('finish_reason') not in {'stop', 'length'} or data.get('matched_stop') is not None and not isinstance(data['matched_stop'], str):
        raise ValueError('terminal token record is not a delivered non-aborted terminal response')
    if type(data.get('uid')) is not int or data['uid'] < 0 or type(data.get('pid')) is not int or data['pid'] <= 0:
        raise ValueError('terminal token record lacks UID/PID')
    full = prompt + generated
    if (data.get('prompt_length') != len(prompt)
            or data.get('prompt_ids_sha256_int32le') != ids_digest(prompt)
            or data.get('generated_ids_sha256_int32le') != ids_digest(generated)
            or data.get('input_ids_sha256_int32le') != ids_digest(full)):
        raise ValueError('terminal token record ID hashes or lengths do not bind its IDs')
    return data


def valid_restore_proof(proof: object, uid: object, cached_len: object) -> bool:
    return (
        isinstance(proof, dict) and proof.get('kind') in {'host', 'device'}
        and all(type(proof.get(key)) is int and proof[key] > 0 for key in ('source_slot', 'destination_slot'))
        and type(cached_len) is int and type(proof.get('length')) is int
        and 0 < proof['length'] <= cached_len and proof.get('uid') == uid
    )


def read_binding(path: Path, token: dict) -> dict:
    data = json.loads(path.read_text(encoding='utf-8'))
    required = ('trace_sha256', 'messages_sha', 'request_sha256', 'raw_ids_sha256', 'input_length')
    if any(not data.get(key) for key in required):
        raise ValueError('raw binding manifest lacks a required trace/request field')
    prompt = token['prompt_ids']
    if data.get('raw_ids_sha256') != ids_digest(prompt) or data.get('input_length') != len(prompt):
        raise ValueError('raw binding manifest does not bind terminal prompt IDs')
    return data

def verify_g4_source(module, token_path: Path, raw_binding: Path, trace: Path, candidate_commit: str) -> dict:
    """Validate the existing D03 selfcheck output chain; never accept a summary proxy."""
    if candidate_commit != module.CANDIDATE_COMMIT or module.PARENT_COMMIT != PARENT_COMMIT:
        raise ValueError('T04 candidate/parent must exactly match loaded SelfCheck constants')
    root = Path(module.SELF_CHECK_OUTPUT).resolve()
    if not root.is_dir() or (root / 'selfcheck_error.json').exists():
        raise ValueError('canonical D03 selfcheck is absent or failed')
    report = json.loads((root / 'selfcheck.json').read_text(encoding='utf-8'))
    admission = json.loads((root / 'admission.json').read_text(encoding='utf-8'))
    binding = report.get('g4_terminal_binding') or {}
    if (report.get('mode') != 'development_selfcheck_not_acceptance'
            or not report.get('cold_eq') or report.get('g4_boundaries') != [448,4544,8640,12672,14144,18240,21504]
            or admission.get('candidate_commit') != candidate_commit
            or admission.get('parent_commit') != PARENT_COMMIT
            or admission.get('trace_sha256') != sha256(trace)):
        raise ValueError('canonical D03 selfcheck report/admission does not bind this run')
    manifest = root / 'MANIFEST.sha256'
    if not manifest.is_file(): raise ValueError('canonical D03 selfcheck manifest is absent')
    declared = {}
    for line in manifest.read_text(encoding='utf-8').splitlines():
        digest, sep, relative = line.partition('  ')
        if not sep or not re.fullmatch(r'[0-9a-f]{64}', digest): raise ValueError('invalid D03 manifest entry')
        path = (root / relative).resolve()
        if root not in path.parents or not path.is_file() or sha256(path) != digest: raise ValueError('D03 manifest member mismatch')
        declared[str(path)] = digest
    source = Path(binding.get('path', '')).resolve()
    terminal = read_token_record(source, max_k=1)
    if (source != token_path.resolve() or str(source) not in declared
            or binding.get('sha256') != sha256(source)
            or binding.get('uid') != terminal['uid'] or binding.get('pid') != terminal['pid']
            or binding.get('prompt_sha256_int32le') != terminal['prompt_ids_sha256_int32le']
            or binding.get('generated_sha256_int32le') != terminal['generated_ids_sha256_int32le']
            or binding.get('generated_length') != len(terminal['generated_ids'])):
        raise ValueError('G4 terminal binding does not bind supplied token artifact')
    raw = json.loads(raw_binding.read_text(encoding='utf-8'))
    if raw.get('trace_sha256') != admission.get('trace_sha256'):
        raise ValueError('raw binding trace SHA differs from canonical selfcheck admission')
    return {'selfcheck_sha256': sha256(root / 'selfcheck.json'), 'admission_sha256': sha256(root / 'admission.json'), 'terminal_binding': binding}


class Phase2:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.sc = load_selfcheck()
        # Reuse the lifecycle's lock/gate/stop methods and only replace launch shape.
        self.base = self.sc.SelfCheck(argparse.Namespace(tail_k=args.k, trace=str(args.trace)))
        self.out = ROUND_ROOT / args.rid
        self.base.out = self.out
        
    def gate(self) -> dict:
        if self.args.rid != EXPECTED_RID:
            raise ValueError(f'RID must be root-assigned {EXPECTED_RID}')
        if not re.fullmatch(r'[0-9a-f]{40}', self.args.candidate_commit):
            raise ValueError('candidate commit must be an explicit lowercase full SHA-1')
        if self.out.exists():
            raise FileExistsError(f'formal round already exists: {self.out}')
        subprocess.run(['git', '-C', str(CANDIDATE), 'merge-base', '--is-ancestor', PARENT_COMMIT, self.args.candidate_commit], check=True)
        proof = self.base.gate(CANDIDATE, self.args.candidate_commit)
        if self.args.k > 64:
            raise ValueError('K must be <= 64')
        return proof

    def start(self, name: str, *, slots: int, prefill: int, state: bool = False) -> tuple[Path, dict]:
        """Use D03's shared service lifecycle with the narrow T04 arm parameters."""
        arm, env = self.base.start(
            name, CANDIDATE, state=state, logits=True,
            host_slots=slots, prefill_chunk=prefill, layer_major=False,
        )
        parsed = self.base.parser(str(arm / 'serve.log'))
        pid = json.loads((arm / 'owned_process.json').read_text())['pid']
        if ast.literal_eval(parsed.get('_unique_suffix', '')) != '.pid=' + str(pid): raise ValueError('T04 parsed PID mismatch')
        expected = {'mamba_host_slots': str(slots), 'max_extend_tokens': str(prefill), 'prefill_layer_major': 'False', 'enable_cache_report': 'True'}
        if any(str(parsed.get(k)) != v for k, v in expected.items()): raise ValueError('T04 parsed service configuration differs from arm contract')
        return arm, env

    def stop(self) -> None:
        self.base.stop()

    def verify_crossarm_args(self) -> None:
        allowed = {'_unique_suffix', 'mamba_host_slots', 'max_extend_tokens'}
        parsed = {name: self.base.parser(str(self.out / name / 'serve.log')) for name in ('candidate_boundary', 'restore', 'recompute', 'legal')}
        baseline = parsed['recompute']
        for name, values in parsed.items():
            if set(values) != set(baseline):
                raise ValueError('T04 parsed argument keys differ across arms')
            if any(values[key] != baseline[key] for key in values if key not in allowed):
                raise ValueError(f'T04 parsed arguments differ beyond PID/slot/chunk: {name}')

    def run_capture(self, arm: Path, env: dict, prefix: Path, suffix: Path, *, restore: bool) -> dict:
        argv = [PY, str(CANDIDATE / 'scripts/logits_probe.py'), 'capture', '--base-url', f'http://127.0.0.1:{PORT}',
                '--model', MODEL, '--prefix', str(prefix), '--suffix', str(suffix), '--dump', str(arm / 'logits')]
        if restore:
            argv.append('--require-restore')
        with (arm / 'logits_capture.log').open('x', encoding='utf-8') as sink:
            subprocess.run(argv, cwd=CANDIDATE, env=env, stdout=sink, stderr=subprocess.STDOUT, check=True, timeout=3600)
        lines = [line for line in (arm / 'logits_capture.log').read_text(encoding='utf-8').splitlines() if line.strip()]
        if not lines:
            raise ValueError('logits capture emitted no JSON')
        result = json.loads(lines[-1])
        if result.get('k') != self.args.k or result.get('input_length') != self._input_length:
            raise ValueError('capture K/input length differs from immutable token input')
        rows = [json.loads(line) for line in (arm / 'logits/index.jsonl').read_text(encoding='utf-8').splitlines() if line]
        matched = [row for row in rows if row.get('kind') == 'logits' and row.get('uid') == result.get('uid') and row.get('seq') == result.get('dump_seq')]
        if len(matched) != 1:
            raise ValueError('logits index lacks unique capture UID/sequence binding')
        candidates = list((arm / 'logits').glob(f"tokens_uid{result['uid']}_pid*.json"))
        tokens = [read_token_record(path, max_k=1, expected_prompt_length=result['input_length']) for path in candidates]
        tokens = [item for item in tokens if item['prompt_length'] == result['input_length'] and item['prompt_ids_sha256_int32le'] == result['input_sha256']]
        if len(tokens) != 1:
            raise ValueError('terminal token record does not uniquely bind logits input UID/SHA')
        owned = json.loads((arm / 'owned_process.json').read_text())
        if os.getpgid(tokens[0]['pid']) != owned.get('pgid'):
            raise ValueError('terminal token PID is outside owned service process group')
        result['capture_pid'] = tokens[0]['pid']
        if restore and not valid_restore_proof(result.get('restore_proof'), result.get('uid'), result.get('cached_len')):
            raise ValueError('restore arm did not prove a real restore')
        write_new(arm / 'capture.json', result)
        return result

    def compare(self, restore: Path, recompute: Path, legal: Path) -> dict:
        argv = [PY, str(CANDIDATE / 'scripts/logits_probe.py'), 'compare', '--recompute', str(recompute / 'logits'), '--restore', str(restore / 'logits'), '--legal', str(legal / 'logits'), '--require-restore']
        target = self.out / 'logits_compare.json'
        with target.open('x', encoding='utf-8') as sink:
            subprocess.run(argv, cwd=CANDIDATE, stdout=sink, stderr=subprocess.STDOUT, check=True, timeout=3600)
        result = json.loads(target.read_text(encoding='utf-8').splitlines()[-1])
        expected = (self._input_digest, self.args.k, self._input_length, list(range(self._input_length - self.args.k, self._input_length)))
        if tuple(result.get(key) for key in ('input_prefix_sha256', 'k', 'input_length', 'positions')) != expected:
            raise ValueError('comparison does not bind the exact full input/K/positions')
        return result

    def run(self) -> None:
        token = read_token_record(self.args.g4_token_file, max_k=self.args.k)
        source_report = verify_g4_source(self.sc, self.args.g4_token_file, self.args.raw_binding_manifest, self.args.trace, self.args.candidate_commit)
        binding = read_binding(self.args.raw_binding_manifest, token)
        document, historical_record, messages = self.sc.trace_record(self.args.trace)
        legacy = json.loads(self.sc.LEGACY_REPLAY.read_text(encoding='utf-8'))
        payload = self.sc.historical_payload(document, messages, legacy)
        if (binding['trace_sha256'] != sha256(self.args.trace)
                or binding['messages_sha'] != historical_record['messages_sha']
                or binding['request_sha256'] != self.sc.request_sha(payload)):
            raise ValueError('raw binding manifest does not bind the admitted historical G4 request')
        proof = self.gate()
        prompt, suffix = token['prompt_ids'], token['generated_ids'][:self.args.k]
        self._input_length = len(prompt) + len(suffix)
        self._input_digest = ids_digest(prompt + suffix)
        self.base.lock_take()
        created = False
        try:
            self.out.mkdir(); created = True
            source = Path(__file__).read_bytes()
            (self.out / Path(__file__).name).write_bytes(source)
            (self.out / 'runner_sha256.txt').write_text(hashlib.sha256(source).hexdigest() + '\n', encoding='utf-8')
            batch = ROOT / 'runs/plan_batches' / f'batch{self.args.batch}_{self.args.rid}_python.sh'
            if not batch.is_file(): raise FileNotFoundError(f'missing root batch wrapper: {batch}')
            (self.out / 'batch.sh').write_bytes(batch.read_bytes())
            batch_sha256 = sha256(batch)
            write_new(self.out / f'status_batch{self.args.batch}.json', {'rid': self.args.rid, 'batch': self.args.batch, 'batch_wrapper_sha256': batch_sha256, 'batch_pid': os.getpid(), 'pid': os.getpid(), 'gate': 'T04', 'state': 'running'})
            for name, path in {'terminal_tokens.json': self.args.g4_token_file, 'raw_binding_manifest.json': self.args.raw_binding_manifest, 'trace.json': self.args.trace}.items():
                target = self.out / name
                target.write_bytes(path.read_bytes())
            tools = {name: sha256(path) for name, path in {
                't04_logits_phase2.py': Path(__file__),
                'd03_gpu_selfcheck.py': ROOT / 'runs/dev_D03/d03_gpu_selfcheck.py',
                'logits_probe.py': CANDIDATE / 'scripts/logits_probe.py',
                'state_envelope.py': CANDIDATE / 'scripts/state_envelope.py',
            }.items()}
            write_new(self.out / 'tool_hashes.json', tools)
            write_new(self.out / 'admission.json', {'rid': self.args.rid, 'card': 'T04', 'phase': 'phase2', 'batch': self.args.batch, 'commit': PARENT_COMMIT, 'code_version': 'E2-base@23f2e2c', 'batch_wrapper_sha256': batch_sha256, 'candidate_commit': self.args.candidate_commit, 'parent_commit': PARENT_COMMIT, 'candidate_proof': proof, 'input': {'token_file_sha256': sha256(self.args.g4_token_file), 'binding_manifest_sha256': sha256(self.args.raw_binding_manifest), 'trace_sha256': sha256(self.args.trace), 'terminal_uid': token['uid'], 'terminal_pid': token['pid'], 'prompt_length': len(prompt), 'k': self.args.k, 'full_input_sha256': self._input_digest}, 'binding': binding, 'g4_selfcheck_chain': source_report, 'g4_source_report': source_report})
            prefix, tail = self.out / 'prompt_ids.json', self.out / 'output_ids_first_k.json'
            write_new(prefix, prompt); write_new(tail, suffix)
            # The boundary arm must itself deliver the historical chat request so D03
            # writes a new immutable terminal-token record.  That record is compared to
            # the supplied token evidence before its raw P+X logits capture proceeds.
            captures = {}
            arm, env = self.start('candidate_boundary', slots=0, prefill=4096, state=True)
            try:
                self.base.chat(arm, payload)
                terminal_paths = sorted((arm / 'logits').glob('tokens_uid*_pid*.json'))
                if len(terminal_paths) != 1:
                    raise ValueError(f'candidate boundary needs exactly one terminal token record, got {len(terminal_paths)}')
                boundary_token = read_token_record(terminal_paths[0], max_k=self.args.k)
                if boundary_token['prompt_ids'] != prompt:
                    raise ValueError('candidate boundary terminal prompt IDs do not match immutable P evidence')
                captures['candidate_boundary_regenerated_x'] = {'matches_supplied': boundary_token['generated_ids'][:self.args.k] == suffix, 'generated_ids_first_k': boundary_token['generated_ids'][:self.args.k], 'supplied_ids_first_k': suffix, 'meaning': 'diagnostic only; boundary configuration differs from frozen X source'}
                rows = [json.loads(line) for line in (arm / 'state/index.jsonl').read_text(encoding='utf-8').splitlines() if line]
                found = {row.get('length') for row in rows if row.get('kind') == 'boundary'}
                if found != set(self.sc.BOUNDARIES):
                    raise ValueError(f'candidate boundary dump lengths differ: {sorted(found)}')
                captures['candidate_boundary_terminal'] = {'path': str(terminal_paths[0]), 'sha256': sha256(terminal_paths[0]), 'uid': boundary_token['uid'], 'pid': boundary_token['pid']}
                captures['candidate_boundary'] = self.run_capture(arm, env, prefix, tail, restore=False)
            finally:
                self.stop()
            for name, slots, prefill, required_restore in (('restore', 32, 4096, True), ('recompute', 0, 4096, False), ('legal', 0, 8192, False)):
                arm, env = self.start(name, slots=slots, prefill=prefill)
                try:
                    captures[name] = self.run_capture(arm, env, prefix, tail, restore=required_restore)
                finally:
                    self.stop()
            self.verify_crossarm_args()
            result = self.compare(self.out / 'restore', self.out / 'recompute', self.out / 'legal')
            write_new(self.out / 'round_metadata.json', {'rid': self.args.rid, 'status': 'complete_measurements_pending_review', 'arms': captures, 'comparison': result})
            (self.out / f'status_batch{self.args.batch}.json').write_text(json.dumps({'rid': self.args.rid, 'batch': self.args.batch, 'batch_wrapper_sha256': batch_sha256, 'batch_pid': os.getpid(), 'pid': os.getpid(), 'gate': 'T04', 'state': 'complete_measurements_pending_review'}, ensure_ascii=False) + '\n', encoding='utf-8')
        except BaseException as exc:
            if created:
                write_new(self.out / 't04_phase2_error.json', {'error': repr(exc)})
                status = self.out / f'status_batch{self.args.batch}.json'
                if status.exists(): status.write_text(json.dumps({'rid': self.args.rid, 'batch': self.args.batch, 'batch_pid': os.getpid(), 'pid': os.getpid(), 'gate': 'T04', 'state': 'error', 'error': repr(exc)}, ensure_ascii=False) + '\n', encoding='utf-8')
            raise
        finally:
            try:
                self.stop()
            finally:
                self.base.lock_release()
                if created:
                    paths = sorted(p for p in self.out.rglob('*') if p.is_file() and p.name != 'RUN_MANIFEST.sha256')
                    (self.out / 'RUN_MANIFEST.sha256').write_text(''.join(f'{sha256(p)}  {p.relative_to(self.out)}\n' for p in paths), encoding='utf-8')


def self_test() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        prompt, generated = list(range(G4_PROMPT_LENGTH)), [4, 5, 6]
        token = {'schema': 'ft_dev_tokens/v1', 'uid': 1, 'pid': 2, 'prompt_length': G4_PROMPT_LENGTH, 'prompt_ids': prompt, 'generated_ids': generated, 'finish_reason': 'length', 'matched_stop': None, 'prompt_ids_sha256_int32le': ids_digest(prompt), 'generated_ids_sha256_int32le': ids_digest(generated), 'input_ids_sha256_int32le': ids_digest(prompt + generated)}
        token_path = root / 'tokens.json'; token_path.write_text(json.dumps(token), encoding='utf-8')
        assert read_token_record(token_path, max_k=2)['uid'] == 1
        bad = dict(token); bad['generated_ids'] = [4]
        token_path.write_text(json.dumps(bad), encoding='utf-8')
        try:
            read_token_record(token_path, max_k=2)
        except ValueError:
            pass
        else:
            raise AssertionError('short generated IDs accepted')
        token_path.write_text(json.dumps(token), encoding='utf-8')
        binding = {'trace_sha256': 'a', 'messages_sha': 'b', 'request_sha256': 'c', 'raw_ids_sha256': ids_digest(prompt), 'input_length': G4_PROMPT_LENGTH}
        binding_path = root / 'binding.json'; binding_path.write_text(json.dumps(binding), encoding='utf-8')
        assert read_binding(binding_path, token)['messages_sha'] == 'b'
        binding['input_length'] = G4_PROMPT_LENGTH + 1; binding_path.write_text(json.dumps(binding), encoding='utf-8')
        try:
            read_binding(binding_path, token)
        except ValueError:
            pass
        else:
            raise AssertionError('wrong prompt length accepted')

    # Runtime parsed-argument checks use actual serve logs; lifecycle configuration is
    # independently covered by the shared SelfCheck CPU suite.


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--rid', default=EXPECTED_RID)
    parser.add_argument('--batch', type=int)
    parser.add_argument('--candidate-commit')
    parser.add_argument('--g4-token-file', type=Path)
    parser.add_argument('--raw-binding-manifest', type=Path)
    parser.add_argument('--trace', type=Path)
    parser.add_argument('--k', type=int, default=32)
    args = parser.parse_args()
    if args.self_test:
        self_test(); return
    if not args.run:
        parser.error('--run is required; no resources are touched otherwise')
    if args.batch is None or args.batch < 1 or not args.candidate_commit or not args.g4_token_file or not args.raw_binding_manifest or not args.trace:
        parser.error('--run requires --batch, --candidate-commit, --g4-token-file, --raw-binding-manifest, and --trace')
    if not all(path.is_file() for path in (args.g4_token_file, args.raw_binding_manifest, args.trace)):
        parser.error('input artifact does not exist as a regular file')
    if os.name != 'posix': parser.error('--run requires Linux')
    Phase2(args).run()


if __name__ == '__main__':
    main()
