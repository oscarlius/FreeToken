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
from types import ModuleType, SimpleNamespace
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
CANDIDATE = ROOT / 'wt/e2d03-continuation'
G4_PROMPT_LENGTH = 21976
FP32_TAIL_K = 32
Y129_BRANCH_LENGTH = 12672
Y129_BRANCH_TOKEN_COUNT = 129
F506_SELFCHECK_SHA256 = '96db3ca98bf40a629342586061b5d0acd21d1fb4e1c47fb8bef0e9b8ea56715b'
F506_BASE_SHA256 = '4cf751a93457ef28a88fc175004c86d12130b84943193cb43c55254c2e0fb453'
F506_MANIFEST_SHA256 = 'd5e472ea4890891c9a5d11f0121964861e2a8a3a07ccc67fcfde3e244926b7d7'
RAW_MANIFEST_SHA256 = '0d59fa0777bdfb3e521b84723c426a895418942a7eff9fa0367d8b3078444926'
TERMINAL_TOKEN_SHA256 = '88ae751e197904cfdbebd36ede46928b29330e44e6a20bbbdd0c5a6b6de1c0d1'
RAW_IDS_SHA256 = '327e35d27fec334e2907e91f278798f789d787157528a71dd0e4da46babd6285'
TERMINAL_UID = 0
TERMINAL_PID = 3762886
SELFCHECK_OUTPUT = ROOT / 'runs/dev_D03/gpu_selfcheck_f5067bb'
CONTROLLED_CLIENT = Path(__file__).with_name('t04_capture_controlled.py')
CONTROLLED_CLIENT_SHA256 = '14b1eb09a9a49ba4c46176ca3edc5d52b927a07f4c476ae55c1d144c979c50fb'
CANDIDATE_PROBE_SHA256 = '7ab4fd3a256c2fd3d510bd63d77b5181a648e5d8f8609ebf1a52b68f3a6c45e7'
EXPECTED_RID = 'E2-R021'
PARENT_COMMIT = 'c30ae0d7003c3bbbf56867ce74da797332fa7ed5'
PY = str(ROOT / 'venv/bin/python')
FT = str(ROOT / 'venv/bin/ft')
MODEL = 'Qwen3.8-Flash-Next-NVFP4'
PORT = 8095


def require_fp32_tail_k(k: object) -> int:
    if type(k) is not int or k != FP32_TAIL_K:
        raise ValueError('T04 f506/Y129 requires fixed FP32 K=32')
    return k


def capture_mode(arm: str) -> str:
    mapping = {
        'candidate_boundary': 'diagnostic',
        'restore': 'branch-bank',
        'recompute': 'fresh',
        'legal': 'fresh',
    }
    try:
        return mapping[arm]
    except KeyError as exc:
        raise ValueError(f'unknown T04 arm: {arm}') from exc


def controlled_argv(*, client: Path, base_url: str, prefix: Path, suffix: Path,
                    dump: Path, arm: str) -> list[str]:
    return [
        PY, str(client), '--base-url', base_url, '--model', MODEL,
        '--prefix', str(prefix), '--suffix', str(suffix), '--dump', str(dump),
        '--mode', capture_mode(arm), '--branch-length', str(Y129_BRANCH_LENGTH),
        '--branch-token-count', str(Y129_BRANCH_TOKEN_COUNT),
    ]


def validate_restore_proof(proof: object, uid: object) -> None:
    if not isinstance(proof, dict):
        raise ValueError('restore arm lacks a restore proof')
    if proof.get('kind') != 'host' or proof.get('uid') != uid:
        raise ValueError('restore proof is not a host proof for this UID')
    if proof.get('length') != Y129_BRANCH_LENGTH:
        raise ValueError('restore proof does not prove host length 12672')


