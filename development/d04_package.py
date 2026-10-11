import hashlib
import json
import pathlib
import tarfile

root = pathlib.Path(__file__).resolve().parent.parent
names = ['scripts/round_json_append.py', 'scripts/round_close.py', 'scripts/round_close.sh',
         'scripts/state_eq.py', 'scripts/agent_trace.py', 'scripts/serve_args_diff.py',
         'scripts/tests/test_round_json_append.py', 'scripts/tests/test_round_close.py',
         'scripts/tests/test_state_eq_label.py']
manifest = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names}
manifest['original/state_eq.py'] = hashlib.sha256((root / 'development/d04_original/state_eq.py').read_bytes()).hexdigest()
output = root / 'development/d04-source.tar.gz'
with tarfile.open(output, 'w:gz') as archive:
    for name in names:
        archive.add(root / name, arcname=name)
    archive.add(root / 'development/d04_original/state_eq.py', arcname='original/state_eq.py')
(root / 'development/d04-source.sha256.json').write_text(json.dumps(manifest, indent=2))
print('D04 package SHA256', hashlib.sha256(output.read_bytes()).hexdigest())
