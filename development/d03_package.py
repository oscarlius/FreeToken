"""Package only the D03 working-tree delta for CPU validation on the isolated candidate."""
import hashlib
import json
import pathlib
import subprocess
import tarfile

root = pathlib.Path(__file__).resolve().parent
worktree = root / 'e2d03'
names = subprocess.check_output(['git', 'diff', '--name-only'], cwd=worktree, text=True).splitlines()
names += subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], cwd=worktree, text=True).splitlines()
files = sorted(set(names))
output = root / 'd03-cpu-source.tar.gz'
with tarfile.open(output, 'w:gz') as archive:
    for name in files:
        source = worktree / name
        if not source.is_file() or '__pycache__' in source.parts:
            raise ValueError(f'unexpected package entry {name}')
        archive.add(source, arcname=name)
manifest = {name: hashlib.sha256((worktree / name).read_bytes()).hexdigest() for name in files}
(root / 'd03-cpu-source.sha256.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(f'D03 source delta packaged: {len(files)} files; sha256={hashlib.sha256(output.read_bytes()).hexdigest()}')