def load_selfcheck(path: Path | None = None):
    """Load the pinned f506 wrapper and expose its protocol plus subclass."""
    path = path or SELFCHECK_OUTPUT / 'd03_gpu_selfcheck_f506.py'
    source = path.read_bytes()
    if hashlib.sha256(source).hexdigest() != F506_SELFCHECK_SHA256:
        raise RuntimeError(f'f506 selfcheck SHA256 mismatch: {path}')
    module = ModuleType('d03_f506_selfcheck')
    module.__file__ = str(path)
    module.__package__ = ''
    exec(compile(source, str(path), 'exec'), module.__dict__)
    protocol = getattr(module, '_protocol', None)
    if getattr(module, 'BASE_SHA256', None) != F506_BASE_SHA256:
        raise RuntimeError('f506 selfcheck does not bind the reviewed lifecycle base')
    if not isinstance(protocol, dict) or not isinstance(getattr(module, 'SelfCheck', None), type):
        raise RuntimeError('f506 selfcheck does not expose reviewed protocol and SelfCheck')
    protocol['SELF_CHECK_OUTPUT'] = SELFCHECK_OUTPUT
    module.SELF_CHECK_OUTPUT = SELFCHECK_OUTPUT
    values = {**protocol, 'SelfCheck': module.SelfCheck,
              'CANDIDATE_COMMIT': module.CANDIDATE_COMMIT,
              'PARENT_COMMIT': module.PARENT_COMMIT,
              'SELF_CHECK_OUTPUT': SELFCHECK_OUTPUT}
    return SimpleNamespace(**values)


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


def read_token_record(path: Path, *, max_k: int, expected_prompt_length: int | None = G4_PROMPT_LENGTH,
                      require_f506_identity: bool = True) -> dict:
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
    if (type(data.get('uid')) is not int or data['uid'] < 0
            or type(data.get('pid')) is not int or data['pid'] <= 0):
        raise ValueError('terminal token record lacks UID/PID')
    if require_f506_identity and (data['uid'] != TERMINAL_UID or data['pid'] != TERMINAL_PID):
        raise ValueError('terminal token record UID/PID does not bind f506 G4 source')
    full = prompt + generated
    if (data.get('prompt_length') != len(prompt)
            or data.get('prompt_ids_sha256_int32le') != ids_digest(prompt)
            or data.get('generated_ids_sha256_int32le') != ids_digest(generated)
            or data.get('input_ids_sha256_int32le') != ids_digest(full)):
        raise ValueError('terminal token record ID hashes or lengths do not bind its IDs')
    return data



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
    """Bind this T04 run to the approved f506 G4/G5 artifact chain."""
    if candidate_commit != module.CANDIDATE_COMMIT or module.PARENT_COMMIT != PARENT_COMMIT:
        raise ValueError('T04 candidate/parent differs from f506 lifecycle constants')
    root = Path(module.SELF_CHECK_OUTPUT).resolve()
    manifest = root / 'MANIFEST.sha256'
    if not manifest.is_file() or sha256(manifest) != F506_MANIFEST_SHA256:
        raise ValueError('f506 full manifest is absent or differs from approved bytes')
    declared: dict[str, str] = {}
    for line in manifest.read_text(encoding='utf-8').splitlines():
        digest, separator, relative = line.partition('  ')
        member = (root / relative).resolve()
        if (not separator or not re.fullmatch(r'[0-9a-f]{64}', digest)
                or root not in member.parents or not member.is_file()
                or sha256(member) != digest):
            raise ValueError('f506 manifest member mismatch')
        declared[str(member)] = digest
    if sha256(token_path) != TERMINAL_TOKEN_SHA256:
        raise ValueError('terminal token source differs from approved f506 G4 record')
    terminal = read_token_record(token_path, max_k=1)
    if (terminal['uid'] != TERMINAL_UID or terminal['pid'] != TERMINAL_PID
            or terminal['prompt_length'] != G4_PROMPT_LENGTH
            or terminal['prompt_ids_sha256_int32le'] != RAW_IDS_SHA256):
        raise ValueError('terminal token record does not bind f506 G4 UID/PID/raw input')
    raw = json.loads(raw_binding.read_text(encoding='utf-8'))
    if (sha256(raw_binding) != RAW_MANIFEST_SHA256
            or raw.get('raw_ids_sha256') != RAW_IDS_SHA256
            or raw.get('input_length') != G4_PROMPT_LENGTH):
        raise ValueError('raw v2 manifest does not bind approved f506 G4 input')
    review = Path(__file__).with_name('d03_f506_r018_independent_review.json')
    if review.is_file():
        data = json.loads(review.read_text(encoding='utf-8'))
        f506 = data.get('f506', {})
        if (f506.get('manifest_sha256') != F506_MANIFEST_SHA256
                or f506.get('g4_uid') != TERMINAL_UID
                or f506.get('g5', {}).get('raw_prompt_int32le_sha256') != RAW_IDS_SHA256):
            raise ValueError('independent f506 review disagrees with required G4/G5 bindings')
    return {'manifest_sha256': F506_MANIFEST_SHA256, 'manifest_members': len(declared),
            'terminal_token_sha256': TERMINAL_TOKEN_SHA256,
            'raw_manifest_sha256': RAW_MANIFEST_SHA256,
            'terminal_uid': TERMINAL_UID, 'terminal_pid': TERMINAL_PID}


