"""Actual V10 CLI: consume canonical evidence, then reuse the reviewed V8 body."""
import hashlib, importlib.util, json, os, subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('d10_v10_reviewed_body', HERE / 'd10_prototype_owned_parent_v8.py')
b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
RID = 'E2-D10-PROTOTYPE-night-20261010-v10'
CHECKER = b.ROOT / 'scripts/round_json_append.py'
SOURCES = tuple(dict.fromkeys((*b.ACTUAL, Path(__file__).name, 'ROOT_NATIVE_REUSE_V2.json')))


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def regular(p, readonly=True):
    p = Path(p)
    if not p.is_file() or p.is_symlink() or readonly and p.stat().st_mode & 0o222:
        raise RuntimeError('regular frozen evidence required: ' + str(p))
    return p


def sources():
    return {str(regular(HERE / name)): sha(HERE / name) for name in SOURCES} | {str(regular(CHECKER)): sha(CHECKER)}


def formal(rid):
    directory = b.ROUND_ROOT / rid
    r = regular(directory / 'round.json'); m = regular(directory / 'MANIFEST.sha256')
    names = []
    for line in m.read_text().splitlines():
        digest, name = line.split('  ', 1); name = name.removeprefix('./')
        if len(digest) != 64 or Path(name).is_absolute() or '..' in Path(name).parts:
            raise RuntimeError('manifest path/digest malformed')
        if name in ('round.json', 'MANIFEST.sha256') or name.startswith('round_history/'):
            raise RuntimeError('governance entry in data manifest')
        if sha(regular(directory / name)) != digest: raise RuntimeError('data digest mismatch: ' + name)
        names.append(name)
    files = []
    for p in directory.rglob('*'):
        if p.is_symlink(): raise RuntimeError('symlink in formal round')
        if p.is_file():
            name = p.relative_to(directory).as_posix()
            if name not in ('round.json', 'MANIFEST.sha256') and not name.startswith('round_history/'):
                files.append(name)
    if sorted(names) != sorted(files) or len(names) != len(set(names)): raise RuntimeError('formal data coverage differs')
    hist = regular(directory / 'round_history/SHA256SUMS')
    result = subprocess.run([str(b.ROOT / 'venv/bin/python'), '-B', str(CHECKER), str(directory), 'check'], capture_output=True, text=True)
    if result.returncode or json.loads(result.stdout).get('ok') is not True: raise RuntimeError('formal history check failed')
    return json.loads(r.read_text()), {'round_json': str(r), 'round_sha256': sha(r), 'manifest_sha256': sha(m), 'history_sha256': sha(hist)}


def round_proof(doc, key, rid, candidate, flag, allowed):
    body, binding = formal(rid)
    if doc.get(key) != binding: raise RuntimeError(key + ' canonical hash binding differs')
    if (body.get('schema') != 'ft_round/v2' or body.get('round_id') != rid or body.get('verdict') not in allowed
        or body.get('experimental', {}).get('candidate_commit') != candidate or body.get('base', {}).get('commit') != b.PARENT):
        raise RuntimeError(key + ' candidate/base/verdict differs')
    candidate_binding = json.loads(regular(b.ROUND_ROOT / rid / 'candidate_binding.json').read_text())
    if (candidate_binding.get('parent_commit') != b.PARENT or candidate_binding.get('new_commit') != candidate
        or candidate_binding.get('default_off_public_flag') != {flag: False}):
        raise RuntimeError(key + ' default-off candidate binding differs')
    if key == 't16':
        gate = b.ROUND_ROOT / rid / f"gate_batch{body['batch']}.json"
        measured = json.loads(regular(gate).read_text())
        if measured.get('proposed_verdict') != 'kept' or measured.get('parent_commit') != b.PARENT or measured.get('new_commit') != candidate or len(measured.get('arms', [])) != 8:
            raise RuntimeError('T16 measured gate identity/coverage differs')
    return body


def cleanup_proof(doc):
    cp = b.ROOT / 'development/night_execution_20261009/D09_T16_RETRY1_OWNED_CLEANUP_READBACK.json'
    if doc.get('d09_cleanup') != {'path': str(cp), 'sha256': sha(regular(cp))}: raise RuntimeError('cleanup hash differs')
    c = json.loads(cp.read_text())
    launch = b.ROOT / 'runs/dev_T16' / f'launch_{b.D09_RID}_batch144.json'
    status = b.ROUND_ROOT / b.D09_RID / 'status_batch144.json'
    ld = json.loads(regular(launch).read_text()); sd = json.loads(regular(status).read_text())
    if (c.get('rid') != b.D09_RID or c.get('cleanup_ok') is not True or c.get('child_absent') != ld.get('child')
        or c.get('launch_sha256') != sha(launch) or c.get('status_sha256') != sha(status) or c.get('status') != sd
        or ld.get('rid') != b.D09_RID or ld.get('batch') != 144 or sd.get('batch') != 144
        or sd.get('rid') != b.D09_RID or sd.get('state') not in ('failed', 'complete_measurements_pending_review')
        or not c.get('owners') or c.get('gpu_compute_absent') is not True or c.get('gpu_lock_absent') is not True):
        raise RuntimeError('cleanup canonical producer binding differs')
    for owner in c['owners']:
        p = Path(owner['path'])
        if b.ROUND_ROOT / b.D09_RID not in p.parents or sha(regular(p)) != owner['sha256'] or owner.get('group_absent') is not True or owner.get('ports_rebound') is not True:
            raise RuntimeError('cleanup service owner binding differs')


