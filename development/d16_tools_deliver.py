"""Install the exact CPU-tested D16 package into the declared operator path."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
CPU_STAGE='/data2/FreeToken/runs/dev_D16/tools_cpu_3386eff97242'
CPU_SHA='6113c5ec9c15c8cc5df8ea563c5329db68af28c44be94e2c90dbd7ef849c31a0'
COMMIT='e9ee6aac1786485bb447579f224b0927d8b15cab'
PROGRAM=r'''import hashlib,json,os,pathlib,subprocess,sys
x=json.load(sys.stdin);source=pathlib.Path(x['cpu_stage']);target=pathlib.Path('/data2/FreeToken/scripts/equiv_suite')
proof=source/'cpu_validation.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
if source.is_symlink() or source.stat().st_uid!=os.geteuid() or source.stat().st_mode&0o222 or proof.is_symlink() or proof.stat().st_mode&0o222 or sha(proof)!=x['cpu_sha']:raise ValueError('exact immutable CPU source required')
report=json.loads(proof.read_bytes())
if report.get('verdict')!='PASS' or report.get('passed')!=31 or report.get('gpu_started') is not False or report.get('requests_sent') is not False or report.get('commit')!=x['commit']:raise ValueError('actual 31-test tool-only CPU proof required')
files={name.removeprefix('scripts/equiv_suite/'):digest for name,digest in report['source_files'].items() if name.startswith('scripts/equiv_suite/')}
if len(files)!=9 or any(pathlib.Path(n).name!=n for n in files):raise ValueError('exact package source map required')
for name,digest in files.items():
 p=source/'source/scripts/equiv_suite'/name
 if p.is_symlink() or p.stat().st_uid!=os.geteuid() or p.stat().st_mode&0o222 or sha(p)!=digest:raise ValueError('CPU-tested package changed: '+name)
target.mkdir(exist_ok=False)
try:
 for name in files:
  with (target/name).open('xb') as stream:stream.write((source/'source/scripts/equiv_suite'/name).read_bytes())
 env={**os.environ,'PYTHONPATH':'/data2/FreeToken/scripts','CUDA_VISIBLE_DEVICES':'','PYTHONDONTWRITEBYTECODE':'1'}
 run=subprocess.run([sys.executable,'-m','equiv_suite','--help'],env=env,capture_output=True,timeout=30)
 if run.returncode:raise ValueError('delivered CLI import failed: '+run.stderr.decode())
 if {p.name:sha(p) for p in target.iterdir()}!=files:raise ValueError('delivered source map differs')
finally:
 for p in target.iterdir():p.chmod(0o444)
 target.chmod(0o555)
result={'schema':'ft_d16_tool_delivery/v1','commit':x['commit'],'cpu_stage':str(source),'cpu_report_sha256':x['cpu_sha'],'target':str(target),'files':files,'gpu_started':False,'requests_sent':False,'cli_import_returncode':0}
out=pathlib.Path('/data2/FreeToken/runs/dev_D16/tool_delivery_'+x['commit'][:12]+'.json')
with out.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
out.chmod(0o444)
print(json.dumps({'receipt_path':str(out),'receipt_sha256':sha(out),**result}))
'''


def main():
    receipt=json.loads((HERE/'d16_tools_cpu_3386eff97242.json').read_bytes())
    sources=receipt['report']['source_files']
    target=HERE.parent/'scripts/equiv_suite'
    if target.exists() or target.is_symlink():raise FileExistsError(target)
    payload={'cpu_stage':CPU_STAGE,'cpu_sha':CPU_SHA,'commit':COMMIT}
    wire='import io,sys\nsys.stdin=io.StringIO('+repr(json.dumps(payload))+')\n'+PROGRAM
    run=subprocess.run(['ssh','-o','BatchMode=yes','9','/data2/FreeToken/venv/bin/python','-'],input=wire.encode(),capture_output=True)
    if run.returncode:raise RuntimeError((run.stderr+run.stdout).decode())
    result=json.loads(run.stdout)
    target.mkdir()
    for name,digest in sources.items():
        if not name.startswith('scripts/equiv_suite/'):continue
        raw=subprocess.check_output(['git','-C',str(HERE/'e2d16-tools'),'show',COMMIT+':'+name])
        if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('local committed package differs: '+name)
        with (target/Path(name).name).open('xb') as stream:stream.write(raw)
    with (HERE/'d16_tools_delivery_e9ee6aac1786.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps({'target':result['target'],'files':len(result['files']),'receipt_sha256':result['receipt_sha256']}))


if __name__=='__main__':main()
