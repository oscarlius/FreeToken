"""Official SDK canary transport; product failures and probe validity are separate."""
from __future__ import annotations
import concurrent.futures, importlib.util, json, re, threading, time, unicodedata
from pathlib import Path
import httpx
from openai import OpenAI
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('r066b_frozen_sdk',HERE.parents[1]/'evaluation/d16_api/sdk_completions.py')
sdk=importlib.util.module_from_spec(spec); spec.loader.exec_module(sdk)
class ProductMismatch(ValueError): pass

def write(path,value):
    with Path(path).open('x',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,sort_keys=True,indent=2); f.write('\n')

def request(item):
    return dict(model='Qwen3.8-Flash-Next-NVFP4',prompt=item['prompt'],max_tokens=32,temperature=0,top_p=1,stream=True,stream_options={'include_usage':True},extra_body={'ignore_eos':False})

def project32(chunks,prompt_tokens):
    text=[]; finish=usage=identity=None
    for chunk in chunks:
        current=chunk.get('id'); choices=chunk.get('choices')
        if not isinstance(current,str) or not current or (identity is not None and current!=identity): raise ValueError('stream identity differs')
        identity=current
        if not isinstance(choices,list) or len(choices)>1: raise ValueError('invalid choices')
        if choices:
            choice=choices[0]
            if finish is not None or choice.get('index')!=0 or not isinstance(choice.get('text'),str): raise ValueError('invalid terminal choice')
            text.append(choice['text']); finish=choice.get('finish_reason')
            if finish is not None and finish not in ('stop','length'): raise ValueError('unsupported finish')
        if chunk.get('usage') is not None:
            if usage is not None: raise ValueError('duplicate usage')
            usage=chunk['usage']; sdk._usage(usage)
    normalized=sdk._usage(usage)
    if finish not in ('stop','length') or normalized['prompt_tokens']!=prompt_tokens or normalized['completion_tokens']>32 or (finish=='length' and normalized['completion_tokens']!=32): raise ValueError('32-token finish/usage contract differs')
    details=usage.get('prompt_tokens_details'); cached=details.get('cached_tokens') if isinstance(details,dict) else None
    if cached is not None and (type(cached) is not int or not 0<=cached<=prompt_tokens): raise ValueError('invalid cached_tokens')
    joined=''.join(text)
    if any(unicodedata.category(c)=='Cs' for c in joined): raise ValueError('invalid surrogate in SDK text')
    return {'text':joined,'finish_reason':finish,'usage':normalized,'completion_id':identity},{'status':'missing' if cached is None else 'reported','value':cached,'fallback_used':False}

def collect(base,label,item,out,ready=None,state=None):
    client=OpenAI(base_url=base.rstrip('/')+'/v1',api_key='r066b-api-only',max_retries=0,timeout=900,http_client=httpx.Client(trust_env=False))
    started=time.monotonic(); event=None; req=request(item); art={'request':sdk._wire_request(req),'response':None,'chunks':[]}
    try:
        raw=client.with_raw_response.completions.create(**req)
        art['response']={'status_code':raw.status_code,'headers':dict(raw.headers)}
        for chunk in raw.parse():
            data=chunk.model_dump(mode='json'); now=time.monotonic(); art['chunks'].append({'arrival_seconds':now-started,'data':data})
            if event is None and any(c.get('text') for c in data.get('choices',[])):
                event=now
                if ready: ready.set()
        art['projection'],art['cached_tokens_observation']=project32((c['data'] for c in art['chunks']),item['prompt_tokens'])
        return art
    except BaseException as exc:
        art['error']={'type':type(exc).__name__,'message':str(exc)}
        if state is not None: state['failed']=True
        raise sdk.CompletionCollectionError(art,exc) from exc
    finally:
        art['client']={'label':label,'started_seconds':started,'completed_seconds':time.monotonic(),'first_nonempty_seconds':event}
        write(Path(out)/(label+'.json'),art); client.close()
        if ready: ready.set()

def assess(record,item):
    text=record['projection']['text']; other=item['other_marker'] in text
    malformed=any(c=='\ufffd' or (unicodedata.category(c)=='Cc' and c not in '\n\r\t') for c in text)
    if other or malformed: raise ProductMismatch('other marker' if other else 'U+FFFD or illegal control')
    return item['own_marker'] in text

def cached_rows(text):
    return [{'new_sequences':int(s),'new_tokens':int(n),'cached_tokens':int(c)} for s,n,c in re.findall(r'Prefill batch, #new-seq: (\d+), #new-token: (\d+), #cached-token: (\d+)',text)]

