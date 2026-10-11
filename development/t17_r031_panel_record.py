"""Register exact sealed R031 operator metadata and verify API/persistent readback."""
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
PROGRAM = r'''
import hashlib,json,pathlib,subprocess,sys,urllib.request
rid='E2-R031-diagnostic-T17';root=pathlib.Path('/data2/_shared/runs/ft_rounds')/rid
expected_round='3689e559df21947a16a7a1f14bc105498cc1e96e4bcf945a19f3f76c5f4ca5ed'
expected_manifest='38538a39d163b031d8679f8b84a2793b02cb607c9be68ac8431c99837df11bba'
writer=pathlib.Path('/data2/FreeToken/scripts/round_json_append.py')
store=pathlib.Path('/data2/_shared/model_hub_dashboard/data/rounds.json')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
if sha(writer)!='67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff':raise ValueError('history validator changed')
if sha(root/'round.json')!=expected_round or sha(root/'MANIFEST.sha256')!=expected_manifest:raise ValueError('exact sealed R031 required')
subprocess.run(['sha256sum','-c','MANIFEST.sha256'],cwd=root,check=True,stdout=subprocess.DEVNULL)
subprocess.run([sys.executable,str(writer),str(root),'check'],check=True,stdout=subprocess.DEVNULL)
if any(p.is_symlink() or p.stat().st_mode&0o222 for p in (root,*root.rglob('*'))):raise ValueError('regular read-only sealed source required')
document=json.loads((root/'round.json').read_bytes());observed=document['results']
if (document.get('verdict')!='kept' or document.get('serve')!='none'
 or document['experimental'].get('operator_only') is not True or document['experimental'].get('diagnostic_only') is not True
 or document['experimental'].get('operator')!='gdn' or observed.get('cuda_initialized') is not False
 or observed['runs']['warm_full_m']['vs_warm_live']['bitwise_equal'] is not True
 or observed['runs']['cold_full_m']['vs_cold_live']['bitwise_equal'] is not True
 or observed['pair_metrics']['warm_full_m__cold_full_m']['different_bytes']!=789):
 raise ValueError('wrong diagnostic metadata')
before=json.loads(store.read_bytes())['rounds'].get(rid)
if before is not None and any(before.get(k)!=v for k,v in document.items()):raise ValueError('existing panel record differs')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
if before is None:
 request=urllib.request.Request('http://127.0.0.1:8098/api/rounds/record',data=(json.dumps(document,allow_nan=False)+'\n').encode(),method='POST',headers={'Content-Type':'application/json'})
 with opener.open(request,timeout=30) as response:posted={'http_status':response.status,'response':json.loads(response.read())}
else:posted={'new_post':False,'previous_record_verified':True}
with opener.open('http://127.0.0.1:8098/api/rounds',timeout=30) as response:visible=json.loads(response.read())['rounds'][rid]
after=json.loads(store.read_bytes())['rounds'][rid]
if any(visible.get(k)!=v or after.get(k)!=v for k,v in document.items()):raise ValueError('API/persistent readback differs')
if sha(root/'round.json')!=expected_round or sha(root/'MANIFEST.sha256')!=expected_manifest:raise ValueError('registration changed sealed source')
print(json.dumps({'rid':rid,'verdict':'kept','post_receipt':posted,'sealed_source_sha256':expected_round,
 'sealed_manifest_sha256':expected_manifest,'readback_verified':True,
 'transport':'full sealed operator metadata POST plus API and persistent readback',
 'scope':'GDN operator diagnostic only; historical R023 not_met retained; no baseline admission'}))
'''

if __name__ == '__main__':
    process = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '9',
                              '/data2/FreeToken/venv/bin/python', '-'], input=PROGRAM.encode(), capture_output=True)
    if process.returncode:
        raise RuntimeError(process.stderr.decode() or process.stdout.decode())
    result = json.loads(process.stdout)
    path = HERE / 't17_r031_panel_receipt.json'
    if path.exists():
        previous = json.loads(path.read_bytes())
        if any(previous.get(k) != result[k] for k in ('rid', 'verdict', 'sealed_source_sha256',
                                                    'sealed_manifest_sha256', 'readback_verified', 'scope')):
            raise ValueError('retained panel receipt differs')
    else:
        with path.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2)
            stream.write('\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'post_receipt'}, indent=2))
