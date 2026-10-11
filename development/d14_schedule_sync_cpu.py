"""Sync a local committed candidate into its dedicated WT and run Linux CPU gates."""
from __future__ import annotations

import base64
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
TREE = HERE / "e2d14-schedule"
PARENT = "e4f32022a5aa4d8734d87d9f6eb15e98c1edde42"

PROGRAM = r'''
import base64,hashlib,json,os,pathlib,subprocess,sys
data=json.load(sys.stdin)
stage=pathlib.Path(data['stage']); stage.mkdir(parents=True,exist_ok=False)
parent=pathlib.Path('/data2/FreeToken/wt/e2d14'); tree=parent.with_name('e2d14-schedule')
py='/data2/FreeToken/venv/bin/python'
report={'schema':'ft_d14_schedule_cpu/v1','gpu_started':False,'candidate_commit':data['commit'],'tree':data['tree'],'stage':str(stage),'worktree':str(tree),'steps':{}}
def cmd(argv,**kw): return subprocess.check_output(argv,text=True,**kw).strip()
try:
 previous=data.get('previous')
 if tree.exists():
  if not previous:raise FileExistsError('dedicated worktree already exists; exact previous receipt required')
  proof_path=pathlib.Path(previous['stage'])/'cpu_validation.json'
  if proof_path.is_symlink() or proof_path.stat().st_mode & 0o222 or hashlib.sha256(proof_path.read_bytes()).hexdigest()!=previous['report_sha256']:raise ValueError('previous CPU proof differs')
  proof=json.loads(proof_path.read_bytes())
  if proof['worktree']!=str(tree) or proof['candidate_commit']!=previous['commit'] or proof['tree']!=previous['tree']:raise ValueError('previous candidate binding differs')
  if cmd(['git','-C',str(tree),'rev-parse','HEAD'])!=previous['commit'] or cmd(['git','-C',str(tree),'rev-parse','HEAD^{tree}'])!=previous['tree'] or cmd(['git','-C',str(tree),'status','--porcelain','--untracked-files=no']):raise ValueError('dedicated source changed since previous CPU proof')
 if cmd(['git','-C',str(parent),'rev-parse','HEAD'])!=data['parent'] or cmd(['git','-C',str(parent),'status','--porcelain','--untracked-files=no']): raise ValueError('clean source parent differs')
 bundle=stage/'candidate.bundle'; raw=base64.b64decode(data['bundle'])
 if hashlib.sha256(raw).hexdigest()!=data['bundle_sha256']: raise ValueError('bundle transport differs')
 bundle.write_bytes(raw)
 subprocess.run(['git','-C',str(parent),'bundle','verify',str(bundle)],check=True,capture_output=True)
 subprocess.run(['git','-C',str(parent),'fetch',str(bundle),'HEAD'],check=True,capture_output=True)
 if cmd(['git','-C',str(parent),'rev-parse',data['commit']+'^{tree}'])!=data['tree']:raise ValueError('fetched candidate tree differs')
 if tree.exists():
  subprocess.run(['git','-C',str(tree),'checkout','--detach',data['commit']],check=True,capture_output=True)
 else:
  subprocess.run(['git','-C',str(parent),'worktree','add','--detach',str(tree),data['commit']],check=True,capture_output=True)
 extensions={}
 for name in ('_cpu_moe.cpython-310-x86_64-linux-gnu.so','_pinned_tensor.cpython-310-x86_64-linux-gnu.so'):
  source=(parent/'python/freetoken/kernel'/name).resolve(strict=True)
  target=tree/'python/freetoken/kernel'/name
  if not source.is_file():raise ValueError('extension source missing')
  if target.exists() or target.is_symlink():
   if not previous or not target.is_symlink() or target.resolve()!=source:raise ValueError('extension collision')
  else: target.symlink_to(source)
  extensions[name]={'target':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
 report['extensions']=extensions
 env=dict(os.environ,CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',TOKENIZERS_PARALLELISM='false',PYTHONPATH=str(tree/'python')+':'+str(tree/'scripts'))
 for key in list(env):
  if key.startswith(('FT_DEV_','FT_D3_','FT_T17_')):env.pop(key)
 env['PATH']='/usr/local/cuda-13.0/bin:/data2/FreeToken/venv/bin:'+env.get('PATH','')
 env['LD_LIBRARY_PATH']='/usr/local/cuda-13.0/lib64:'+env.get('LD_LIBRARY_PATH','')
 commands={
  'scheduler':[py,'-m','pytest','-q','-p','no:cacheprovider','tests/scheduler/test_dev_prefill_schedule.py','tests/scheduler/test_prefill_d0_metadata.py','tests/scheduler/test_switch_defaults.py','tests/scheduler/test_scheduler_chunked_prefill.py'],
  'engine':[py,'-m','pytest','-q','-p','no:cacheprovider','tests/engine/test_layer_major_tracks.py'],
  'd0':[py,'-m','pytest','-q','-p','no:cacheprovider','tests/moe/test_d0_fields.py'],
  'tools':[py,'-m','pytest','-q','-p','no:cacheprovider','tests/scripts/test_equiv_suite.py'],
  'import':[py,'-c','import freetoken,torch; print(freetoken.__file__,torch.__version__); assert not torch.cuda.is_initialized()']}
 for name,argv in commands.items():
  process=subprocess.run(argv,cwd=tree,env=env,capture_output=True,timeout=180)
  log=stage/(name+'.log');log.write_bytes(process.stdout+process.stderr)
  report['steps'][name]={'argv':argv,'returncode':process.returncode,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'stdout':process.stdout.decode(errors='replace'),'stderr':process.stderr.decode(errors='replace')}
  if process.returncode:raise RuntimeError('CPU gate failed: '+name)
 if cmd(['git','-C',str(tree),'rev-parse','HEAD'])!=data['commit'] or cmd(['git','-C',str(tree),'rev-parse','HEAD^{tree}'])!=data['tree'] or cmd(['git','-C',str(tree),'status','--porcelain','--untracked-files=no']):raise ValueError('candidate changed during CPU test')
 report['source_files']={name:hashlib.sha256((tree/name).read_bytes()).hexdigest() for name in cmd(['git','-C',str(tree),'diff','--name-only',data['parent'],data['commit']]).splitlines()}
 report['verdict']='PASS'
except BaseException as exc:
 report['verdict']='FAIL';report['error']=repr(exc)
finally:
 (stage/'cpu_validation.json').write_text(json.dumps(report,indent=2)+'\n')
 for path in reversed([stage,*sorted(stage.rglob('*'))]):
  if path.is_symlink():raise ValueError('unexpected symlink in frozen CPU stage')
  path.chmod(path.stat().st_mode & ~0o222)
print(json.dumps({'stage':str(stage),'report':report,'report_sha256':hashlib.sha256((stage/'cpu_validation.json').read_bytes()).hexdigest()}))
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous-receipt', type=Path)
    args = parser.parse_args()
    def git(*args):
        return subprocess.check_output(["git", "-C", str(TREE), *args], text=True).strip()
    if git("status", "--porcelain"):
        raise ValueError("commit the complete local candidate first")
    commit, tree = git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")
    bundle = HERE / ("d14_schedule_" + commit[:12] + ".bundle")
    if bundle.exists():
        raise FileExistsError(bundle)
    subprocess.run(["git", "-C", str(TREE), "bundle", "create", str(bundle), "HEAD", "^" + PARENT], check=True)
    raw = bundle.read_bytes()
    identity = hashlib.sha256(raw + PROGRAM.encode()).hexdigest()
    payload = {"commit": commit, "tree": tree, "parent": PARENT, "bundle_sha256": hashlib.sha256(raw).hexdigest(),
               "bundle": base64.b64encode(raw).decode(), "stage": "/data2/FreeToken/runs/dev_D14/schedule_cpu_" + identity[:12]}
    if args.previous_receipt:
        previous = json.loads(args.previous_receipt.read_bytes())
        payload['previous'] = {'stage': previous['stage'], 'report_sha256': previous['report_sha256'],
                               'commit': previous['report']['candidate_commit'], 'tree': previous['report']['tree']}
    wire = "import io,sys\nsys.stdin=io.StringIO(" + repr(json.dumps(payload)) + ")\n" + PROGRAM
    process = subprocess.run(["ssh", "-o", "BatchMode=yes", "9", "/data2/FreeToken/venv/bin/python", "-"],
                             input=wire.encode(), capture_output=True)
    if process.returncode:
        raise RuntimeError(process.stderr.decode(errors="replace"))
    result = json.loads(process.stdout)
    result["controller"] = {"program": PROGRAM, "program_sha256": hashlib.sha256(PROGRAM.encode()).hexdigest(),
                            "bundle_sha256": payload["bundle_sha256"]}
    target = HERE / ("d14_schedule_cpu_" + identity[:12] + ".json")
    with target.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({"receipt": str(target), "stage": result["stage"], "verdict": result["report"]["verdict"],
                      "steps": {k: {"returncode": v["returncode"], "stdout": v["stdout"]} for k, v in result["report"]["steps"].items()}}))
    if result["report"]["verdict"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
