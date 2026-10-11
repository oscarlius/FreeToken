"""Record the sealed diagnostic and append R024's classification note to the authorized panel."""
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
PROGRAM = r'''
import hashlib,importlib.util,json,pathlib,subprocess,sys,urllib.request
root=pathlib.Path('/data2/_shared/runs/ft_rounds')
store=pathlib.Path('/data2/_shared/model_hub_dashboard/data/rounds.json')
writer=pathlib.Path('/data2/FreeToken/scripts/round_json_append.py')
if hashlib.sha256(writer.read_bytes()).hexdigest()!='67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff':raise ValueError('verified append validator required')
spec=importlib.util.spec_from_file_location('panel_append_validator',writer)
validator=importlib.util.module_from_spec(spec);sys.modules[spec.name]=validator;spec.loader.exec_module(validator)
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
results=[]
for rid,expected in [('E2-R025-diagnostic-T17','e3eba14fba52c2a8fb77eae5bae988ffa60eb476ab57b10e6cb3ee950905f9ef'),
                     ('E2-R024-gate-D07','d527648fdef34dc033df2202ab008ece74b2793fc10e38a09b9b92312c3e07eb')]:
 directory=root/rid
 raw=(directory/'round.json').read_bytes()
 if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('exact sealed/current correction source required')
 subprocess.run(['sha256sum','-c','MANIFEST.sha256'],cwd=directory,check=True,stdout=subprocess.DEVNULL)
 subprocess.run([sys.executable,str(writer),str(directory),'check'],check=True,stdout=subprocess.DEVNULL)
 document=json.loads(raw);before=json.loads(store.read_bytes())['rounds'].get(rid)
 if rid.startswith('E2-R025'):
  if document['experimental']['diagnostic_only'] is not True or document['verdict']!='kept':raise ValueError('diagnostic-only record required')
  if before is not None:
   if any(before.get(key)!=value for key,value in document.items()):raise ValueError('existing R025 differs; review before any update')
   payload=None
  else:payload=document
 else:
  correction=document['diagnostics']['raw_file_classification_correction']
  if before is None:payload=document
  elif before.get('diagnostics',{}).get('raw_file_classification_correction') is not None:
   if before['diagnostics']['raw_file_classification_correction']!=correction:raise ValueError('existing panel correction differs')
   payload=None
  else:payload={'round_id':rid,'diagnostics':{'raw_file_classification_correction':correction}}
 if payload is not None:
  request=urllib.request.Request('http://127.0.0.1:8098/api/rounds/record',
   data=(json.dumps(payload,ensure_ascii=False,allow_nan=False)+'\n').encode(),method='POST',headers={'Content-Type':'application/json'})
  with opener.open(request,timeout=30) as response:posted=json.loads(response.read())
 else:posted={'previous_record_verified':True,'new_post':False}
 after=json.loads(store.read_bytes())['rounds'][rid]
 if before is not None:validator.validate_change(before,after)
 if rid.startswith('E2-R025'):
  for key,value in document.items():
   if after.get(key)!=value:raise ValueError('new panel record differs from sealed diagnostic')
 else:
  if after['diagnostics']['raw_file_classification_correction']!=correction:raise ValueError('panel append readback differs')
 if hashlib.sha256((directory/'round.json').read_bytes()).hexdigest()!=expected:raise ValueError('panel write changed source round')
 results.append({'rid':rid,'post_receipt':posted,'sealed_source_sha256':expected,'readback_verified':True,
  'scope':'diagnostic measurement only; R023 not_met retained' if rid.startswith('E2-R025') else 'append-only classification correction; original metrics retained'})
print(json.dumps(results,ensure_ascii=False))
'''

if __name__ == '__main__':
    wire = PROGRAM
    process = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '9',
                              '/data2/FreeToken/venv/bin/python', '-'], input=wire.encode('utf-8'), capture_output=True)
    if process.returncode:
        print(process.stderr.decode())
        raise SystemExit(process.returncode)
    result = json.loads(process.stdout)
    with (HERE / 't17_r025_panel_receipt.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
