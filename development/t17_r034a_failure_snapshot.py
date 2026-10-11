"""Copy terminal R034a evidence with complete before/after identity and SHA proof.

Artifact-only SSH operation: never starts GPU or changes the original round.
"""
import json, subprocess
from pathlib import Path
PROGRAM = r'''import hashlib,json,os,pathlib,shutil,datetime
source=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R034a')
root=pathlib.Path('/data2/FreeToken/runs/dev_D16')/('r034a_failure_snapshot_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
assert not pathlib.Path('/proc/2377715').exists() and not pathlib.Path('/proc/3176171').exists()
assert not pathlib.Path('/data2/_shared/gpu.lock').exists()
status=json.loads((source/'status_batch63.json').read_text())
assert status['state']=='failed' and status['batch_pid']==2377715
assert json.loads((source/'failed_harness.json').read_text())['admitted'] is False
root.mkdir(exist_ok=False);dest=root/'snapshot'/'E2-R034a';dest.mkdir(parents=True)
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def identity(p):
 s=p.stat();return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
def paths():
 assert not source.is_symlink()
 rows=sorted(source.rglob('*'))
 assert not any(p.is_symlink() for p in rows)
 assert all(p.is_file() or p.is_dir() for p in rows)
 return rows
original=paths();names=[p.relative_to(source).as_posix() for p in original]
records={};total=0
try:
 for index,p in enumerate(original):
  name=p.relative_to(source).as_posix();target=dest/name
  if p.is_dir():target.mkdir(exist_ok=False);continue
  before=identity(p);sha=digest(p);target.parent.mkdir(parents=True,exist_ok=True)
  with target.open('xb') as out,p.open('rb') as inp:shutil.copyfileobj(inp,out,8*1024*1024)
  assert before==identity(p) and sha==digest(p)==digest(target),name
  assert target.stat().st_ino!=p.stat().st_ino or target.stat().st_dev!=p.stat().st_dev
  records[name]={'sha256':sha,'source_identity':before,'size':before[2]};total+=before[2]
  if len(records)%5000==0:print(json.dumps({'copied_files':len(records),'bytes':total}),flush=True)
 assert names==[p.relative_to(source).as_posix() for p in paths()]
 # A second complete source pass detects any mutation after earlier copies.
 for name,row in records.items():
  p=source/name;assert identity(p)==row['source_identity'] and digest(p)==row['sha256'],name
 assert not pathlib.Path('/proc/2377715').exists() and not pathlib.Path('/proc/3176171').exists()
 assert not pathlib.Path('/data2/_shared/gpu.lock').exists()
 log=pathlib.Path('/data2/_shared/runs/ft_rounds/batch63.log');logsha=digest(log);logid=identity(log)
 shutil.copyfile(log,root/'batch63.log')
 assert digest(log)==logsha==digest(root/'batch63.log') and identity(log)==logid
 report={'schema':'ft_t17_terminal_failure_snapshot/v1','verdict':'PASS','source':str(source),'snapshot':str(dest),'source_unchanged':True,'gpu_started':False,'requests_sent':False,'admitted':False,'model_admitted':False,'files':records,'source_entries':names,'file_count':len(records),'bytes':total,'batch_log':{'source':str(log),'sha256':logsha,'source_identity':logid},'limits':['Snapshot only; no D04 closure or T17 acceptance','No root cause or fixed GPU behavior proven']}
 (root/'snapshot_report.json').write_text(json.dumps(report,sort_keys=True)+'\n')
except Exception as exc:
 (root/'failed_snapshot.json').write_text(json.dumps({'verdict':'FAIL','error':repr(exc),'admitted':False}));raise
finally:
 for p in sorted(root.rglob('*'),reverse=True):p.chmod(0o444 if p.is_file() else 0o555)
 root.chmod(0o555)
print(json.dumps({'stage':str(root),'report_sha256':digest(root/'snapshot_report.json'),'file_count':len(records),'bytes':total,'source_unchanged':True}),flush=True)
'''
def main():
 p=subprocess.Popen(['ssh','-o','BatchMode=yes','9','/data2/FreeToken/venv/bin/python','-'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
 p.stdin.write(PROGRAM);p.stdin.close()
 lines=[]
 for line in p.stdout:lines.append(line);print(line,end='',flush=True)
 code=p.wait()
 delivery=Path(__file__).with_name('t17_r034a_snapshot_execution.json')
 with delivery.open('x',encoding='utf-8') as f:json.dump({'returncode':code,'output':''.join(lines)},f,indent=2)
 raise SystemExit(code)
if __name__=='__main__':main()
