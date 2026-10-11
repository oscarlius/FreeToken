"""Verify reviewed LF Git blobs and package only the D14 source commit."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
tree = ROOT/'development/e2d14'
git = lambda *args:subprocess.check_output(['git','-C',str(tree),*args])
commit = git('rev-parse','HEAD').decode().strip()
parent = git('show','-s','--format=%P','HEAD').decode().strip()
assert commit == 'e4f32022a5aa4d8734d87d9f6eb15e98c1edde42'
assert parent == '23f2e2caa3395837c9474735ffc83321f3b9b5a1'
assert not git('status','--porcelain').strip()
cpu = json.loads((ROOT/'development/d14_cpu_before_after.json').read_text())
files = {name:hashlib.sha256(git('show','HEAD:'+name)).hexdigest() for name in ['README.md',*cpu['files']]}
assert all(files[name] == digest for name,digest in cpu['files'].items())
assert cpu['steps'][0]['returncode'] == 1 and cpu['steps'][1]['returncode'] == 0
bundle = ROOT/'development/e2d14_e4f3202.bundle'
if bundle.exists():
    raise SystemExit('bundle already exists; inspect before replacement')
subprocess.run(['git','-C',str(tree),'bundle','create',str(bundle),'fix/e2-ngram-track','^'+parent],check=True)
record = {'schema':'ft_d14_source_package/v1','commit':commit,'parent':parent,
    'branch':'fix/e2-ngram-track','server_tree':'/data2/FreeToken/wt/e2d14','git_blob_sha256':files,
    'bundle':str(bundle),'bundle_sha256':hashlib.sha256(bundle.read_bytes()).hexdigest(),
    'cpu_report_sha256':hashlib.sha256((ROOT/'development/d14_cpu_before_after.json').read_bytes()).hexdigest(),
    'gpu_validated':False}
(ROOT/'development/d14_candidate_commit.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print(json.dumps(record))
