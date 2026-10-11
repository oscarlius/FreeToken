set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, json, os, pathlib, subprocess, sys
stage=pathlib.Path('/data2/FreeToken/runs/dev_D03/t16_r018_closure_05aacfd')
directory=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R018-gate-D03')
expected={
 't16_r018_prepare.py':'e5fbdd372be56792b4ee89dbb297c82461f22a7d60eaaab48da9b8e070acc2da',
 't16_r018_close.py':'05aacfdf34c1bdf22a8aa84b84bec12ebedb128daf2d745eb30ad7f6b0cb8578',
 't16_r018_raw_review.json':'6c2a90d98c028ceaeff90d78a85e6eb75b368982a3114f2b6eed1524ea787243',
 'cpu_validation.log':'f1d6e85603e2622c91fda724e5d7d8bd5bdc9dfedcf03015f4c789a1392f17c8',
}
for name,digest in expected.items():
 path=stage/name
 if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
  raise ValueError('reviewed closure source or CPU evidence changed: '+name)
report=json.loads((stage/'cpu_validation.json').read_text())
if any(s['returncode'] for s in report['steps']) or report['gpu_started'] is not False or report['original_round_mutated'] is not False or report['fixture_canonical_override'] is not True:
 raise ValueError('private-stage CPU closure proof differs')
for p in [directory,*directory.rglob('*')]:
 if p.is_symlink() or p.stat().st_uid!=os.geteuid():raise ValueError('foreign round owner or symlink')
copies={'t16_r018_prepare.py':'closure_preparer.py','t16_r018_close.py':'closure_runner.py',
        't16_r018_raw_review.json':'review_batch46.json','cpu_validation.json':'closure_cpu_fixture_validation.json'}
if any((directory/n).exists() for n in ['round.json','round_history','MANIFEST.sha256','initial_metadata.json','closure_metadata_review.json',*copies.values()]):
 raise FileExistsError('existing closure artifacts retained; do not rerun')
approval={'schema':'ft_independent_closure_review/v1','reviewer':'/root/d06_server_review',
 'recorded_by':'mainline_owner','recommendation':'APPROVE',
 'scope':'source, frozen raw review, private Linux D04 pipeline, and metadata binding; not formal or scientific acceptance',
 'rid':directory.name,'batch':46,'sources':expected,
 'private_copy_round_sha256':'9a6c081c88a4415d4483aa934d5ffa33f04373d409397b3299e0e1dc744dd576',
 'private_copy_manifest_sha256':'0337c5b8bdcc571e7d14245b41029f74f0ae21318b0bdcd02b70fe15e51a4ad5',
 'formal_verdict':'pending_review','parent':'E2-R002-gate-D03',
 'base_commit':'c30ae0d7003c3bbbf56867ce74da797332fa7ed5',
 'candidate_commit':'f5067bbe05da51d5f78185213435a8be095a684a'}
for source,target in copies.items():
 with (directory/target).open('xb') as stream:stream.write((stage/source).read_bytes())
with (directory/'closure_metadata_review.json').open('x') as stream:
 stream.write(json.dumps(approval,indent=2)+'\n')
argv=[sys.executable,str(stage/'t16_r018_close.py'),'--close','--round-dir',str(directory),'--root','/data2/FreeToken']
result=subprocess.run(argv,check=True,text=True,capture_output=True,timeout=120)
print(result.stdout)
metadata=json.loads((directory/'round.json').read_text())
proof={'rid':directory.name,'batch':46,'closed_at':metadata['closed_at'],
 'formal_verdict':metadata['verdict'],'parent':metadata['parent'],
 'manifest_sha256':hashlib.sha256((directory/'MANIFEST.sha256').read_bytes()).hexdigest(),
 'round_sha256':hashlib.sha256((directory/'round.json').read_bytes()).hexdigest(),
 'raw_review_sha256':expected['t16_r018_raw_review.json'],
 'closure_metadata_review_sha256':hashlib.sha256((directory/'closure_metadata_review.json').read_bytes()).hexdigest(),
 'fixture_override':False,'gpu_started':False,'original_round_sealed':True}
with (stage/'actual_closure_proof.json').open('x') as stream:
 stream.write(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))
PY
