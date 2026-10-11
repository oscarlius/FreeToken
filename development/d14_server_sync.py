"""Synchronize the local D14 commit into its dedicated server worktree."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]
package = json.loads((ROOT/'development/d14_candidate_commit.json').read_text())
bundle = ROOT/'development/e2d14_e4f3202.bundle'
assert hashlib.sha256(bundle.read_bytes()).hexdigest() == package['bundle_sha256']
stage = '/data2/FreeToken/runs/dev_D14/source_e4f3202'
subprocess.run(['ssh','-o','BatchMode=yes','9','mkdir', '-p',stage],check=True)
subprocess.run(['scp','-l','36000',str(bundle),'9:'+stage+'/candidate.bundle'],check=True)
program = r'''
import hashlib,json,pathlib,subprocess,sys
data=json.load(sys.stdin);root=pathlib.Path('/data2/FreeToken');repo=root/'wt/e2base';stage=pathlib.Path(data['stage']);bundle=stage/'candidate.bundle'
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert digest(bundle)==data['package']['bundle_sha256']
commit=data['package']['commit'];parent=data['package']['parent'];branch=data['package']['branch'];tree=pathlib.Path(data['package']['server_tree'])
assert not tree.exists()
ref=subprocess.run(['git','-C',str(repo),'show-ref','--verify','--quiet','refs/heads/'+branch],capture_output=True,text=True)
assert ref.returncode==1,('candidate ref lookup must prove absence',ref.returncode,ref.stderr)
subprocess.run(['git','-C',str(repo),'bundle','verify',str(bundle)],check=True,capture_output=True)
subprocess.run(['git','-C',str(repo),'fetch',str(bundle),'refs/heads/'+branch+':refs/heads/'+branch],check=True,capture_output=True)
subprocess.run(['git','-C',str(repo),'worktree','add',str(tree),branch],check=True,capture_output=True)
assert subprocess.check_output(['git','-C',str(tree),'rev-parse','HEAD'],text=True).strip()==commit
assert subprocess.check_output(['git','-C',str(tree),'show','-s','--format=%P','HEAD'],text=True).strip()==parent
for name,expected in data['package']['git_blob_sha256'].items():assert digest(tree/name)==expected,(name,digest(tree/name))
extensions={}
for name in ('_cpu_moe.cpython-310-x86_64-linux-gnu.so','_pinned_tensor.cpython-310-x86_64-linux-gnu.so'):
 relative='python/freetoken/kernel/'+name;source=repo/relative
 assert source.exists()
 (tree/relative).symlink_to(source)
 extensions[relative]={'source':str(source),'sha256':digest(source)}
assert not subprocess.check_output(['git','-C',str(tree),'status','--porcelain','--untracked-files=no']).strip()
report={'schema':'ft_d14_server_source/v1','commit':commit,'parent':parent,'tree':str(tree),'branch':branch,
 'git_blob_sha256':data['package']['git_blob_sha256'],'compiled_extensions':extensions,'gpu_started':False}
(stage/'source_report.json').write_text(json.dumps(report,indent=2)+'\n')
for p in [stage,*stage.iterdir()]:p.chmod(p.stat().st_mode&~0o222)
print(json.dumps(report))
'''
result=subprocess.run(['ssh','-o','BatchMode=yes','9','/data2/FreeToken/venv/bin/python','-c',shlex.quote(program)],
    input=json.dumps({'stage':stage,'package':package}).encode(),capture_output=True)
if result.returncode:
    print(result.stderr.decode(errors='replace'));raise SystemExit(result.returncode)
report=json.loads(result.stdout)
(ROOT/'development/d14_server_source.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report))
