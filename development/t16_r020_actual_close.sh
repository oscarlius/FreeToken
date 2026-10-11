set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import datetime,hashlib,json,os,pathlib,subprocess,sys
stage=pathlib.Path('/data2/FreeToken/runs/dev_D06/t16_r020_closure_54ff603')
directory=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R020-gate-D06')
proof_path=stage.parent/'t16_r020_actual_closure_proof.json'
expected={
 't16_r020_prepare.py':'b1147d9fd9924739445b1cfed5c5033484e3bd069f89d18ac326a80899fd747e',
 't16_r020_close.py':'54ff60330437c04d25d4b9f3a5a2845cc69327bf5fe8464ce5195a5aa295bb3f',
 'tests/test_t16_r020_close.py':'7b89ca23c5bf4a43f0f9a53333937349d08cf660cacdde46b84b72fdb13d4093',
 't16_r020_raw_review.json':'67a895cc4e6913e6e5530fa3a4b20ed13e9a1d2fc4bfeabde4713c98375c3dc4',
 'cpu_validation.log':'ee595fb1a1cdf2b361a3ce682d95b70d256205204316aacabfce141f03d797f3',
 'cpu_validation.json':'efcfb1777d4ea0e42cdfe5e11c0947d73f4ef05ae46cd32944e04ad3a5d8506c',
}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for name,digest in expected.items():
 path=stage/name
 if path.is_symlink() or path.stat().st_uid!=os.geteuid() or path.stat().st_mode&0o222 or sha(path)!=digest:
  raise ValueError('reviewed readonly source or CPU proof changed: '+name)
report=json.loads((stage/'cpu_validation.json').read_text())
if (any(s['returncode'] for s in report['steps']) or report['gpu_started'] is not False
 or report['original_round_mutated'] is not False or report['fixture_canonical_override'] is not True
 or report['round_sha256']!='bdbd059929e131eef6dfd0f67ce888fddd1cf7bfca6e89d3eba0c53f8395e06c'
 or report['manifest_sha256']!='57dde8dd83591a890750f71348aa07bec67a6ee29ff8763eb0b0b43b5a46c99a'):
 raise ValueError('reviewed private CPU closure proof differs')
for p in [directory,*directory.rglob('*')]:
 if p.is_symlink() or p.stat().st_uid!=os.geteuid():raise ValueError('foreign round owner or symlink')
copies={'t16_r020_prepare.py':'closure_preparer.py','t16_r020_close.py':'closure_runner.py',
 't16_r020_raw_review.json':'review_batch48.json','cpu_validation.json':'closure_cpu_fixture_validation.json'}
if proof_path.exists() or proof_path.is_symlink() or any((directory/n).exists() or (directory/n).is_symlink()
 for n in ['round.json','round_history','MANIFEST.sha256','initial_metadata.json','closure_metadata_review.json',*copies.values()]):
 raise FileExistsError('existing closure evidence retained; do not rerun')
approval={'schema':'ft_independent_closure_review/v1','reviewer':'/root/d06_server_review',
 'recorded_by':'mainline_owner','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'recommendation':'APPROVE','rid':directory.name,'batch':48,'sources':expected,
 'scope':'source, frozen raw review, private Linux D04 pipeline, and metadata binding; not formal acceptance',
 'private_copy_round_sha256':report['round_sha256'],'private_copy_manifest_sha256':report['manifest_sha256'],
 'formal_verdict':'pending_review','parent':'E2-pre-gate-D00',
 'base_commit':'23f2e2caa3395837c9474735ffc83321f3b9b5a1',
 'candidate_commit':'03692633df48456fb0baa78de7b64e5628a12ab1'}
for source,target in copies.items():
 with (directory/target).open('xb') as stream:stream.write((stage/source).read_bytes())
with (directory/'closure_metadata_review.json').open('x') as stream:
 stream.write(json.dumps(approval,indent=2)+'\n')
argv=[sys.executable,str(stage/'t16_r020_close.py'),'--close','--round-dir',str(directory),'--root','/data2/FreeToken']
result=subprocess.run(argv,check=True,text=True,capture_output=True,timeout=120)
print(result.stdout)
metadata=json.loads((directory/'round.json').read_text())
proof={'rid':directory.name,'batch':48,'closed_at':metadata['closed_at'],
 'formal_verdict':metadata['verdict'],'parent':metadata['parent'],
 'manifest_sha256':sha(directory/'MANIFEST.sha256'),'round_sha256':sha(directory/'round.json'),
 'raw_review_sha256':expected['t16_r020_raw_review.json'],
 'closure_metadata_review_sha256':sha(directory/'closure_metadata_review.json'),
 'closure_runner_sha256':expected['t16_r020_close.py'],
 'fixture_override':False,'gpu_started':False,'original_round_sealed':True}
with proof_path.open('x') as stream:
 stream.write(json.dumps(proof,indent=2)+'\n');stream.flush();os.fsync(stream.fileno())
proof_path.chmod(0o444)
print(json.dumps(proof))
PY