class Phase2:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.sc = load_selfcheck()
        # Reuse the lifecycle's lock/gate/stop methods and only replace launch shape.
        self.base = self.sc.SelfCheck(argparse.Namespace(tail_k=args.k, trace=str(args.trace), raw_ids=None, raw_manifest=None))
        self.out = ROUND_ROOT / args.rid
        self.base.out = self.out
        
    def gate(self) -> dict:
        require_fp32_tail_k(self.args.k)
        if self.args.rid != EXPECTED_RID:
            raise ValueError(f'RID must be root-assigned {EXPECTED_RID}')
        if not re.fullmatch(r'[0-9a-f]{40}', self.args.candidate_commit):
            raise ValueError('candidate commit must be an explicit lowercase full SHA-1')
        if self.out.exists():
            raise FileExistsError(f'formal round already exists: {self.out}')
        subprocess.run(['git', '-C', str(CANDIDATE), 'merge-base', '--is-ancestor', PARENT_COMMIT, self.args.candidate_commit], check=True)
        return self.base.gate(CANDIDATE, self.args.candidate_commit)

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
        mode = capture_mode(arm.name)
        if restore != (mode == 'branch-bank'):
            raise ValueError('capture arm and restore contract disagree')
        if sha256(CONTROLLED_CLIENT) != CONTROLLED_CLIENT_SHA256:
            raise RuntimeError('controlled client differs from reviewed source')
        probe = CANDIDATE / 'scripts/logits_probe.py'
        if sha256(probe) != CANDIDATE_PROBE_SHA256:
            raise RuntimeError('candidate logits probe differs from controlled-client frozen probe')
        argv = controlled_argv(client=CONTROLLED_CLIENT,
                              base_url=f'http://127.0.0.1:{PORT}', prefix=prefix,
                              suffix=suffix, dump=arm / 'logits', arm=arm.name)
        log = arm / 'logits_capture.log'
        with log.open('x', encoding='utf-8') as sink:
            subprocess.run(argv, cwd=CANDIDATE, env=env, stdout=sink,
                           stderr=subprocess.STDOUT, check=True, timeout=3600)
        lines = [line for line in log.read_text(encoding='utf-8').splitlines() if line.strip()]
        if not lines:
            raise ValueError('controlled logits capture emitted no JSON')
        result = json.loads(lines[-1])
        if result.get('mode') != mode or result.get('k') != self.args.k:
            raise ValueError('controlled capture mode/K differs from arm contract')
        if result.get('input_length') != self._input_length or result.get('input_sha256') != self._input_digest:
            raise ValueError('controlled capture does not bind immutable P+X input')
        positions = list(range(self._input_length - self.args.k, self._input_length))
        if result.get('positions') != positions:
            raise ValueError('controlled capture positions differ from P+X tail')
        rows = [json.loads(line) for line in (arm / 'logits/index.jsonl').read_text(encoding='utf-8').splitlines() if line]
        matched = [row for row in rows if row.get('kind') == 'logits' and row.get('uid') == result.get('uid') and row.get('seq') == result.get('dump_seq')]
        if len(matched) != 1:
            raise ValueError('logits index lacks unique capture UID/sequence binding')
        token_paths = sorted((arm / 'logits').glob('tokens_uid*_pid*.json'))
        tokens = [read_token_record(path, max_k=1,
                                    expected_prompt_length=result['input_length'],
                                    require_f506_identity=False)
                  for path in token_paths]
        tokens = [token for token in tokens
                  if token['uid'] == result.get('uid')
                  and token['prompt_ids_sha256_int32le'] == result.get('input_sha256')]
        if len(tokens) != 1:
            raise ValueError('capture terminal token does not uniquely bind UID/input SHA')
        owned = json.loads((arm / 'owned_process.json').read_text(encoding='utf-8'))
        if type(owned.get('pgid')) is not int or os.getpgid(tokens[0]['pid']) != owned['pgid']:
            raise ValueError('capture terminal token PID is outside the owned service group')
        result['capture_pid'] = tokens[0]['pid']
        if restore:
            validate_restore_proof(result.get('restore_proof'), result.get('uid'))
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
                't04_f506_y129_runner.py': Path(__file__),
                'd03_gpu_selfcheck_f506.py': SELFCHECK_OUTPUT / 'd03_gpu_selfcheck_f506.py',
                't04_capture_controlled.py': CONTROLLED_CLIENT,
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
                boundary_token = read_token_record(terminal_paths[0], max_k=self.args.k, require_f506_identity=False)
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
                # Keep the GPU lock when f506 could not prove complete owned cleanup.
                if (getattr(self.base, 'proc', None) is None
                        and not getattr(self.base, '_cleanup_failed', False)):
                    self.base.lock_release()
                if created:
                    paths = sorted(p for p in self.out.rglob('*') if p.is_file() and p.name != 'RUN_MANIFEST.sha256')
                    (self.out / 'RUN_MANIFEST.sha256').write_text(''.join(f'{sha256(p)}  {p.relative_to(self.out)}\n' for p in paths), encoding='utf-8')


