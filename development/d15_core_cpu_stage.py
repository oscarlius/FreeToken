"""Freeze a clean D15 core CPU regression stage without exposing CUDA devices."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


REMOTE = r'''
import base64, hashlib, json, os, pathlib, re, stat, subprocess, sys
p = json.loads(sys.stdin.read())
wt, stage = pathlib.Path(p['worktree']), pathlib.Path(p['stage'])
tests = ['tests/scheduler', 'tests/kvcache', 'tests/engine', 'tests/models/qwen4_exp']
paths = ['python/freetoken', *tests, 'tests/conftest.py']
expected = ['tests/scheduler/test_abort_inflight_prefill.py::test_prefix_commit_sentinel_guard', 'tests/scheduler/test_abort_inflight_prefill.py::test_post_terminal_overlap_step_is_dropped']
def sha(data): return hashlib.sha256(data).hexdigest()
def git(*args, text=True): return subprocess.check_output(['git', '-C', str(wt), *args], text=text)
def git_text(*args): return git(*args).strip()
def put(name, data):
    path = stage / name
    path.write_bytes(data)
    return path
if os.environ.get('CUDA_VISIBLE_DEVICES') not in (None, ''): raise RuntimeError('launcher exposed CUDA')
if not wt.is_dir() or wt.is_symlink(): raise RuntimeError('invalid worktree')
if git_text('rev-parse', 'HEAD') != p['candidate']: raise RuntimeError('candidate mismatch')
if git_text('status', '--porcelain'): raise RuntimeError('candidate dirty')
if stage.exists() or stage.is_symlink(): raise RuntimeError('stage exists')
stage.mkdir(mode=0o700, parents=True)
put('stage_tool.py', base64.b64decode(p['tool_b64']))
entries=[]
for line in git('ls-tree', '-r', '--full-tree', p['candidate'], '--', *paths).splitlines():
    meta, name = line.split('\t', 1); mode, kind, blob = meta.split()
    if kind != 'blob': continue
    local = wt / name
    if not local.is_file() or local.is_symlink(): raise RuntimeError('nonregular source: '+name)
    disk=local.read_bytes(); blob_data=subprocess.check_output(['git','-C',str(wt),'show',p['candidate']+':'+name])
    if disk != blob_data: raise RuntimeError('blob mismatch: '+name)
    entries.append({'path':name,'git_blob':blob,'mode':mode,'sha256':sha(disk),'bytes':len(disk)})
if not entries: raise RuntimeError('empty source manifest')
manifest={'candidate_commit':p['candidate'],'paths':paths,'entries':entries}
manifest_raw=json.dumps(manifest,sort_keys=True,separators=(',',':')).encode(); put('source_manifest.json',manifest_raw)
env=dict(os.environ, CUDA_VISIBLE_DEVICES='', PYTHONPATH=str(wt/'python'), PYTHONDONTWRITEBYTECODE='1')
probe=[p['python'],'-c',"""import json,os,pathlib,torch,freetoken
root=pathlib.Path(os.environ['PYTHONPATH']).resolve(); mod=pathlib.Path(freetoken.__file__).resolve()
assert os.environ['CUDA_VISIBLE_DEVICES']=='' and mod.is_relative_to(root)
assert not torch.cuda.is_initialized() and torch.cuda.device_count()==0
print(json.dumps({'module':str(mod),'cuda_visible_devices':os.environ['CUDA_VISIBLE_DEVICES'],'cuda_initialized':torch.cuda.is_initialized(),'cuda_device_count':torch.cuda.device_count()}))"""]
binding=subprocess.run(probe,cwd=wt,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT); put('import_binding.log',binding.stdout)
if binding.returncode: raise RuntimeError('import binding failed')
binding_data=json.loads(binding.stdout)
argv=[p['python'],'-m','pytest','-q','-p','no:cacheprovider',*tests]
run=subprocess.run(argv,cwd=wt,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT); put('cpu_tests.log',run.stdout)
log=run.stdout.decode(errors='replace'); failures=re.findall(r'^FAILED (.+)$',log,flags=re.MULTILINE); match=re.search(r'(\d+) failed, (\d+) passed, (\d+) skipped',log)
counts={'failed':int(match.group(1)),'passed':int(match.group(2)),'skipped':int(match.group(3))} if match else None
base=pathlib.Path(p['baseline']).read_bytes(); base_data=json.loads(base); base_ok=sha(base)==p['baseline_sha256']
passed=(run.returncode==1 and failures==expected and counts=={'failed':2,'passed':553,'skipped':110} and base_ok and base_data.get('commit')=='23f2e2caa3395837c9474735ffc83321f3b9b5a1' and base_data.get('failed_tests')==expected)
report={'schema':'ft_d15_core_cpu_stage/v1','candidate_commit':p['candidate'],'worktree':str(wt),'candidate_clean_before':True,'cuda_visible_devices':'','import_binding':binding_data,'pytest_argv':argv,'pytest_returncode':run.returncode,'pytest_log_sha256':sha(run.stdout),'failure_set':failures,'counts':counts,'expected_failure_set':expected,'baseline':{'path':p['baseline'],'sha256':sha(base),'sha256_matches_expected':base_ok,'commit':base_data.get('commit'),'failure_set':base_data.get('failed_tests')},'source_manifest':{'path':'source_manifest.json','sha256':sha(manifest_raw),'entries':len(entries)},'stage_tool_sha256':sha((stage/'stage_tool.py').read_bytes()),'gpu_started':False,'requests_sent':False,'verdict':'PASS_NO_NEW_FAILURES' if passed else 'FAIL'}
raw=json.dumps(report,sort_keys=True,separators=(',',':')).encode(); put('cpu_validation.json',raw); put('report_sha256.txt',(sha(raw)+'  cpu_validation.json\n').encode()); put('argv.json',json.dumps(argv).encode()+b'\n')
for path in sorted(stage.rglob('*'),key=lambda x:len(x.parts),reverse=True):
    if path.is_symlink(): raise RuntimeError('stage symlink: '+str(path))
    path.chmod(0o555 if path.is_dir() else 0o444)
stage.chmod(0o555)
for path in stage.rglob('*'):
    if path.is_symlink() or stat.S_IMODE(path.stat().st_mode)!=(0o555 if path.is_dir() else 0o444): raise RuntimeError('freeze failed: '+str(path))
print(json.dumps({'stage':str(stage),'report_sha256':sha(raw),'verdict':report['verdict'],'pytest_returncode':run.returncode,'counts':counts,'failure_set':failures},sort_keys=True))
sys.exit(0 if passed else 1)
'''

BASELINE = '/data2/FreeToken/runs/dev_D15/core_baseline_23f2e2c_paths/cpu_validation.json'
BASELINE_SHA = '992f99a55c087a38180558b1f3356e3fce9157e71b08d451a65789c4d97ed718'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--host', default='172.16.108.9')
    parser.add_argument('--worktree', default='/data2/FreeToken/wt/e2d15')
    parser.add_argument('--runs-root', default='/data2/FreeToken/runs/dev_D15')
    parser.add_argument('--python', default='/data2/FreeToken/venv/bin/python')
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}', args.candidate): parser.error('--candidate needs full lowercase SHA')
    tool=Path(__file__).read_bytes(); token=hashlib.sha256(tool).hexdigest()[:12]
    payload={'candidate':args.candidate,'worktree':args.worktree,'python':args.python,'baseline':BASELINE,'baseline_sha256':BASELINE_SHA,'tool_b64':base64.b64encode(tool).decode(),'stage':f'{args.runs_root}/core_{args.candidate[:7]}_verified_{token}'}
    source="import io,sys\nsys.stdin=io.StringIO("+repr(json.dumps(payload))+")\n"+REMOTE
    result=subprocess.run(['ssh','-o','BatchMode=yes',args.host,args.python,'-'],input=source,text=True,capture_output=True)
    receipt={'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
    output=Path(__file__).with_name(f'd15_core_cpu_{args.candidate[:7]}_{token}.json')
    if output.exists(): raise RuntimeError(f'receipt exists: {output}')
    output.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(result.stdout,end='')
    if result.stderr: print(result.stderr,end='',file=sys.stderr)
    raise SystemExit(result.returncode)


if __name__ == '__main__': main()
