"""Two frozen prompts, two requests; backend sampled IDs prove throughput."""
from __future__ import annotations
import argparse,json,threading,time,math
from pathlib import Path
from urllib.request import Request,build_opener,ProxyHandler
HERE=Path(__file__).resolve().parent
PAYLOADS=[json.loads(x) for x in (HERE/'inputs_r045_v7.jsonl').read_text().splitlines()]

def body(row):
    return {'model':'Qwen3.8-Flash-Next-NVFP4','messages':[{'role':'user','content':row['text']}],
            'temperature':0,'top_p':1,'stream':True,'max_tokens':512,'ignore_eos':True,
            'stream_options':{'include_usage':True}}

def put(path,value):
    path.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n',encoding='utf-8')

def run_pair(endpoint,output,timeout):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    barrier=threading.Barrier(2);results=[None,None];errors=[]
    def call(i):
        record={'client':i,'request':body(PAYLOADS[i]),'usage':None,'finish_reason':None,'done':False}
        try:
            barrier.wait(timeout=10);record['submitted_monotonic_ns']=time.monotonic_ns();put(output/f'client{i}.json',record)
            req=Request(endpoint+'/v1/chat/completions',data=json.dumps(record['request']).encode(),headers={'Content-Type':'application/json'})
            with build_opener(ProxyHandler({})).open(req,timeout=timeout) as reply,(output/f'client{i}.sse').open('wb') as raw:
                for line in reply:
                    raw.write(line)
                    if not line.startswith(b'data:'):continue
                    payload=line[5:].strip()
                    if payload==b'[DONE]':record['done']=True;continue
                    if not payload:continue
                    row=json.loads(payload)
                    if row.get('error'):raise RuntimeError(str(row['error']))
                    if row.get('usage') is not None:record['usage']=row['usage']
                    for choice in row.get('choices',[]):
                        if choice.get('finish_reason') is not None:record['finish_reason']=choice['finish_reason']
            record['ended_monotonic_ns']=time.monotonic_ns()
        except BaseException as e:
            record['error']=repr(e);errors.append(repr(e))
        finally:results[i]=record;put(output/f'client{i}.json',record)
    ts=[threading.Thread(target=call,args=(i,)) for i in range(2)]
    for t in ts:t.start()
    for t in ts:t.join(timeout+15)
    if any(t.is_alive() for t in ts):raise RuntimeError('clients exceeded absolute subprocess timeout')
    put(output/'clients.json',results)
    if errors:raise RuntimeError('client failure: '+','.join(errors))
    return results

def evaluate(metrics,samples,clients):
    if len(clients)!=2 or any(not c.get('done') or c.get('finish_reason')!='length' or not isinstance(c.get('usage'),dict) or c['usage'].get('completion_tokens')!=512 for c in clients):
        raise RuntimeError('failed_harness: max512 ignore_eos completion not proven')
    if len(samples)<272:raise RuntimeError('failed_harness: warm16 plus256 paired steps absent')
    pair=samples[0].get('uids')
    if not isinstance(pair,list) or len(pair)!=2 or len(set(pair))!=2:raise RuntimeError('failed_harness: invalid two UID pair')
    metric_by_step={r['step']:r for r in metrics}
    if len(metric_by_step)!=len(metrics):raise RuntimeError('failed_harness: duplicate metrics step')
    paired=[];previous=-1;last_time=0;tail=False
    for sample in samples:
        if sample.get('uids')!=pair or sample.get('step')!=previous+1 or sample.get('completed_monotonic_ns',0)<=last_time or sample.get('timestamp_source')!='after_existing_scheduler_copy_done_and_host_append':raise RuntimeError('failed_harness: noncontinuous UID/step/completion trace')
        previous=sample['step'];last_time=sample['completed_monotonic_ns']
        tokens=sample.get('tokens',[])
        if [t.get('uid') for t in tokens]!=pair:
            tail=True;continue
        if tail:raise RuntimeError('failed_harness: paired decode resumed after terminal tail')
        if any(type(t.get('token_id')) is not int for t in tokens):raise RuntimeError('failed_harness: actual sampled ID absent')
        metric=metric_by_step.get(sample['step'])
        if metric is None or metric.get('uids')!=pair or len(metric.get('lanes',[]))!=2:raise RuntimeError('failed_harness: completed metric missing or UID mismatch')
        if not isinstance(metric.get('gpu_completion_ms'),(int,float)) or not math.isfinite(metric['gpu_completion_ms']) or metric['gpu_completion_ms']<=0:raise RuntimeError('failed_harness: GPU completion elapsed missing')
        if [x.get('uid') for x in metric['lanes']]!=pair:raise RuntimeError('failed_harness: metric lane binding mismatch')
        paired.append(sample)
    measured=paired[16:]
    if len(measured)<256:raise RuntimeError('failed_harness: fewer than256 actual common decode tokens per lane after warm16')
    duration=(measured[-1]['completed_monotonic_ns']-paired[15]['completed_monotonic_ns'])/1e9
    if duration<=0:raise RuntimeError('failed_harness: nonpositive common interval')
    count=[len(measured),len(measured)];speeds=[n/duration for n in count]
    lane_summary=[]
    for i,uid in enumerate(pair):
        rows=[metric_by_step[x['step']]['lanes'][i] for x in measured]
        lookups=sum(r['lookups'] for r in rows);hits=sum(r['hits'] for r in rows)
        lane_summary.append({'uid':uid,'lookups':lookups,'hits':hits,'misses':sum(r['misses'] for r in rows),'hit_rate':hits/lookups if lookups else None,'h2d_bytes':sum(r['h2d_bytes'] for r in rows)})
    return {'verdict':'positive_candidate' if all(x>30 for x in speeds) else 'valid_negative',
            'uids':pair,'warm_paired_steps':16,'common_actual_tokens':count,'duration_s':duration,'lane_tps':speeds,
            'interval_start_ns':paired[15]['completed_monotonic_ns'],'interval_end_ns':measured[-1]['completed_monotonic_ns'],
            'timestamp_source':'backend sampled IDs after existing scheduler copy drain',
            'all_d10_steps':len(metrics),'measured_d10_steps':len(measured),'lane_counters':lane_summary,
            'gpu_completion_ms':[metric_by_step[x['step']]['gpu_completion_ms'] for x in measured],
            'additional_cuda_synchronization':False,'product_acceptance':False}

def main():
    p=argparse.ArgumentParser();p.add_argument('--endpoint',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--timeout',type=float,required=True);p.add_argument('--trace-root',type=Path,required=True);a=p.parse_args()
    clients=run_pair(a.endpoint,a.output,a.timeout)
    metrics=[json.loads(x) for x in (a.trace_root/'raw_d10_steps.jsonl').read_text().splitlines()]
    samples=[json.loads(x) for x in (a.trace_root/'raw_d10_samples.jsonl').read_text().splitlines()]
    result=evaluate(metrics,samples,clients);put(a.output/'measurement.json',result);print(json.dumps(result,sort_keys=True))
if __name__=='__main__':main()
