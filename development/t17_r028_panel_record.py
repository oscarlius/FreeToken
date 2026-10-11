"""Register the exact sealed R028 harness failure and verify persistent readback."""
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
PROGRAM = r'''
import hashlib,json,pathlib,subprocess,sys,urllib.error,urllib.request
rid='E2-R028-diagnostic-T17'
directory=pathlib.Path('/data2/_shared/runs/ft_rounds')/rid
expected_round='22782aa01b49a6d855ff794abeb11b8126db098672cea421f26f088d742468a9'
expected_manifest='4d0ee4947373f8338deb4d9cb7c0e503a61bf389c2eef5098674191b24dd36b4'
writer=pathlib.Path('/data2/FreeToken/scripts/round_json_append.py')
store=pathlib.Path('/data2/_shared/model_hub_dashboard/data/rounds.json')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
if digest(writer)!='67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff':raise ValueError('verified history validator changed')
if digest(directory/'round.json')!=expected_round or digest(directory/'MANIFEST.sha256')!=expected_manifest:raise ValueError('exact sealed failure required')
subprocess.run(['sha256sum','-c','MANIFEST.sha256'],cwd=directory,check=True,stdout=subprocess.DEVNULL)
subprocess.run([sys.executable,str(writer),str(directory),'check'],check=True,stdout=subprocess.DEVNULL)
if any(p.stat().st_mode&0o222 for p in (directory,*directory.rglob('*'))):raise ValueError('sealed failure must remain read-only')
document=json.loads((directory/'round.json').read_bytes())
if (document.get('verdict')!='failed_harness' or document['experimental']['diagnostic_only'] is not True
    or document['results']['measurements_completed'] is not False
    or len(document['diagnostics']['original_raw_files'])!=23):raise ValueError('wrong failure classification')
before=json.loads(store.read_bytes())['rounds'].get(rid)
if before is not None and any(before.get(k)!=v for k,v in document.items()):raise ValueError('existing panel record differs; review required')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
if before is None:
 # The live seven-value POST enum predates D04 failed_harness. Its documented
 # artifact merge supplies missing fields from the sealed source on GET /rounds.
 payload={key:value for key,value in document.items() if key!='verdict'}
 request=urllib.request.Request('http://127.0.0.1:8098/api/rounds/record',data=(json.dumps(payload,allow_nan=False)+'\n').encode(),method='POST',headers={'Content-Type':'application/json'})
 try:
  with opener.open(request,timeout=30) as response:posted={'http_status':response.status,'response':json.loads(response.read())}
 except urllib.error.HTTPError as error:
  print(json.dumps({'http_status':error.code,'response_body':error.read().decode()}),file=sys.stderr)
  raise SystemExit(1)
else:posted={'new_post':False,'previous_record_verified':True}
with opener.open('http://127.0.0.1:8098/api/rounds',timeout=30) as response:
 visible=json.loads(response.read())['rounds'][rid]
if any(visible.get(k)!=v for k,v in document.items()):raise ValueError('artifact-merged API readback differs')
after=json.loads(store.read_bytes())['rounds'][rid]
if any(after.get(k)!=v for k,v in document.items()):raise ValueError('persistent panel readback differs')
if digest(directory/'round.json')!=expected_round or digest(directory/'MANIFEST.sha256')!=expected_manifest:raise ValueError('panel record changed sealed source')
print(json.dumps({'rid':rid,'verdict':'failed_harness','post_receipt':posted,'sealed_source_sha256':expected_round,
 'sealed_manifest_sha256':expected_manifest,'readback_verified':True,
 'transport':'metadata POST followed by sealed-artifact verdict merge; direct failed_harness POST unsupported',
 'scope':'initialization failure only; no measurements; R023 not_met retained'}))
'''

if __name__ == '__main__':
    process = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '9',
                              '/data2/FreeToken/venv/bin/python', '-'], input=PROGRAM.encode(), capture_output=True)
    if process.returncode:
        print(process.stderr.decode())
        raise SystemExit(process.returncode)
    result = json.loads(process.stdout)
    receipt = HERE / 't17_r028_panel_receipt.json'
    if receipt.exists():
        previous = json.loads(receipt.read_bytes())
        if any(previous.get(key) != result[key] for key in ('rid', 'verdict', 'sealed_source_sha256',
                                                           'sealed_manifest_sha256', 'readback_verified', 'scope')):
            raise ValueError('previous registration receipt differs')
    else:
        with receipt.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='post_receipt'}, indent=2))
