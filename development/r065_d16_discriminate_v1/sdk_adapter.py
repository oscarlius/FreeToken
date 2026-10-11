"""R065 official openai SDK adapter. No model launch or native state reads."""
from __future__ import annotations
import concurrent.futures, importlib.util, json, threading, time, unicodedata
from pathlib import Path
import httpx
from openai import OpenAI

HERE = Path(__file__).resolve().parent
EVAL = HERE.parents[1] / 'evaluation/d16_api'
spec = importlib.util.spec_from_file_location('r065_frozen_sdk', EVAL / 'sdk_completions.py')
frozen = importlib.util.module_from_spec(spec); spec.loader.exec_module(frozen)
class CriterionMismatch(ValueError):
    """A valid API observation fails an authorized comparison criterion."""

def write(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, sort_keys=True); f.write('\n')

def request(prompt, model, tokens):
    if tokens not in (64, 128): raise ValueError('unapproved token budget')
    return dict(model=model, prompt=prompt, max_tokens=tokens, temperature=0, top_p=1,
                stream=True, stream_options={'include_usage': True}, extra_body={'ignore_eos': True})

def project64(chunks):
    text=[]; finish=None; usage=None; identity=None
    for chunk in chunks:
        current=chunk.get('id')
        if not isinstance(current,str) or not current or (identity is not None and current!=identity): raise ValueError('stream identity differs')
        identity=current; choices=chunk.get('choices')
        if not isinstance(choices,list) or len(choices)>1: raise ValueError('invalid choices')
        if choices:
            choice=choices[0]
            if finish is not None or choice.get('index')!=0 or not isinstance(choice.get('text'),str): raise ValueError('invalid terminal choice')
            text.append(choice['text']); finish=choice.get('finish_reason')
        if chunk.get('usage') is not None:
            if usage is not None: raise ValueError('duplicate usage')
            usage=chunk['usage']; frozen._usage(usage)
    if finish!='length' or usage is None or usage.get('completion_tokens')!=64: raise CriterionMismatch('64 token contract differs')
    return dict(text=''.join(text),finish_reason=finish,usage=frozen._usage(usage),completion_id=identity)

def collect(client, req):
    if req['max_tokens']==128:
        artifact=frozen.collect_completion(client,req)
    else:
        if client.max_retries!=0: raise ValueError('retries forbidden')
        check={**req,'max_tokens':128}; frozen.validate_request(check)
        started=time.monotonic(); artifact={'request':frozen._wire_request(req),'response':None,'chunks':[]}
        try:
            raw=client.with_raw_response.completions.create(**req)
            artifact['response']={'status_code':raw.status_code,'headers':dict(raw.headers),'received_seconds':time.monotonic()-started}
            for chunk in raw.parse(): artifact['chunks'].append({'arrival_seconds':time.monotonic()-started,'data':chunk.model_dump(mode='json')})
            artifact['projection']=project64(row['data'] for row in artifact['chunks'])
        except BaseException as exc:
            artifact['error']={'type':type(exc).__name__,'message':str(exc)}
            raise frozen.CompletionCollectionError(artifact,exc) from exc
    full_usage=next(row['data']['usage'] for row in artifact['chunks'] if row['data'].get('usage') is not None)
    artifact['full_usage_observation']=full_usage
    details=full_usage.get('prompt_tokens_details')
    reported=isinstance(details,dict) and 'cached_tokens' in details and details['cached_tokens'] is not None
    cached=details['cached_tokens'] if reported else None
    if reported and (type(cached) is not int or cached<0): raise frozen.CompletionCollectionError(artifact,ValueError('invalid cached_tokens'))
    artifact['cached_tokens_observation']={'status':'reported' if reported else 'missing','value':cached,'fallback_used':False}
    return artifact

