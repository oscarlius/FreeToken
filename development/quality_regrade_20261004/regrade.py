"""Offline quality analysis with one pinned evaluator and immutable answer inputs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

EVALUATOR_SHA='39f10fa8ddab2c1b076862eb827d903be945243bb2e2422ec448e8560646e330'
PREVIOUS_SHA='250e197f1c09716ae399d491537c396e3ba47706b7d289b6b95220b5a30f4a71'
PROMPTS_SHA='bde77ab02bb11539f6ee69861dc441ea3670ed6796d4d27226af1f89f74f9cad'
RID='E2-R009-regrade'
ROUNDS=Path('/data2/_shared/runs/ft_rounds')
INPUTS={
    'E0-R000':('_e0/paper_headroom_20261003/quality60/quality_results_Qwen3.8-Flash-Next-NVFP4.jsonl','355398ab3f88e261afb0ad8b728b9fcd9851b41468b5a48cea8b8f73124f8233'),
    'E2-R004':('E2-R004/P1/quality60/quality_results_Qwen3.8-Flash-Next-NVFP4.jsonl','8ca169dba9ec3b38e6d103e7d5e2cfbf093256def6dae3abd1d5b127f297031b'),
    'E2-R009':('E2-R009/P1/quality60/quality_results_Qwen3.8-Flash-Next-NVFP4.jsonl','2d0f2b5960ab3680884d0da0d2285648e5c1f7072d51d6f091ed980bc7d24adc')}

def sha(data):return hashlib.sha256(data).hexdigest()
def encoded(value):return (json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
def put(path,value):
    with path.open('xb') as stream:stream.write(encoded(value))

def validate(records,prompts):
    if len(records)!=60 or len(prompts)!=60:raise ValueError('exact 60-question corpus required')
    ids=[row.get('question_id') for row in records]
    if len(set(ids))!=60 or set(ids)!=set(prompts):raise ValueError('duplicate/missing/foreign question')
    for row in records:
        q=prompts[row['question_id']]
        if row.get('category')!=q['category']:raise ValueError('question category differs')
        if not isinstance(row.get('response'),str) or not isinstance(row.get('thinking'),str):
            raise ValueError('actual separated answer/thinking required')
        if row.get('finish_reason') not in ('stop','length'):raise ValueError('actual terminal reason required')
        if type(row.get('passed')) is not bool:raise ValueError('historical actual verdict required')
        if q['category']=='code_autotest' and not(q.get('test_code') or q.get('test_cases')):
            raise ValueError('code question has no executable tests')

def grade_set(records,prompts,grade):
    validate(records,prompts);graded=[];counts={};categories={}
    for row in records:
        q=prompts[row['question_id']]
        status,detail=grade(q,row['response'],finish_reason=row['finish_reason'])
        if status not in ('PASS','ANSWER_FAIL','TRUNCATED'):raise ValueError('grader/runtime error: '+row['question_id']+': '+detail)
        result={**row,'historical_passed':row['passed'],'historical_detail':row.get('detail'),
                'status':status,'detail':detail,'passed':status=='PASS','evaluator_sha256':EVALUATOR_SHA,
                'question_sha256':sha(encoded(q)),'original_record_sha256':sha(encoded(row)),
                'response_sha256':sha(row['response'].encode()),'thinking_sha256':sha(row['thinking'].encode())}
        graded.append(result);counts[status]=counts.get(status,0)+1
        category=categories.setdefault(q['category'],{'total':0,'passed':0,'thinking_truncated':0})
        category['total']+=1;category['passed']+=int(status=='PASS')
        category['thinking_truncated']+=int(row['finish_reason']=='length' and not row['response'].strip())
    summary={'total':60,'passed':counts.get('PASS',0),'pass_rate':counts.get('PASS',0)/60,
             'status_counts':counts,'categories':categories,'historical_passed':sum(r['passed'] for r in records),
             'changed_verdicts':[r['question_id'] for r in graded if r['historical_passed']!=r['passed']],
             'thinking_truncated':[r['question_id'] for r in records if r['finish_reason']=='length' and not r['response'].strip()]}
    return graded,summary

def execute():
    if sys.platform!='linux':raise ValueError('same target Linux environment required')
    here=Path(__file__).resolve().parent
    evaluator=here/'evaluator.py';prompts_path=here/'test_prompts_60.json'
    if sha(evaluator.read_bytes())!=EVALUATOR_SHA or sha(prompts_path.read_bytes())!=PROMPTS_SHA:
        raise ValueError('pinned evaluator/corpus changed')
    raw_prompts=json.loads(prompts_path.read_bytes());prompts={q['id']:q for q in raw_prompts}
    if len(raw_prompts)!=len(prompts):raise ValueError('duplicate corpus ID')
    inputs={}
    for rid,(relative,digest) in INPUTS.items():
        path=ROUNDS/relative;data=path.read_bytes()
        if path.is_symlink() or sha(data)!=digest:raise ValueError('historical input changed: '+rid)
        inputs[rid]=[json.loads(line) for line in data.splitlines() if line];validate(inputs[rid],prompts)
    directory=ROUNDS/RID
    if directory.exists():raise FileExistsError('existing analysis retained')
    spec=importlib.util.spec_from_file_location('quality_standard_pinned',evaluator)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    directory.mkdir();(directory/'source').mkdir()
    for path in (evaluator,prompts_path,Path(__file__)):
        with (directory/'source'/path.name).open('xb') as stream:stream.write(path.read_bytes())
    result={'schema':'ft_quality_regrade/v1','round_id':RID,'gpu_started':False,
            'evaluator_sha256':EVALUATOR_SHA,'questions_sha256':PROMPTS_SHA,
            'python_version':sys.version,'python_executable':sys.executable,'sets':{},'comparison':{}}
    for rid,rows in inputs.items():
        graded,summary=grade_set(rows,prompts,module.grade_question)
        output=directory/(rid+'.regraded.jsonl')
        with output.open('xb') as stream:
            for row in graded:stream.write((json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n').encode())
        result['sets'][rid]={**summary,'input_path':str(ROUNDS/INPUTS[rid][0]),'input_sha256':INPUTS[rid][1],
                            'output_file':output.name,'output_sha256':sha(output.read_bytes())}
    graded={rid:{r['question_id']:r for r in [json.loads(line) for line in (directory/(rid+'.regraded.jsonl')).read_bytes().splitlines()]} for rid in inputs}
    baseline=graded['E0-R000']
    for rid,rows in graded.items():
        result['comparison'][rid]={'same_graded_verdicts':sum(row['status']==baseline[qid]['status'] for qid,row in rows.items()),
                                  'same_response':sum(row['response']==baseline[qid]['response'] for qid,row in rows.items()),
                                  'same_thinking':sum(row['thinking']==baseline[qid]['thinking'] for qid,row in rows.items())}
    for rid,(relative,digest) in INPUTS.items():
        if sha((ROUNDS/relative).read_bytes())!=digest:raise ValueError('input changed while grading: '+rid)
    put(directory/'quality_summary.json',result)
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':execute()