def cache_scope(cache,rows,prompt_total,warm):
    positive=[r['cached_tokens'] for r in rows if r['cached_tokens']>0]
    backend_met=bool(rows) and ((len(positive)==1 and positive[0]>=8192 and rows[0]['cached_tokens']==0 and sum(r['new_tokens'] for r in rows)+positive[0]==prompt_total) if warm else (not positive and sum(r['new_tokens'] for r in rows)==prompt_total))
    api_met=all(c is not None for c in cache) and ((cache[0]==0 and cache[1]>=8192) if warm else cache==[0,0])
    api_consistent=all(c is None or (c==0 if not warm or i==0 else c>=8192) for i,c in enumerate(cache))
    return api_consistent and (backend_met or (not rows and api_met))

def pair(base,items,out,warm,log=None):
    ready=threading.Event(); state={}; barrier=threading.Barrier(2)
    offset=Path(log).stat().st_size if log else None
    def one(index,label,item):
        if warm and index==1:
            if not ready.wait(900): raise TimeoutError('first SDK stream never progressed')
            if state.get('failed'): raise RuntimeError('first SDK call failed; second not sent')
        if not warm: barrier.wait(30)
        return collect(base,label,item,out,ready if warm and index==0 else None,state if warm and index==0 else None)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        fs=[pool.submit(one,i,label,item) for i,(label,item) in enumerate(items)]
        records=[f.result() for f in fs]
    windows=[(r['client']['started_seconds'],r['client']['completed_seconds']) for r in records]
    overlap=max(w[0] for w in windows)<min(w[1] for w in windows)
    rows=[]; end=None
    if log:
        with Path(log).open('rb') as f: f.seek(offset); raw=f.read(); end=f.tell()
        rows=cached_rows(raw.decode('utf-8',errors='replace'))
    cache=[r['cached_tokens_observation']['value'] for r in records]
    prompt_total=sum(r['projection']['usage']['prompt_tokens'] for r in records)
    cache_met=cache_scope(cache,rows,prompt_total,warm)
    first=records[0]['client']['first_nonempty_seconds']
    coverage={'api_windows_overlap':overlap,'first_chunk_order':not warm or (first is not None and windows[1][0]>=first),'cache_scope_met':cache_met,'api_cached_tokens':cache,'backend_rows':rows,'backend_log':str(log) if log else None,'log_start_byte':offset,'log_end_byte':end,'fallback_used':False,'physical_batching_claim':False}
    return records,coverage

def run_service(base,run,inputs=None,pair_fn=pair,log=None):
    run=Path(run); data=inputs or json.loads((HERE/'inputs.json').read_text())['items']; calls=0; retry_used=False; summaries=[]
    result={'schema':'ft_r066b_criteria/v1','rid':'E2-R066b-canary-v2','c_met':False,'handoff_R063':False}
    try:
        for phase,warm,keys in (('pair1',True,('primary_p1_sun','primary_p1_ice')),('pair2',False,('primary_p2_sun','primary_p2_ice'))):
            attempt=0
            while True:
                label=phase+('_alternative' if attempt else ''); out=run/'calls'/label; out.mkdir(parents=True)
                calls+=2
                records,coverage=pair_fn(base,[(k,data[k]) for k in keys],out,warm,log)
                valid=[assess(r,data[k]) for r,k in zip(records,keys)]
                summary={'phase':phase,'template':'alternative' if attempt else 'primary','own_markers_present':valid,'coverage':coverage,'calls':2}
                write(out/'pair_result.json',summary); summaries.append(summary)
                if all(valid) or retry_used: break
                retry_used=True; attempt=1; keys=tuple(k.replace('primary_','alternative_') for k in keys)
            summary['final_for_phase']=True
        final=[s for s in summaries if s.get('final_for_phase')]
        met=all(all(s['own_markers_present']) and all(s['coverage'][k] for k in ('api_windows_overlap','first_chunk_order','cache_scope_met')) for s in final)
        result.update(proposed_verdict='passed_canary' if met else 'probe_invalid',c_met=met,handoff_R063=True,product_failure_observed=False,claim='并发无串扰（共享前缀 + 独立前缀）' if met else None)
    except BaseException as exc:
        result.update(proposed_verdict='not_met' if isinstance(exc,ProductMismatch) else 'failed_harness',reason=str(exc),exception_type=type(exc).__name__,product_failure_observed=isinstance(exc,ProductMismatch))
        raise
    finally:
        result.update(calls=calls,global_template_retry_used=retry_used,pairs=summaries)
        write(run/'criteria_result.json',result)
