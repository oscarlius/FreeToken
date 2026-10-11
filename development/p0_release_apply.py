"""Publish the verified P0 release under the mainline handoff authorization."""
import base64
import hashlib
import json
import os
from pathlib import Path
import runpy
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]
receipt = json.loads((ROOT/'development/p0_release_stage_receipt.json').read_text())
local = ROOT/'plan/data_releases/FTD-20261004-1.json'
if local.exists() or local.is_symlink():
    raise ValueError('local immutable release already exists; inspect before any publication')
if hashlib.sha256((ROOT/'development/ftd_release_20261004.py').read_bytes()).hexdigest() != receipt['tool_sha256']:
    raise ValueError('reviewed release source changed')
payload = {k: receipt[k] for k in ('stage','tool_sha256','review_sha256')}
program = r'''
import base64,hashlib,json,pathlib,runpy,sys
data=json.load(sys.stdin);stage=pathlib.Path(data['stage']);tool=stage/'development/ftd_release_20261004.py';review_path=stage/'review.json'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(tool)==data['tool_sha256'] and sha(review_path)==data['review_sha256']
namespace=runpy.run_path(str(tool),run_name='ftd_reviewed_publication');review=json.loads(review_path.read_text())
assert review['ready_for_apply'] and not review['planned_appends'] and len(review['rounds'])==21
result=namespace['apply'](review,pathlib.Path(review['writer']),by='Codex mainline under CODEX_HANDOFF_20261004b section 2.2 authorization',
 server_release_dir=pathlib.Path('/data2/_shared/runs/ft_releases/FTD-20261004-1'),local_release_copy=stage/'FTD-20261004-1.json')
manifest=pathlib.Path(result['server_manifest']);document=json.loads(manifest.read_text())
assert document['release_id']=='FTD-20261004-1' and len(document['rounds'])==21
assert not any(p.stat().st_mode&0o222 for p in [manifest.parent,*manifest.parent.iterdir()])
with (stage/'apply_receipt.json').open('x') as stream:json.dump(result,stream,indent=2)
print(json.dumps({'server_manifest':str(manifest),'sha256':sha(manifest),'manifest_base64':base64.b64encode(manifest.read_bytes()).decode(),
 'rounds':len(document['rounds']),'formal_counts':{v:sum(r['artifact_verdict']==v for r in document['rounds']) for v in ('kept','failed_harness')},
 'server_apply_receipt':str(stage/'apply_receipt.json')}))
'''
process = subprocess.run(['ssh','-o','BatchMode=yes','9','/data2/FreeToken/venv/bin/python','-c',shlex.quote(program)],
                         input=json.dumps(payload).encode(),capture_output=True)
if process.returncode:
    print(process.stderr.decode());raise SystemExit(process.returncode)
result = json.loads(process.stdout)
data = base64.b64decode(result.pop('manifest_base64'))
if hashlib.sha256(data).hexdigest() != result['sha256']:
    raise ValueError('downloaded release bytes differ')
namespace=runpy.run_path(str(ROOT/'development/ftd_release_20261004.py'))
namespace['atomic_create'](local,data);os.chmod(local,0o444)
with (ROOT/'development/p0_release_publish_receipt.json').open('x',encoding='utf-8') as stream:
    json.dump({**result,'local_manifest':str(local),'byte_identical':True},stream,ensure_ascii=False,indent=2);stream.write('\n')
print(json.dumps({**result,'local_manifest':str(local),'byte_identical':True},ensure_ascii=False,indent=2))