def self_test() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        prompt, generated = list(range(G4_PROMPT_LENGTH)), [4, 5, 6]
        token = {'schema': 'ft_dev_tokens/v1', 'uid': TERMINAL_UID, 'pid': TERMINAL_PID, 'prompt_length': G4_PROMPT_LENGTH, 'prompt_ids': prompt, 'generated_ids': generated, 'finish_reason': 'length', 'matched_stop': None, 'prompt_ids_sha256_int32le': ids_digest(prompt), 'generated_ids_sha256_int32le': ids_digest(generated), 'input_ids_sha256_int32le': ids_digest(prompt + generated)}
        token_path = root / 'tokens.json'; token_path.write_text(json.dumps(token), encoding='utf-8')
        assert read_token_record(token_path, max_k=2)['uid'] == TERMINAL_UID
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--rid', default=EXPECTED_RID)
    parser.add_argument('--batch', type=int)
    parser.add_argument('--candidate-commit')
    parser.add_argument('--g4-token-file', type=Path)
    parser.add_argument('--raw-binding-manifest', type=Path)
    parser.add_argument('--trace', type=Path)
    parser.add_argument('--k', type=int, default=FP32_TAIL_K)
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    try:
        require_fp32_tail_k(args.k)
    except ValueError as exc:
        parser.error(str(exc))
    if not args.run:
        parser.error('--run is required; no resources are touched otherwise')
    if args.batch is None or args.batch < 1 or not args.candidate_commit or not args.g4_token_file or not args.raw_binding_manifest or not args.trace:
        parser.error('--run requires --batch, --candidate-commit, --g4-token-file, --raw-binding-manifest, and --trace')
    if not all(path.is_file() for path in (args.g4_token_file, args.raw_binding_manifest, args.trace)):
        parser.error('input artifact does not exist as a regular file')
    if os.name != 'posix':
        parser.error('--run requires Linux')

    interrupt_seen = False
    def interrupted(signum, _frame):
        nonlocal interrupt_seen
        if interrupt_seen:
            return
        interrupt_seen = True
        raise InterruptedError('T04 f506/Y129 interrupted by signal ' + str(signum))

    previous = {signum: signal.signal(signum, interrupted)
                for signum in (signal.SIGINT, signal.SIGTERM)}
    try:
        Phase2(args).run()
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
    return 0


if __name__ == '__main__':
    main()

