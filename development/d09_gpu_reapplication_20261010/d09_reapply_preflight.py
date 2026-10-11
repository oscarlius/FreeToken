"""CPU-only, fail-closed D09 bd57 GPU-reapplication adapter.

This module deliberately has no service-start branch.  It materializes the new
candidate's route descriptor and effects contract for independent review; GPU
execution remains outside this packet and requires fresh T16 closure and root
admission.
"""
from __future__ import annotations
import hashlib, json, os, subprocess, sys, time
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path('/data2/FreeToken')
WT = ROOT / 'wt/d09-page-conservation-20261010'
C17 = ROOT / 'wt/d09-message-boundary-v1'
CANDIDATE = 'bd57cfdccc2a935d46cb0a89b8b36be7a18706de'
T16_RID = 'E2-D09-T16-reapply-bd57-20261010'
T17_RID = 'E2-D09-T17-reapply-bd57-20261010'
NATIVE = {
    '_cpu_moe.cpython-310-x86_64-linux-gnu.so': ('10a2bd8311b9569bd03a6569db59da707699a44e67d7b677c35c3547d77855b4', 12448560),
    '_pinned_tensor.cpython-310-x86_64-linux-gnu.so': ('07701be28030c4ebf63c210804b6eba2556cc0f4d2f1e5ed80b9d423ebfe7e68', 10841304),
}

def sha(path: Path | str) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def _candidate_identity() -> dict:
    head = subprocess.check_output(['git', '-C', str(WT), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(WT), 'status', '--porcelain', '--untracked-files=no'], text=True)
    if head != CANDIDATE or dirty:
        raise RuntimeError('bd57 candidate identity/cleanliness differs')
    return {'commit': head, 'tracked_clean': True}

def native_links() -> dict:
    result = {}
    for name, (digest, size) in NATIVE.items():
        dest = WT / 'python/freetoken/kernel' / name
        source = C17 / 'python/freetoken/kernel' / name
        if not dest.is_symlink() or not source.is_file() or dest.resolve() != source.resolve():
            raise RuntimeError('bd57 native link differs: ' + name)
        if source.is_symlink() or sha(source) != digest or source.stat().st_size != size:
            raise RuntimeError('read-only c17 native source differs: ' + name)
        if sha(dest) != digest or dest.stat().st_size != size:
            raise RuntimeError('bd57 native link bytes differ: ' + name)
        result[name] = {'destination': str(dest), 'resolved_source': str(source.resolve()), 'sha256': digest, 'size': size}
    return result

def plan(stage: str) -> dict:
    if stage == 't16':
        return {'rid': T16_RID, 'stage': 'T16', 'services': 8, 'calls': 100,
                'flags': [], 'server_args': {'message_boundary_ckpt': False}, 'requires_prior_t16_closure': False}
    if stage == 't17':
        return {'rid': T17_RID, 'stage': 'T17', 'services': 6, 'calls': 8, 'max_tokens': 32,
                'cells': [{'P': 20282, 'tail': 1020}, {'P': 22558, 'tail': 197}],
                'flags': ['--enable-message-boundary-ckpt'], 'requires_prior_t16_closure': True}
    raise ValueError(stage)

def require_fresh_t16_closure(closure: dict | None) -> None:
    if not closure:
        raise RuntimeError('T17 is blocked: fresh bd57 T16 closure is absent')
    required = {'rid': T16_RID, 'candidate_commit': CANDIDATE, 'verdict': 'kept', 'services': 8, 'calls': 100}
    if any(closure.get(k) != value for k, value in required.items()):
        raise RuntimeError('T17 is blocked: supplied T16 closure is not the new bd57 T16 result')

@dataclass
class CpuEffects:
    """CPU test seam; records a descriptor but cannot execute it."""
    clock: callable = time.monotonic
    idle: callable = lambda: True
    events: list[dict] = field(default_factory=list)

    def materialize(self, item: dict) -> dict:
        binding = {'candidate': CANDIDATE, 'rid': item['rid'], 'route': '/internal/t17/exact-ids',
                   'cwd': str(WT), 'pythonpath': str(WT / 'python'), 'flags': item['flags']}
        if not binding['pythonpath'] or item['services'] < 1:
            raise RuntimeError('input binding incomplete')
        self.events.append({'event': 'materialize', 'input_binding': binding})
        return binding

    def spawn_factory(self, binding: dict) -> dict:
        descriptor = {'argv': [str(ROOT / 'venv/bin/python'), '-u', 'bd57_route_adapter.py', '--cpu-route-probe'],
                      'cwd': binding['cwd'], 'route': binding['route'], 'execute': False}
        self.events.append({'event': 'spawn_factory', 'descriptor': descriptor})
        return descriptor

    def cleanup(self, deadline: float) -> None:
        if self.clock() > deadline or not self.idle():
            self.events.append({'event': 'cleanup_failed_harness', 'lock_retained': True})
            raise RuntimeError('failed_harness: GPU idle wait expired')
        self.events.append({'event': 'cleanup', 'gpu_lock_taken': False, 'gpu_idle': True})

