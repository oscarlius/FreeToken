set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import datetime, hashlib, json, pathlib
from types import ModuleType
d = pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R013').resolve(strict=True)
stage = pathlib.Path('/data2/FreeToken/runs/dev_D03/r013_parent_3bf5f99')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
sources = {'d03_phase2_prepare_r013_parent.py':'3bf5f99fd0b87a60552bfdcf8e2b32774de703cc99cf9a583b76cd9915eaabf0',
           'initial_measurement_close_r013_parent.py':'a05f4cb922e286a6d8e48a71b1e298d10a271480fe46b07009e27bb3ab14d758'}
report = json.loads((stage/'cpu_validation.json').read_text())
if (len(report['steps']) != 2 or any(step['returncode'] for step in report['steps'])
        or report['log_sha256'] != sha(stage/'cpu_validation.log')
        or report['log_sha256'] != '1cc4834a81c3afd508af12e1fcdb10c2734c22a555c27b8a7f93ea247311f971'):
    raise ValueError('exact parent-provenance Linux CPU proof missing')
payloads = {}
for name, digest in sources.items():
    source = stage/'development'/name
    data = source.read_bytes()
    if source.is_symlink() or hashlib.sha256(data).hexdigest() != digest or source.stat().st_mode & 0o222:
        raise ValueError('parent-provenance source changed')
    payloads[name] = data
module = ModuleType('r013_parent_fix'); module.__file__ = str(stage/'development/d03_phase2_prepare_r013_parent.py')
exec(compile(payloads['d03_phase2_prepare_r013_parent.py'],module.__file__,'exec'),module.__dict__)
module.assert_owned(d)
old = d/'initial_metadata.json'
old_bytes = old.read_bytes()
old_identity = (old.stat().st_dev,old.stat().st_ino)
old_sha = hashlib.sha256(old_bytes).hexdigest()
if old_sha != 'db11e270b7c1de11cadc2e55e71a59f2dc60f021b0ca3a727dc9c6094784e180':
    raise ValueError('unsealed pre-fix metadata changed')
backup = d/'initial_metadata.before_parent_fix.json'
for name in ('round.json','round_history','MANIFEST.sha256','review_initial_metadata.json',backup.name,*sources):
    if (d/name).exists():
        raise ValueError('formal control or recovery artifact already exists: '+name)
module.verify_manifest(d)
module.validate_admission(d,module.SPECS[d.name],45)
module.validate_status(d,module.SPECS[d.name],45)
module.validate_measurement(d,module.SPECS[d.name])
for name,data in payloads.items():
    with (d/name).open('xb') as stream:
        stream.write(data)
with backup.open('xb') as stream:
    stream.write(old_bytes)
backup.chmod(0o444)
if sha(old) != old_sha or (old.stat().st_dev,old.stat().st_ino) != old_identity:
    raise ValueError('metadata identity changed during recovery')
old.unlink()
result = module.prepare(d,45,d/'review_raw_measurements.json')
document = json.loads((d/'initial_metadata.json').read_text())
if document['parent'] != 'E2-R017':
    raise ValueError('regenerated parent differs from actual phase parent')
result.update(recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
              old_metadata_sha256=old_sha,old_metadata_backup=backup.name,
              new_parent=document['parent'],preparer_sha256=sources['d03_phase2_prepare_r013_parent.py'],
              closer_sha256=sources['initial_measurement_close_r013_parent.py'])
with (d/'metadata_parent_fix.json').open('x') as stream:
    stream.write(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,sort_keys=True))
PY
