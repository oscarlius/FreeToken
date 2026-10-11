set -euo pipefail
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python - <<'PY'
import datetime, hashlib, importlib.util, json, os, pathlib, stat, subprocess
d = pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R017').resolve(strict=True)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
expected_inputs = {
    'review_raw_measurements.json': '292a8262f211da3dc758bff786b7c04f7055388bb7336f1efc7e599e31b2d4ed',
    'poststop_proof.json': '53f02a2a07a0f80d21a37f70567aa1dc243b465462eafad6f0b3ae8280a92d69',
    'initial_metadata.json': '6b10e5f3913aea700d799c587a6a4bcb8a81feba03a9396f26915235c4a939fc',
    'review_initial_metadata.json': '0a2eebdd9dc6872cfce8450823e8ceb596fc046ecf3f316847dcd1fa91ab0e99',
    'initial_measurement_close.py': 'dbfecaee0c31fa1a7057a922e2c8e09944cdb8c51f22fe1e6fb6b8e6b3329835',
}
review_source = pathlib.Path('/data2/FreeToken/runs/dev_D03/r017_close_inputs/review_initial_metadata.json')
review_bytes = review_source.read_bytes()
assert hashlib.sha256(review_bytes).hexdigest() == expected_inputs['review_initial_metadata.json']
assert not (d / 'review_initial_metadata.json').exists()
for name, digest in expected_inputs.items():
    if name != 'review_initial_metadata.json':
        assert sha(d / name) == digest, name
with (d / 'review_initial_metadata.json').open('xb') as stream:
    stream.write(review_bytes)
assert sha(d / 'review_initial_metadata.json') == expected_inputs['review_initial_metadata.json']
def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
rollback_path = pathlib.Path('/data2/FreeToken/runs/dev_D03/d03_t16_close.py')
assert sha(rollback_path) == 'f188e3cc7ba228cd76b4b9afe690ea4d7ed8f09a34fcaefba06e7f2ff431db04'
rollback = load(rollback_path, 'reviewed_closure_rollback').rollback
closer = load(d / 'initial_measurement_close.py', 'reviewed_initial_validation')
now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
document = closer.validate(d, d.name, 44, d / 'initial_metadata.json', d / 'review_initial_metadata.json', now)
expected_tools = {
    'round_json_append.py': 'a4bd8b095bf718076f4d4b7f9ed8d6f5a96263b80e455ae2324d4f3c67601c91',
    'round_close.py': 'e6fa3bc840c5c6e7c5fa43d4091bb5011932e6f856c2e0111ecdbe590f730c08',
    'round_close.sh': '6df87a2f2edfcbc985a2d593edb16349bf923e1f301939cdda1590d52d1f55f9',
}
source = pathlib.Path('/data2/FreeToken/scripts')
payloads, versions = {}, {}
for name, digest in expected_tools.items():
    assert sha(source / name) == digest, name
    payloads[name] = (source / name).read_bytes()
    versions[name] = {'sha256': digest, 'md5': hashlib.md5(payloads[name]).hexdigest()}
payloads['d04_tool_versions.json'] = closer.json_bytes(versions)
payloads['round.json'] = closer.json_bytes(document)
for name in payloads:
    assert not (d / name).exists(), name
modes = [(p, stat.S_IMODE(p.stat().st_mode), p.stat().st_dev, p.stat().st_ino) for p in [d, *d.rglob('*')]]
created = []
sealed = False
try:
    for name, content in payloads.items():
        path = d / name
        with path.open('xb') as stream:
            created.append((path, path.stat().st_dev, path.stat().st_ino))
            stream.write(content)
    subprocess.run(['bash', str(d / 'round_close.sh'), d.name, '--round-root', str(d.parent)],
                   env={**os.environ, 'FT_ROUND_PYTHON': '/data2/FreeToken/venv/bin/python'}, check=True)
    sealed = True
except BaseException:
    if not sealed:
        rollback(d, created, modes)
    raise
subprocess.run(['/data2/FreeToken/venv/bin/python', str(d / 'round_json_append.py'), str(d), 'check'], check=True)
for line in (d / 'MANIFEST.sha256').read_text().splitlines():
    digest, relative = line.split('  ', 1)
    path = (d / relative).resolve()
    assert d in path.parents and sha(path) == digest, relative
assert (d / 'round.json').read_bytes() == (d / 'round_history/round.v001.json').read_bytes()
assert all(not p.stat().st_mode & 0o222 for p in [d, *d.rglob('*')])
assert document['verdict'] == 'pending_review' and document['proposed_verdict'] is None
print('T10_R017_D04_CLOSED', json.dumps({'rid': d.name, 'batch': 44, 'closed_at': document['closed_at'],
    'round_sha256': sha(d / 'round.json'), 'manifest_sha256': sha(d / 'MANIFEST.sha256'),
    'independent_review_sha256': sha(d / 'review_initial_metadata.json'),
    'formal_verdict': document['verdict'], 'scientific_classification': 'pending_stage2_fresh_logits'}))
PY
