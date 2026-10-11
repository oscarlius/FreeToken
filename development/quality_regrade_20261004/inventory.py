"""Bounded read-only inventory for the three historical quality answer sets."""
import hashlib,json,shlex,subprocess
from pathlib import Path

PROGRAM=r'''
import hashlib,json,pathlib,sys
payload=json.load(sys.stdin);root=pathlib.Path('/data2/_shared/runs/ft_rounds')
store=json.loads(pathlib.Path('/data2/_shared/model_hub_dashboard/data/rounds.json').read_text())
paths={'E0-quality60':root/'_e0/paper_headroom_20261003/quality60/quality_results_Qwen3.8-Flash-Next-NVFP4.jsonl',
       'E0-quality60_4096':root/'_e0/paper_headroom_20261003/quality60_4096/quality_results_Qwen3.8-Flash-Next-NVFP4.jsonl',
       'E2-R004':root/'E2-R004/P1/quality60/quality_results_Qwen3.8-Flash-Next-NVFP4.jsonl',
       'E2-R009':root/'E2-R009/P1/quality60/quality_results_Qwen3.8-Flash-Next-NVFP4.jsonl'}
def sha(data):return hashlib.sha256(data).hexdigest()
sets={};rows={}
for label,path in paths.items():
 data=path.read_bytes();records=[json.loads(line) for line in data.splitlines() if line]
 rows[label]={r['question_id']:r for r in records}
 sets[label]={'path':str(path),'sha256':sha(data),'count':len(records),
              'passed':sum(r['passed'] is True for r in records),'keys':sorted(records[0]),
              'first':{k:records[0].get(k) for k in ('question_id','latency_s','finish_reason','detail')},
              'thinking_truncated':[r['question_id'] for r in records if r.get('finish_reason')=='length' and not r.get('response')],
              'historical_grade_function_evidence':'benchmark_client grade_response detail format; evaluator hash alone is not execution proof'}
comparisons={}
for label,records in rows.items():
 if label=='E2-R009':continue
 target=rows['E2-R009'];shared=set(records)&set(target)
 comparisons[label]={'same_questions':len(shared)==60,'same_historical_pass':sum(records[k]['passed']==target[k]['passed'] for k in shared),
                     'same_response':sum(records[k]['response']==target[k]['response'] for k in shared),
                     'same_thinking':sum(records[k]['thinking']==target[k]['thinking'] for k in shared),
                     'max_content_token_delta':max(abs(records[k]['content_tokens']-target[k]['content_tokens']) for k in shared),
                     'max_thinking_token_delta':max(abs(records[k]['thinking_tokens']-target[k]['thinking_tokens']) for k in shared)}
raw=payload['local_raw'];local={r['question_id']:r for r in raw}
comparisons['local_raw']={label:{'same_response':sum(local[k]['response']==r['response'] for k,r in records.items()),
 'same_thinking':sum(local[k]['thinking']==r['thinking'] for k,r in records.items())} for label,records in rows.items()}
print(json.dumps({'sets':sets,'comparisons':comparisons,'E0_record':store['rounds']['E0-R000'],
 'existing_regrade_round':(root/'E2-R009-regrade').exists()},ensure_ascii=False))
'''
root=Path(__file__).resolve().parents[2]
source=root.parent/'_shared/runs/run_paper_headroom_20261003_raw.jsonl'
payload={'local_raw':[json.loads(line) for line in source.read_bytes().splitlines() if line]}
result=subprocess.run(['ssh','-o','BatchMode=yes','9','/data2/FreeToken/venv/bin/python','-c',shlex.quote(PROGRAM)],
                      input=json.dumps(payload).encode(),capture_output=True)
if result.returncode:print(result.stderr.decode());raise SystemExit(result.returncode)
document=json.loads(result.stdout)
print(json.dumps(document,ensure_ascii=False,indent=2))
