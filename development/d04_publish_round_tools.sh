set -euo pipefail
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, json, os, pathlib, stat
root=pathlib.Path('/data2/FreeToken')
source=root/'runs/dev_D04/candidate/scripts'
target=root/'scripts'
assert target.is_dir() and not target.is_symlink() and target.stat().st_uid==os.getuid()
expected={'round_json_append.py':'88178a9a3c83dec204e90e6dcf8c4db9',
          'round_close.py':'415aa82b34c8fd82d09bfe8a8ce67eed',
          'round_close.sh':'430693122ef66bb5a293fb421ff0f7fc'}
record=root/'runs/dev_D04/publish_new_round_tools_20261004.json'
assert not record.exists()
payloads={}
for name,digest in expected.items():
 data=(source/name).read_bytes()
 assert hashlib.md5(data).hexdigest()==digest,name
 assert not (target/name).exists() and not (target/name).is_symlink(),name
 payloads[name]=data
created=[]
try:
 for name,data in payloads.items():
  p=target/name
  with p.open('xb') as f:
   created.append(p)
   f.write(data)
  p.chmod(0o755 if name.endswith('.sh') else 0o644)
  assert hashlib.md5(p.read_bytes()).hexdigest()==expected[name]
 result={'status':'published','source_package_sha256':'6bb1e69111812367b2accab7b5f3075d9592f904d53d55b740fae4ea735b4b77',
         'tools':{name:{'md5':expected[name],'sha256':hashlib.sha256(data).hexdigest()} for name,data in payloads.items()},
         'real_round_used':'E2-R006','comparison_scripts':'unchanged pending baseline/T16 gates'}
 with record.open('x') as f:
  json.dump(result,f,indent=2)
 print(json.dumps(result,indent=2))
 print('PUBLICATION_RECORD_SHA256',hashlib.sha256(record.read_bytes()).hexdigest())
except BaseException:
 for p in reversed(created):
  if p.is_file() and p.stat().st_uid==os.getuid() and p.read_bytes()==payloads[p.name]:
   p.unlink()
 raise
PY
/data2/FreeToken/venv/bin/python /data2/FreeToken/scripts/round_json_append.py /data2/_shared/runs/ft_rounds/E2-R006 check