def native_cpu_import() -> dict:
    code = "import json,torch; before=torch.cuda.is_initialized(); import freetoken.kernel._cpu_moe as cpu; import freetoken.kernel._pinned_tensor as pinned; print(json.dumps({'cpu_moe':cpu.__file__,'pinned_tensor':pinned.__file__,'cuda_initialized_before':before,'cuda_initialized_after':torch.cuda.is_initialized()}))"
    env = os.environ | {'PYTHONPATH': str(WT / 'python'), 'CUDA_VISIBLE_DEVICES': '', 'PYTHONDONTWRITEBYTECODE': '1'}
    result = subprocess.run([str(ROOT / 'venv/bin/python'), '-c', code], text=True, capture_output=True, env=env, timeout=90)
    if result.returncode:
        raise RuntimeError('native CPU import failed: ' + result.stderr[-500:])
    proof = json.loads(result.stdout)
    if proof['cuda_initialized_before'] or proof['cuda_initialized_after']:
        raise RuntimeError('native CPU import initialized CUDA')
    if not all(str(WT) in proof[key] for key in ('cpu_moe', 'pinned_tensor')):
        raise RuntimeError('native CPU import did not resolve bd57 links')
    return proof
def candidate_route_probe() -> dict:
    adapter = HERE / 'bd57_route_adapter.py'
    env = os.environ | {'PYTHONPATH': str(WT / 'python'), 'CUDA_VISIBLE_DEVICES': '', 'PYTHONDONTWRITEBYTECODE': '1'}
    result = subprocess.run([str(ROOT / 'venv/bin/python'), str(adapter), '--cpu-route-probe'], text=True, capture_output=True, env=env, timeout=90)
    if result.returncode:
        raise RuntimeError('candidate CPU route probe failed: ' + result.stderr[-500:])
    proof = json.loads(result.stdout)
    if proof['route'] != '/internal/t17/exact-ids' or proof['cuda_initialized']:
        raise RuntimeError('candidate CPU route proof differs')
    return proof

def candidate_cpu_import() -> dict:
    code = "import json,torch; before=torch.cuda.is_initialized(); from freetoken.server import api_server; print(json.dumps({'app':type(api_server.app).__name__,'cuda_initialized_before':before,'cuda_initialized_after':torch.cuda.is_initialized()}))"
    env = os.environ | {'PYTHONPATH': str(WT / 'python'), 'CUDA_VISIBLE_DEVICES': '', 'PYTHONDONTWRITEBYTECODE': '1'}
    result = subprocess.run([str(ROOT / 'venv/bin/python'), '-c', code], text=True, capture_output=True, env=env, timeout=90)
    if result.returncode:
        raise RuntimeError('candidate CPU import failed: ' + result.stderr[-500:])
    proof = json.loads(result.stdout)
    if proof['cuda_initialized_before'] or proof['cuda_initialized_after']:
        raise RuntimeError('candidate CPU import initialized CUDA')
    return proof

def filedry() -> dict:
    identity = _candidate_identity()
    links = native_links()
    refs = {
        't16_runner': ROOT / 'development/d09_t16_night_v1/d09_t16_full_runner_retry1.py',
        't17_runner': ROOT / 'development/d09_t17_morning_20261010/runner.py',
        'cpu_receipt': WT / 'development/d09_cpu_repair_20261010/CPU_REPAIR_RECEIPT.json',
    }
    if any(not path.is_file() for path in refs.values()):
        raise RuntimeError('required protocol reference missing')
    effects = CpuEffects(); t16 = plan('t16'); binding = effects.materialize(t16); descriptor = effects.spawn_factory(binding)
    effects.cleanup(effects.clock() + 1)
    try:
        require_fresh_t16_closure(None)
    except RuntimeError as error:
        t17_gate = str(error)
    return {
        'schema': 'ft_d09_bd57_reapplication_filedry/v2', 'status': 'cpu_preflight_ready_not_gpu_admitted',
        'candidate': identity, 'native_links': links, 'references': {key: {'path': str(value), 'sha256': sha(value)} for key, value in refs.items()},
        'route_adapter': {'path': str(HERE/'bd57_route_adapter.py'), 'sha256': sha(HERE/'bd57_route_adapter.py'), 'probe': candidate_route_probe()}, 'native_cpu_import': native_cpu_import(), 'candidate_cpu_import': candidate_cpu_import(), 't16': t16, 't17': plan('t17'),
        't17_gate': t17_gate, 'effects': effects.events, 'spawn_descriptor': descriptor,
        'constraints': {'gpu_started': False, 'http_started': False, 'gpu_lock_taken': False,
                        'requires_fresh_t16_then_new_root_admission_then_user_gpu_approval': True},
    }

if __name__ == '__main__':
    print(json.dumps(filedry(), sort_keys=True))



