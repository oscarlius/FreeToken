"""Register the verified sealed offline analysis in the authorized 8098 round library."""
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
PROGRAM = r'''
import hashlib,json,pathlib,subprocess,sys,urllib.request
rid='E2-R009-regrade';root=pathlib.Path('/data2/_shared/runs/ft_rounds')/rid
expected='7c18881bbd5d66d5ea66c2e4069da9c416f4c223381e4b01fe02218f735b8ec1'
manifest='b7a88d869559ecca01fa24eab1113f15854ecf7be178649f7f0a19a6157cddb5'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
if sha(root/'round.json')!=expected or sha(root/'MANIFEST.sha256')!=manifest:
 raise ValueError('exact independently reviewed sealed analysis required')
subprocess.run(['sha256sum','-c','MANIFEST.sha256'],cwd=root,check=True,stdout=subprocess.DEVNULL)
subprocess.run([sys.executable,str(root/'round_json_append.py'),str(root),'check'],check=True,stdout=subprocess.DEVNULL)
document=json.loads((root/'round.json').read_bytes())
if (document['verdict']!='kept' or document['experimental']!={'analysis_only':True,'gpu_started':False}
 or document['evaluator_sha256']!='39f10fa8ddab2c1b076862eb827d903be945243bb2e2422ec448e8560646e330'):
 raise ValueError('offline-only pinned analysis required')
for item in document['results']['sets'].values():
 if item['passed']!=47 or item['total']!=60 or sha(pathlib.Path(item['input_path']))!=item['input_sha256']:
  raise ValueError('historical input or analyzed result changed')
store=pathlib.Path('/data2/_shared/model_hub_dashboard/data/rounds.json')
before=json.loads(store.read_bytes())['rounds'].get(rid)
if before is not None:
 if any(before.get(key)!=value for key,value in document.items()):
  raise ValueError('existing record differs; preserve and inspect it')
 posted={'new_post':False,'existing_record_verified':True}
else:
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 request=urllib.request.Request('http://127.0.0.1:8098/api/rounds/record',
  data=(json.dumps(document,ensure_ascii=False,allow_nan=False)+'\n').encode(),method='POST',headers={'Content-Type':'application/json'})
 with opener.open(request,timeout=30) as response:
  posted={'http_status':response.status,'response':json.loads(response.read())}
after=json.loads(store.read_bytes())['rounds'][rid]
if any(after.get(key)!=value for key,value in document.items()):raise ValueError('persisted readback differs')
if sha(root/'round.json')!=expected or sha(root/'MANIFEST.sha256')!=manifest:
 raise ValueError('panel write changed sealed source')
print(json.dumps({'round_id':rid,'readback_verified':True,'sealed_source_sha256':expected,
 'manifest_sha256':manifest,'scope':'offline analysis only; no new generation or T17 acceptance',
 'post_receipt':posted}))
'''

if __name__ == '__main__':
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '9',
                             '/data2/FreeToken/venv/bin/python', '-'], input=PROGRAM.encode(), capture_output=True)
    if result.returncode:
        print(result.stderr.decode())
        raise SystemExit(result.returncode)
    receipt = json.loads(result.stdout)
    with (HERE / 'panel_receipt.json').open('x', encoding='utf-8') as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({key: value for key, value in receipt.items() if key != 'post_receipt'}, indent=2))
