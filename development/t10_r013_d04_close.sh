set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import datetime, hashlib, json, os, pathlib, stat, subprocess
from types import ModuleType
d = pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R013').resolve(strict=True)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
review_source = pathlib.Path('/data2/FreeToken/runs/dev_D03/r013_close_inputs_ab48676/review_initial_metadata.json')
review_bytes = review_source.read_bytes()
review_sha = 'de10719d612984d4e0790ac7aaab74a3fb76ad5e4b61446bd14e689d01be9f3d'
if hashlib.sha256(review_bytes).hexdigest() != review_sha:
    raise ValueError('independent metadata review changed')
review = json.loads(review_bytes)
if (review['rid'],review['batch'],review['verdict']) != (d.name,45,'PASS'):
    raise ValueError('exact metadata PASS review required')
for name,digest in review['hashes'].items():
    if (d/name).is_symlink() or sha(d/name) != digest:
        raise ValueError('reviewed input changed: '+name)
if any((d/name).exists() for name in ('round.json','round_history','MANIFEST.sha256','review_initial_metadata.json')):
    raise ValueError('initial control or archived review already exists')
def load_bytes(path,name,expected):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('reviewed closure dependency changed: '+str(path))
    module = ModuleType(name); module.__file__ = str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__)
    return module
rollback = load_bytes(pathlib.Path('/data2/FreeToken/runs/dev_D03/d03_t16_close.py'),
    'r013_closure_rollback','f188e3cc7ba228cd76b4b9afe690ea4d7ed8f09a34fcaefba06e7f2ff431db04').rollback
closer = load_bytes(d/'initial_measurement_close_r013_parent.py','r013_initial_validation',
    'a05f4cb922e286a6d8e48a71b1e298d10a271480fe46b07009e27bb3ab14d758')
with (d/'review_initial_metadata.json').open('xb') as stream:
    stream.write(review_bytes)
now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
document = closer.validate(d,d.name,45,d/'initial_metadata.json',d/'review_initial_metadata.json',now)
expected_tools = {
    'round_json_append.py':'a4bd8b095bf718076f4d4b7f9ed8d6f5a96263b80e455ae2324d4f3c67601c91',
    'round_close.py':'e6fa3bc840c5c6e7c5fa43d4091bb5011932e6f856c2e0111ecdbe590f730c08',
    'round_close.sh':'6df87a2f2edfcbc985a2d593edb16349bf923e1f301939cdda1590d52d1f55f9'}
source = pathlib.Path('/data2/FreeToken/scripts')
payloads,versions = {},{}
for name,digest in expected_tools.items():
    if sha(source/name) != digest:
        raise ValueError('D04 tool changed: '+name)
    payloads[name] = (source/name).read_bytes()
    versions[name] = {'sha256':digest,'md5':hashlib.md5(payloads[name]).hexdigest()}
payloads['d04_tool_versions.json'] = closer.json_bytes(versions)
payloads['round.json'] = closer.json_bytes(document)
for name in payloads:
    if (d/name).exists():
        raise ValueError('closure target already exists: '+name)
modes = [(p,stat.S_IMODE(p.stat().st_mode),p.stat().st_dev,p.stat().st_ino) for p in [d,*d.rglob('*')]]
created = []
sealed = False
try:
    for name,content in payloads.items():
        path = d/name
        with path.open('xb') as stream:
            created.append((path,path.stat().st_dev,path.stat().st_ino)); stream.write(content)
    subprocess.run(['bash',str(d/'round_close.sh'),d.name,'--round-root',str(d.parent)],
        env={**os.environ,'FT_ROUND_PYTHON':'/data2/FreeToken/venv/bin/python'},check=True)
    sealed = True
except BaseException:
    if not sealed:
        rollback(d,created,modes)
    raise
subprocess.run(['/data2/FreeToken/venv/bin/python',str(d/'round_json_append.py'),str(d),'check'],check=True)
for line in (d/'MANIFEST.sha256').read_text().splitlines():
    digest,relative = line.split('  ',1); path = (d/relative).resolve()
    if d not in path.parents or sha(path) != digest:
        raise ValueError('sealed manifest mismatch: '+relative)
if (d/'round.json').read_bytes() != (d/'round_history/round.v001.json').read_bytes():
    raise ValueError('closed metadata and history differ')
if any(p.stat().st_mode & 0o222 for p in [d,*d.rglob('*')]):
    raise ValueError('closed round still writable')
if document['parent'] != 'E2-R017' or document['verdict'] != 'pending_review' or document['proposed_verdict'] is not None:
    raise ValueError('closed scientific or parent scope changed')
print('T10_R013_D04_CLOSED '+json.dumps({'rid':d.name,'batch':45,'closed_at':document['closed_at'],
    'parent':document['parent'],'round_sha256':sha(d/'round.json'),'manifest_sha256':sha(d/'MANIFEST.sha256'),
    'independent_review_sha256':sha(d/'review_initial_metadata.json'),'formal_verdict':document['verdict'],
    'scientific_classification':'pending; warm-prefix/final-ID K1 scope only'}))
PY
