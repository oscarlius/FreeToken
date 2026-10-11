"""Prepare a fresh D04 closure clone from the independently checked failure snapshot."""
from pathlib import Path
import json
import subprocess

PROGRAM = r'''
import datetime,hashlib,json,pathlib,shutil
snapshot=pathlib.Path('/data2/FreeToken/runs/dev_D16/r034a_failure_snapshot_20261005_172920')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
report_path=snapshot/'snapshot_report.json'
assert sha(report_path)=='c50c31334d179cd4b684c39c05c765182833d8d1302d4d573fb82e3c1cf7692b'
report=json.loads(report_path.read_text());source=snapshot/'snapshot/E2-R034a'
assert report['verdict']=='PASS' and report['source_unchanged'] is True
assert not source.is_symlink() and not source.stat().st_mode&0o222
root=snapshot.parent/('r034a_close_clone_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
root.mkdir(exist_ok=False);clone=root/'E2-R034a';clone.mkdir()
try:
 for name in report['source_entries']:
  src=source/name;dst=clone/name
  assert not src.is_symlink()
  if src.is_dir():dst.mkdir(exist_ok=False);continue
  expected=report['files'][name];assert src.is_file() and not src.stat().st_mode&0o222
  dst.parent.mkdir(parents=True,exist_ok=True)
  with dst.open('xb') as out,src.open('rb') as inp:shutil.copyfileobj(inp,out,8*1024*1024)
  assert sha(dst)==expected['sha256'] and dst.stat().st_size==expected['size']
  assert (dst.stat().st_dev,dst.stat().st_ino)!=(src.stat().st_dev,src.stat().st_ino)
 actual={p.relative_to(clone).as_posix() for p in clone.rglob('*') if p.is_file()}
 assert actual==set(report['files'])
 result={'schema':'ft_t17_failure_close_clone/v1','clone':str(clone),'source_snapshot':str(source),'source_report_sha256':sha(report_path),'raw_files':len(actual),'bytes':report['bytes'],'verdict':'PREPARED','d04_closed':False,'model_admitted':False,'gpu_started':False,'files':{n:r['sha256'] for n,r in report['files'].items()}}
 path=root/'clone_preparation.json';path.write_text(json.dumps(result,sort_keys=True)+'\n');path.chmod(0o444)
 print(json.dumps({k:v for k,v in result.items() if k!='files'}),flush=True)
except Exception as error:
 (root/'failed_clone.json').write_text(json.dumps({'error':repr(error),'d04_closed':False}));raise
'''

def main():
    done=subprocess.run(['ssh','-o','BatchMode=yes','9','/data2/FreeToken/venv/bin/python','-'],input=PROGRAM,text=True,capture_output=True)
    with Path(__file__).with_name('t17_r034a_clone_execution.json').open('x',encoding='utf-8') as f:
        json.dump({'returncode':done.returncode,'stdout':done.stdout,'stderr':done.stderr},f,indent=2)
    print(done.stdout);print(done.stderr);raise SystemExit(done.returncode)

if __name__=='__main__':main()
