from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import shutil
HERE=Path(__file__).resolve().parent; RID="E2-R067c-d20-short-tail-retry2"; ARTIFACTS=("t17_d14_startup.py","t17_d14_exact_ids.py","t17_d14_observe.py")
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def verify_service_bindings(config):
 for s in config['services']:
  arm=f"/data2/FreeToken/runs/dev_R067/{RID}/services/{s['name']}"
  assert s['service_dir']==arm and s['cwd']==arm,s['name']
  assert s['argv'][5]==arm+'/t17_d14_startup.py',s['name']
  assert hashlib.sha256(json.dumps(s['argv'],separators=(',',':')).encode()).hexdigest()==s['argv_sha256'],s['name']
  assert 'E2-R067c-d20-short-tail-retry1' not in json.dumps((s['argv'],s['env']),sort_keys=True),s['name']
  for key in ('FT_DEV_STATE_DUMP','FT_T17_INPUT_RECEIPTS','FT_T17_OBSERVATIONS','PYTHONPATH'): assert arm in s['env'][key],(s['name'],key)
def filedry(out):
 c=json.loads((HERE/'RETRY2_CONFIG_CPU_ONLY.json').read_text()); m=json.loads((HERE/'RETRY2_UPLOAD_MANIFEST.json').read_text())
 assert not out.exists() and c['rid']==RID and not c['admission']['admit'] and c['retry']['last_allowed_retry']
 for n,d in m['files'].items(): assert sha(HERE/n)==d,n
 verify_service_bindings(c)
 out.mkdir(parents=True)
 for s in c['services']:
  arm=out/s['name'];arm.mkdir()
  for a in ARTIFACTS: shutil.copyfile(HERE/'tooling'/a,arm/a);(arm/a).chmod(0o444)
  (arm/'no_start.json').write_text(json.dumps({'popen':False,'admit':False,'service':s['name']})+'\n')
 r={'rid':RID,'services':10,'calls':14,'artifacts':30,'admit':False,'gpu_started':False,'service_started':False,'http_generation':False};(out/'receipt.json').write_text(json.dumps(r,sort_keys=True)+'\n');r['receipt_sha256']=sha(out/'receipt.json');return r
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--filedry',action='store_true');p.add_argument('--out',type=Path);p.add_argument('--run',action='store_true');a=p.parse_args(argv)
 if a.run: raise RuntimeError('--run is prohibited in retry2 CPU validation')
 if not a.filedry or a.out is None:p.error('--filedry and --out are required')
 print(json.dumps(filedry(a.out),sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