def native_proof(doc):
    n = regular(HERE / 'd10_native_provenance_v2.json'); reuse = regular(HERE / 'ROOT_NATIVE_REUSE_V2.json')
    if doc.get('native_provenance') != {'path': str(n), 'sha256': sha(n)}: raise RuntimeError('native provenance binding differs')
    if sha(n) != '7c7aaaec99b8082b939eb7b03950db0d5d11444f0a8b3aac2175d45a96a14982' or sha(reuse) != 'de2f510f8734b5c5595b8d5a7c2308fa8bccea58fdb08acdbc55645e781f44b3': raise RuntimeError('native receipt differs')
    x = json.loads(n.read_text()); r = json.loads(reuse.read_text())
    if (x['candidate_commit'] != b.CANDIDATE or x['parent_commit'] != b.PARENT or x['reuse_receipt'] != str(reuse)
        or x['reuse_receipt_sha256'] != sha(reuse) or r['candidate_commit'] != b.CANDIDATE or r['base_commit'] != b.PARENT
        or r['native_source_diff_empty'] is not True or r['compiled'] is not False or len(r['files']) != 2): raise RuntimeError('native ABI receipt content differs')
    for record in r['files']:
        for key, wt in [('source', b.ROOT / 'wt/release-e2'), ('destination', b.WT)]:
            p = regular(record[key], readonly=False)
            if p.parent != wt / 'python/freetoken/kernel' or sha(p) != record['sha256'] or p.stat().st_size != record['size']: raise RuntimeError('native extension bytes differ')
    head = subprocess.check_output(['git', '-C', str(b.WT), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(b.WT), 'status', '--porcelain', '--untracked-files=no'], text=True)
    diff = subprocess.check_output(['git', '-C', str(b.WT), 'diff', '--name-only', b.PARENT, 'HEAD', '--', 'python/freetoken/kernel'], text=True)
    if head != b.CANDIDATE or dirty or diff: raise RuntimeError('candidate identity/native source differs')


def admission(path):
    doc = json.loads(regular(path).read_text())
    expected = {'schema': 'ft_d10_prototype_v10_admission/v1', 'admit': True, 'rid': RID, 'candidate': b.CANDIDATE, 'parent': b.PARENT,
                'flag': b.FLAG, 'calls_max': 8, 'services_max': 1, 'source_sha256': sources(), 'runner_source_sha256': b.runner().source_hashes()}
    if any(doc.get(k) != v for k, v in expected.items()): raise RuntimeError('V10 identity/source binding differs')
    round_proof(doc, 't16', b.T16_RID, b.CANDIDATE, 'd10_staggered_decode', {'kept'})
    round_proof(doc, 'd09', b.D09_RID, 'c17b69a46cd512fbf3d127d3879bce92caae457b', 'enable_message_boundary_ckpt', {'kept', 'not_met', 'failed_harness'})
    cleanup_proof(doc); native_proof(doc)
    svc = doc['service']; argv = svc['argv']; port = svc['api_port']; out = Path(doc['prototype_output'])
    if (type(port) is not int or not 1024 <= port <= 65534 or argv[:2] != ['ft', 'serve'] or b.FLAG not in argv or argv.count('--port') != 1
        or int(argv[argv.index('--port') + 1]) != port or svc['tcpstore_port'] != port + 1 or svc['endpoint'] != f'http://127.0.0.1:{port}'
        or svc['cwd'] != str(b.WT) or out != b.RUNS / RID): raise RuntimeError('V10 service/output scope differs')
    for name in ['production.active.json', 'production.cleanup_failed.json']:
        p = b.ROOT / 'run' / name
        if p.exists() or p.is_symlink(): raise RuntimeError('production marker prohibits prototype')
    return doc


def child_argv(admission_path, batch, receipt, output):
    return [str(b.ROOT / 'venv/bin/python'), str(Path(__file__).resolve()), '--run', '--owned-child', '--admission', str(admission_path),
            '--batch', str(batch), '--launch-receipt', str(receipt), '--worktree', str(b.WT), '--output-root', str(output)]


b.RID = RID
b.require_admission = admission
b.child_argv = child_argv
b.hashes = sources
b.filedry = lambda: {'schema': 'ft_d10_v10_filedry/v1', 'rid': RID, 'entrypoint': str(Path(__file__).resolve()),
                    'source_sha256': sources(), 'runner_source_sha256': b.runner().source_hashes(),
                    'gpu_started': False, 'http_started': False, 'service_started': False, 'compile_started': False}
controller = b.controller
child = b.child

if __name__ == '__main__': b.main()