def collect_one(base, model, label, item, output, barrier=None):
    client=OpenAI(base_url=base.rstrip('/')+'/v1',api_key='r065-api-only',max_retries=0,
                  timeout=900,http_client=httpx.Client(trust_env=False))
    started=None
    try:
        if barrier: barrier.wait(timeout=20)
        started=time.monotonic(); artifact=collect(client,request(item['prompt'],model,item['max_tokens']))
        artifact['client']={'label':label,'started_seconds':started,'completed_seconds':time.monotonic()}
        if artifact['projection']['usage']['prompt_tokens']!=item['prompt_tokens']:
            artifact['contract_error']='prompt token count differs'; write(output/ (label+'.json'),artifact); raise CriterionMismatch(artifact['contract_error'])
        write(output/(label+'.json'),artifact); return artifact
    except frozen.CompletionCollectionError as exc:
        exc.artifact['client']={'label':label,'started_seconds':started,'completed_seconds':time.monotonic()}
        write(output/(label+'.json'),exc.artifact)
        if isinstance(exc.__cause__,CriterionMismatch) or (isinstance(exc.__cause__,ValueError) and str(exc.__cause__)=='D16 SDK completion must end at length with 128 tokens'):
            raise CriterionMismatch(str(exc)) from exc
        raise
    finally: client.close()

def pair(base,model,items,output):
    barrier=threading.Barrier(2)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(collect_one,base,model,label,item,output,barrier) for label,item in items]
        records=[future.result() for future in futures]
    windows=[(x['client']['started_seconds'],x['client']['completed_seconds']) for x in records]
    if max(x[0] for x in windows)>=min(x[1] for x in windows): raise ValueError('API windows do not overlap')
    return records

def comparable(left,right,fields=('text','finish_reason','usage')):
    for field in fields:
        if left['projection'][field]!=right['projection'][field]: raise CriterionMismatch('completion differs: '+field)

def discriminate(text, own, other):
    if own not in text or other in text: raise CriterionMismatch('own/other marker contract differs')
    if any(c=='\ufffd' or unicodedata.category(c)=='Cs' or (unicodedata.category(c)=='Cc' and c not in '\n\r\t') for c in text):
        raise CriterionMismatch('malformed replacement/surrogate/control response')

def run_service(base, model, service, run_dir):
    inputs=json.loads((HERE/'inputs.json').read_text(encoding='utf-8'))['items']
    output=Path(run_dir)/service/'calls'; proposal=None
    def old(label,arm): return json.loads((Path(run_dir)/arm/'calls'/(label+'.json')).read_text())
    try:
        output.mkdir()
        if service=='A':
            a1=collect_one(base,model,'A1',inputs['long'],output); a2=collect_one(base,model,'A2',inputs['long'],output)
            write(output/'same_process_second_cache.json',a2['cached_tokens_observation'])
            comparable(a1,a2)
        elif service=='B':
            b=collect_one(base,model,'B1',inputs['long'],output); comparable(old('A1','A'),b); comparable(old('A2','A'),b)
        elif service=='C':
            c,_=pair(base,model,[('C_long',inputs['long']),('C_short',inputs['short'])],output)
            baseline=old('A1','A'); comparable(baseline,c,('finish_reason','usage'))
            observation=baseline['projection']['text']!=c['projection']['text']
            records=pair(base,model,[('C_alpha',inputs['alpha']),('C_beta',inputs['beta'])],output)
            for record,key,other in zip(records,('alpha','beta'),('beta','alpha')):
                discriminate(record['projection']['text'],inputs[key]['marker'],inputs[other]['marker'])
            proposal={'schema':'ft_r065_d16_criteria/v1','rid':'E2-R065-d16-discriminate',
                'proposed_verdict':'passed_R065_criteria','handoff_ready':True,'services':3,'calls':7,
                'batch_invariance_difference_reproduced':observation,'short_Y_is_numeric_evidence':False,
                'limits':['API overlap does not prove physical batching','cached_tokens missing is not zero','R063 requires separate handoff']}
        else: raise ValueError('unapproved service')
        write(output/'service_result.json',{'service':service,'passed':True,'calls':{'A':2,'B':1,'C':4}[service]})
        if proposal: write(Path(run_dir)/'criteria_result.json',proposal)
    except BaseException as exc:
        result=Path(run_dir)/'criteria_result.json'
        if not result.exists(): write(result,{'schema':'ft_r065_d16_criteria/v1','rid':'E2-R065-d16-discriminate','proposed_verdict':'not_met' if isinstance(exc,CriterionMismatch) else 'failed_harness','handoff_ready':False,'failed_service':service,'reason':str(exc),'exception_type':type(exc).__name__})
        raise
