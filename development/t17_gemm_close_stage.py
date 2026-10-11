"""Create an immutable CPU-only GEMM close-review stage; actual closing is explicit."""
from __future__ import annotations

import argparse, base64, hashlib, json, re, subprocess
from pathlib import Path

HERE = Path(__file__).parent
REMOTE = '/data2/FreeToken/venv/bin/python'
PREFIX = '/data2/FreeToken/runs/dev_D14/gemm_close_'
TOOLS = ('round_json_append.py', 'round_close.py', 'round_close.sh')

def sha(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def load(path: Path) -> dict: return json.loads(path.read_bytes())
def scoped(path: Path, rid: str, kind: str) -> None:
    if path.name != f't17_gemm_close_{rid}_{kind}_receipt.json': raise ValueError('receipt filename must be RID scoped')
def files(receipt: Path, bindings: Path, monitor: Path) -> dict[str, bytes]:
    out = {'t17_gemm_close.py': (HERE / 't17_gemm_close.py').read_bytes(),
           't17_gemm_close_stage.py': (HERE / 't17_gemm_close_stage.py').read_bytes(),
           't17_gemm_read.py': (HERE / 't17_gemm_read.py').read_bytes(),
           'launch_receipt.json': receipt.read_bytes(), 'bindings.json': bindings.read_bytes(), 'monitor.json': monitor.read_bytes()}
    out.update({name: (HERE.parent / 'scripts' / name).read_bytes() for name in TOOLS})
    return out

PROGRAM = r'''
import base64,hashlib,json,os,pathlib,subprocess,sys
x=json.load(sys.stdin);stage=pathlib.Path(x['stage']);env={**os.environ,'CUDA_VISIBLE_DEVICES':'','PYTHONDONTWRITEBYTECODE':'1'}
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write_new(p,data):
 with p.open('xb') as f:f.write(data)
def freeze():
 for p in reversed([stage,*stage.rglob('*')]):p.chmod(p.stat().st_mode&~0o222)
if x['mode']=='stage':
 stage.mkdir(exist_ok=False)
 try:
  for name,value in x['files'].items():
   p=stage/name;p.parent.mkdir(parents=True,exist_ok=True);write_new(p,base64.b64decode(value))
  p=subprocess.run([sys.executable,str(stage/'t17_gemm_close.py'),'--receipt',str(stage/'launch_receipt.json'),'--bindings',str(stage/'bindings.json'),'--monitor',str(stage/'monitor.json')],env=env,capture_output=True)
  write_new(stage/'audit.log',p.stdout+p.stderr)
  if p.returncode: print((p.stdout+p.stderr).decode(),file=sys.stderr);raise SystemExit(p.returncode)
  review=json.loads(p.stdout);write_new(stage/'audit.json',(json.dumps(review,ensure_ascii=False,indent=2)+'\n').encode())
  report={'schema':'ft_t17_gemm_close_stage/v1','rid':review['rid'],'gpu_started':False,'returncode':0,'audit_sha256':digest(stage/'audit.json'),'audit_log_sha256':digest(stage/'audit.log'),'source_files':{name:digest(stage/name) for name in x['files']},'original_raw_files':len(review['original_raw_files']),'diagnostic_only':True,'limits':review['limits']}
  write_new(stage/'stage.json',(json.dumps(report,indent=2)+'\n').encode());print(json.dumps({'stage':str(stage),'report_sha256':digest(stage/'stage.json'),**report}))
 finally: freeze()
else:
 report=json.loads((stage/'stage.json').read_bytes())
 if digest(stage/'stage.json')!=x['report_sha256'] or report['rid']!=x['rid'] or report['gpu_started'] or report['returncode']!=0:raise ValueError('exact successful frozen stage required')
 for name,want in report['source_files'].items():
  p=stage/name
  if p.is_symlink() or p.stat().st_mode&0o222 or digest(p)!=want:raise ValueError('stage source changed: '+name)
 if digest(stage/'audit.json')!=report['audit_sha256'] or digest(stage/'audit.log')!=report['audit_log_sha256']:raise ValueError('staged audit receipt changed')
 if stage.is_symlink() or stage.stat().st_uid!=os.geteuid() or stage.parent!=pathlib.Path('/data2/FreeToken/runs/dev_D14') or not stage.name.startswith('gemm_close_'):raise ValueError('exact owned frozen stage required')
 p=subprocess.run([sys.executable,str(stage/'t17_gemm_close.py'),'--close','--receipt',str(stage/'launch_receipt.json'),'--bindings',str(stage/'bindings.json'),'--monitor',str(stage/'monitor.json'),'--audit-file',str(stage/'audit.json')],env=env,capture_output=True)
 if p.returncode:print((p.stdout+p.stderr).decode(),file=sys.stderr);raise SystemExit(p.returncode)
 print(p.stdout.decode())
'''

def remote(data: dict) -> dict:
    wire = 'import io,sys\nsys.stdin=io.StringIO(' + repr(json.dumps(data)) + ')\n' + PROGRAM
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '9', REMOTE, '-'], input=wire.encode(), capture_output=True)
    if result.returncode: raise RuntimeError(result.stderr.decode() or result.stdout.decode())
    return json.loads(result.stdout)
def exclusive(path: Path, value: dict) -> None:
    with path.open('x', encoding='utf-8') as stream: json.dump(value, stream, ensure_ascii=False, indent=2); stream.write('\n')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--receipt', type=Path, required=True); parser.add_argument('--bindings', type=Path, required=True); parser.add_argument('--monitor', type=Path, required=True); parser.add_argument('--stage-receipt', type=Path, required=True); parser.add_argument('--close', action='store_true'); parser.add_argument('--close-receipt', type=Path)
    args = parser.parse_args(); receipt = load(args.receipt); rid = receipt.get('rid')
    if not isinstance(rid, str) or not re.fullmatch(r'E2-R\d{3}-diagnostic-T17', rid): raise ValueError('exact RID required')
    if args.close:
        if not args.close_receipt: parser.error('--close requires --close-receipt')
        scoped(args.stage_receipt, rid, 'stage'); scoped(args.close_receipt, rid, 'closure')
        stage_receipt = load(args.stage_receipt); result = remote({'mode':'close','stage':stage_receipt['stage'],'report_sha256':stage_receipt['report_sha256'],'rid':rid}); exclusive(args.close_receipt, result)
    else:
        scoped(args.stage_receipt, rid, 'stage'); payload = files(args.receipt, args.bindings, args.monitor)
        identity = sha(b''.join(name.encode()+payload[name] for name in sorted(payload)))
        result = remote({'mode':'stage','stage':PREFIX+identity[:12],'files':{name:base64.b64encode(value).decode() for name,value in payload.items()}})
        if result['rid'] != rid or result['gpu_started'] is not False or result['returncode'] != 0: raise ValueError('stage did not return exact CPU audit')
        exclusive(args.stage_receipt, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
