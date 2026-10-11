"""Append the independent analysis review through the frozen D04 tool."""
import json
from pathlib import Path
import shlex
import subprocess

HERE=Path(__file__).resolve().parent
PROGRAM=r'''
import hashlib,json,pathlib,subprocess,sys
r=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R009-regrade')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest='b7a88d869559ecca01fa24eab1113f15854ecf7be178649f7f0a19a6157cddb5'
if sha(r/'MANIFEST.sha256')!=manifest:raise ValueError('analysis manifest changed')
subprocess.run(['sha256sum','-c','MANIFEST.sha256'],cwd=r,stdout=subprocess.DEVNULL,check=True)
doc=json.loads((r/'round.json').read_bytes())
for item in doc['results']['sets'].values():
 if sha(pathlib.Path(item['input_path']))!=item['input_sha256']:raise ValueError('historical input changed')
 if sha(r/item['output_file'])!=item['output_sha256']:raise ValueError('regrade changed')
review={'independent_review':{'id':'quality-standard-20261004','recommendation':'keep_offline_analysis',
 'checked':['180 explicit grader calls and identical per-question states','three immutable input hashes',
            '41 manifest members and all read-only modes','canonical evaluator/client exact SHA',
            'E0 before/after D04 append-only validation with .7833 preserved','13 Linux publication/bridge tests'],
 'reviewers':['t17_review independent regrade and post-sync verification','release_review source/publication review'],
 'gpu_started':False,'acceptance_scope':'offline grading provenance only; no model generation or T17 acceptance'}}
tool=[sys.executable,str(r/'round_json_append.py'),str(r)]
review_path=pathlib.Path('/data2/FreeToken/runs/quality_publish_E2-R009-regrade/independent_review.json')
encoded=(json.dumps(review,indent=2)+'\n').encode()
if review_path.exists():
 if review_path.is_symlink() or review_path.read_bytes()!=encoded:raise ValueError('review payload changed')
else:
 with review_path.open('xb') as stream:stream.write(encoded)
 review_path.chmod(0o444)
if 'independent_review' not in doc:
 subprocess.run(tool+['add','--json',str(review_path)],check=True)
elif doc['independent_review']!=review['independent_review']:raise ValueError('different review already recorded')
doc=json.loads((r/'round.json').read_bytes())
if doc['verdict']=='pending_review':
 subprocess.run(tool+['verdict','--new','kept','--by','Codex',
  '--reason','Independent CPU replay and post-sync verification passed; retain offline regrade provenance only, no new model generation or T17 acceptance.',
  '--evidence','quality_summary.json',manifest,'independent_review.quality-standard-20261004'],check=True)
elif doc['verdict']!='kept':raise ValueError('different formal verdict; preserve it')
subprocess.run(tool+['check'],check=True)
subprocess.run(['sha256sum','-c','MANIFEST.sha256'],cwd=r,stdout=subprocess.DEVNULL,check=True)
if any(p.is_symlink() or p.stat().st_mode&0o222 for p in [r,*r.rglob('*')]):raise ValueError('sealed modes changed')
first=json.loads((r/'round_history/round.v001.json').read_bytes())
if first['verdict']!='pending_review':raise ValueError('initial snapshot changed')
doc=json.loads((r/'round.json').read_bytes())
print(json.dumps({'round_id':r.name,'formal_verdict':doc['verdict'],'round_sha256':sha(r/'round.json'),
 'manifest_sha256':manifest,'history_count':len(list((r/'round_history').glob('round.v*.json'))),'gpu_started':False}))
'''
result=subprocess.run(['ssh','-o','BatchMode=yes','9','/data2/FreeToken/venv/bin/python','-c',shlex.quote(PROGRAM)],capture_output=True)
if result.returncode:print((result.stdout+result.stderr).decode());raise SystemExit(result.returncode)
receipt=json.loads(result.stdout.decode().splitlines()[-1])
with (HERE/'final_receipt.json').open('x',encoding='utf-8') as stream:json.dump(receipt,stream,indent=2);stream.write('\n')
print(json.dumps(receipt,indent=2))
