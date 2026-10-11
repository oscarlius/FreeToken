set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib,subprocess,sys
directory=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R018-gate-D03')
patch=pathlib.Path('/data2/FreeToken/runs/dev_D04/r018_epoch_metadata_add.json')
writer=pathlib.Path('/data2/FreeToken/scripts/round_json_append.py')
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
if patch.is_symlink() or sha(patch)!='cb8a0e10eb6dbad5753e3b2a19388edb0f3ed2e30a71b769983c228557246baa':raise ValueError('reviewed additive patch changed')
if hashlib.md5(writer.read_bytes()).hexdigest()!='88178a9a3c83dec204e90e6dcf8c4db9':raise ValueError('published D04 writer changed')
old=directory.joinpath('round.json').read_bytes()
if hashlib.sha256(old).hexdigest()!='99517fb399c8adf758e2b50a63bedabf7b5c5fb322d8795c2e4fc0d33a940ca7':raise ValueError('actual first snapshot changed')
manifest='e7b63c0ec3c4b2d53d42663581af9bcd86de21dd3cf9748fc450c3b19b80f142'
if sha(directory/'MANIFEST.sha256')!=manifest:raise ValueError('sealed manifest changed')
subprocess.run(['git','-C','/data2/FreeToken/wt/e1r003st','merge-base','--is-ancestor',
 '23f2e2caa3395837c9474735ffc83321f3b9b5a1','c30ae0d7003c3bbbf56867ce74da797332fa7ed5'],check=True)
subprocess.run([sys.executable,str(writer),str(directory),'check'],check=True)
subprocess.run([sys.executable,str(writer),str(directory),'add','--json',str(patch)],check=True)
subprocess.run([sys.executable,str(writer),str(directory),'check'],check=True)
current=directory.joinpath('round.json').read_bytes();new=json.loads(current)
applied=json.loads(patch.read_text())
for key,value in applied['base'].items():
 if new['base'].pop(key)!=value:raise ValueError('appended epoch field differs')
if new.pop('metadata_reconciliation')!=applied['metadata_reconciliation'] or new!=json.loads(old):
 raise ValueError('original metadata fields changed')
if (directory/'round_history/round.v001.json').read_bytes()!=old:raise ValueError('original history changed')
if (directory/'round_history/round.v002.json').read_bytes()!=current:raise ValueError('new history differs')
if sha(directory/'MANIFEST.sha256')!=manifest:raise ValueError('raw manifest changed')
for line in (directory/'MANIFEST.sha256').read_text().splitlines():
 digest,relative=line.split('  ',1)
 if sha(directory/relative)!=digest:raise ValueError('raw artifact changed: '+relative)
if any(p.stat().st_mode&0o222 for p in [directory,*directory.rglob('*')]):raise ValueError('writable sealed entry')
proof={'rid':directory.name,'round_sha256':hashlib.sha256(current).hexdigest(),
 'v001_sha256':hashlib.sha256(old).hexdigest(),'v002_sha256':sha(directory/'round_history/round.v002.json'),
 'manifest_sha256':manifest,'patch_sha256':sha(patch),'history_versions':2,
 'formal_verdict':new['verdict'],'measurement_fields_preserved':True,
 'reviewer':'/root/d06_server_review','gpu_started':False}
with patch.with_name('r018_epoch_metadata_append_proof.json').open('x') as stream:
 stream.write(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))
PY
