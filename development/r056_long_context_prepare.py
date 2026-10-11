#!/usr/bin/env python3
"""E2-R056 production performance at 0.88 / 98304; inert without --run."""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,math,os,shlex,shutil,statistics,subprocess,sys,time
from pathlib import Path

RID='E2-R056';CANDIDATE='0aa23431e5b800797543bdecbf35a01045131d7d'
ROOT=Path('/data2/FreeToken');WT=ROOT/'wt/e2base1-ordinary-rewind';VENV=ROOT/'venv'
ROUNDS=Path('/data2/_shared/runs/ft_rounds');HERE=Path(__file__).resolve().parent
D07_SOURCE=HERE/'d07_g3g4_prepare.py';FILE_PREP_SOURCE=HERE/'d07_r046a_file_prepare_v1.py'
OBSERVER=HERE/'r056_performance_memory_observer.py';MODEL='Qwen3.8-Flash-Next-NVFP4'
PROBE=ROOT/'scripts/probe_ft_cold32k.py';PROBE_SHA='b97190f589f7383972f0799ec0855bfd76e0f0b928e13ebc3696644d970de88b'
PERF=ROOT/'scripts/ft_perf_decomp.py';PERF_SHA='949a18a521c8243cdd42d1deed0ab12544bc16e8e076b0dbb1251ac3dfb872cd'
AGENT=WT/'scripts/_agent_trace_original.py';AGENT_SHA='332a1870378d5bffa4891180280060e70f6135b6acff21b48603a5fc98ad44d9'
SEED=ROOT/'wt/e1r003/seed_real.txt';SEED_SHA='8fe6b36da6c19eabb4a259535a9835f20e41921d4d7023ec7aaa0063c8b50bf3'
INPUT_REVIEW=ROOT/'runs/dev_R056/r056_seed_real_cpu_input_v1.json';INPUT_REVIEW_SHA='770071f74ede52ae0e6ba6de012785847bd6ca118637e43e3667f50ccb2d54bc'
BASELINE=ROOT/'runs/dev_D17/t20_live_performance_r_overlap_20261006_2257/review.json'
BASELINE_SHA='04abeb2657b7b0da693ad6d43ca03da6f2098fff122ad06c244512d4c2b147ce'
HISTORICAL_ARGS=ROUNDS/'E2-R040/PRODUCTION/args_preprobe_checked.json'
HISTORICAL_ARGS_SHA='6816c859626948e89d0e7a089fb0d08ae7d4c2c534bc9fb3fa917cd464ac171b'
WRITER=ROOT/'scripts/round_json_append.py';WRITER_SHA='67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff'
REVIEW_DIR=ROOT/'runs/dev_R056/reviews/E2-R056-v2'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def encoded(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def digest(value):return hashlib.sha256(encoded(value)).hexdigest()
def wire_digest(spec,payload):
    # Preserve insertion order and the exact JSON defaults of each real sender.
    body=json.dumps(payload,ensure_ascii=False) if spec['kind']=='cold87' else json.dumps(payload)
    return hashlib.sha256(body.encode('utf-8')).hexdigest()
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as out:json.dump(value,out,ensure_ascii=False,indent=2,sort_keys=True);out.write('\n')
def module(path):
    spec=importlib.util.spec_from_file_location('r056_'+path.stem,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def sealed(path,expected):
    if not isinstance(expected,str) or len(expected)!=64 or path.is_symlink() or not path.is_file() or path.stat().st_mode&0o222 or sha(path)!=expected:raise RuntimeError('R056 sealed source/review binding differs: '+str(path))
    return json.loads(path.read_text())
def load_d07():
    d=module(D07_SOURCE);d.CANDIDATE=CANDIDATE;d.WORKTREE=WT;d.RID=RID
    original=d.serve_argv
    def arguments(port):
        argv=original(port)
        for key,value in (('--memory-ratio','0.88'),('--kv-reserve-tokens','98304'),('--max-seq-len-override','98304')):argv[argv.index(key)+1]=value
        return argv
    d.serve_argv=arguments;return d
def source_paths():return (Path(__file__).resolve(),D07_SOURCE,FILE_PREP_SOURCE,OBSERVER,PROBE,PERF,AGENT,INPUT_REVIEW,BASELINE,HISTORICAL_ARGS,WRITER)


def input_review():
    r=sealed(INPUT_REVIEW,INPUT_REVIEW_SHA)
    request=r.get('request',{});window=r.get('window',{});frontend=r.get('frontend',{})
    if (r.get('schema')!='ft_r056_seed_real_cpu_input_review/v1' or r.get('rid')!=RID or r.get('candidate_commit')!=CANDIDATE or r.get('candidate_worktree')!=str(WT) or r.get('seed',{}).get('sha256')!=SEED_SHA or request.get('prompt_tokens')!=87100 or request.get('max_tokens')!=2048 or request.get('thinking_requested') is not True or request.get('tools_count')!=3 or window.get('kv_reserve_tokens')!=98304 or window.get('max_seq_len_override')!=98304 or r.get('verdict')!='CPU_INPUT_BINDING_PASS' or r.get('source_modules_sha256',{}).get(str(AGENT))!=AGENT_SHA or frontend.get('handler_messages_equal_wire') is not True or frontend.get('handler_template_tools_equal_wire') is not True):raise RuntimeError('R056 release-tree actual input review differs')
    if request['prompt_tokens']+request['max_tokens']>98304 or window.get('input_plus_output_tokens')!=89148:raise RuntimeError('R056 prompt plus original completion budget exceeds window')
    return r
def packet():
    r=input_review();d=load_d07();candidate=d.checked_worktree(WT)
    for path,expected in ((PROBE,PROBE_SHA),(PERF,PERF_SHA),(AGENT,AGENT_SHA),(SEED,SEED_SHA),(WRITER,WRITER_SHA)):
        if path.is_symlink() or not path.is_file() or sha(path)!=expected:raise RuntimeError('R056 scientific source SHA differs: '+str(path))
    for name,expected in r['source_modules_sha256'].items():
        if sha(Path(name))!=expected:raise RuntimeError('R056 actual frontend source changed: '+name)
    for name,record in r.get('model_assets',{}).items():
        if sha(Path(name))!=record['sha256']:raise RuntimeError('R056 tokenizer/config asset changed: '+name)
    old=sealed(BASELINE,BASELINE_SHA);args=sealed(HISTORICAL_ARGS,HISTORICAL_ARGS_SHA)
    if old.get('rid')!='E2-R040' or args.get('kv_reserve_tokens')!='73728' or args.get('max_seq_len_override')!='73728':raise RuntimeError('R056 historical actual-window metadata differs')
    return {'schema':'ft_r056_packet/v1','rid':RID,'candidate_commit':CANDIDATE,'candidate':candidate,'input_review':r,
            'memory_ratio':'0.88','window':98304,'requests':11,'services':3,'first_shot':'production/cold32_0',
            'historical_window':73728,'comparison_scope':'cross-window observation; no same-window benefit verdict',
            'baseline_sha256':BASELINE_SHA,'historical_args_sha256':HISTORICAL_ARGS_SHA,
            'no_d0_route_pause':True,'authorization':'CODEX_HANDOFF section twelve'}


def real_seed_payload():
    if sha(SEED)!=SEED_SHA or sha(AGENT)!=AGENT_SHA:raise RuntimeError('R056 original seed/agent bytes changed')
    agent=module(AGENT);tools=getattr(agent,'tool_specs',None) or getattr(agent,'agent_tools',None)
    if not callable(tools):raise RuntimeError('R056 original agent tools function absent')
    payload=agent.build_payload([{'role':'user','content':SEED.read_text(encoding='utf-8')+'\n\n'+agent.TASK_PROMPT}],MODEL,tools(),True,2048)
    r=input_review()
    if digest(payload)!=r['request'].get('payload_canonical_sha256') or hashlib.sha256(json.dumps(payload,ensure_ascii=False).encode()).hexdigest()!=r['request'].get('payload_wire_sha256'):raise RuntimeError('R056 actual seed first-request payload SHA differs')
    return payload
def request_specs():
    return ([{'name':f'cold32_{i}','kind':'cold32','target':32052,'prompt_tokens':32064,'max_tokens':128} for i in range(4)]
            +[{'name':f'cold64_{i}','kind':'cold64','target':65412,'prompt_tokens':65424,'max_tokens':128} for i in range(2)]
            +[{'name':f'short_{i}','kind':'short','prompt_tokens':23,'max_tokens':128} for i in range(3)]
            +[{'name':f'cold87_{i}','kind':'cold87','prompt_tokens':87100,'max_tokens':2048} for i in range(2)])
def payloads():
    probe=module(PROBE);perf=module(PERF);tok=probe.AutoTokenizer.from_pretrained(probe.MODEL_DIR,trust_remote_code=True,local_files_only=True)
    long=real_seed_payload();result=[]
    for spec in request_specs():
        if spec['kind']=='cold87':payload=json.loads(json.dumps(long,ensure_ascii=False))
        else:
            text=perf.SHORT_PROMPT
            if spec['kind']!='short':
                text,built=probe.build_text(tok,spec['target'],RID+'-production-'+spec['name'])
                if built!=spec['target']:raise RuntimeError('R056 original cold builder length differs')
            payload={'model':MODEL,'messages':[{'role':'user','content':text}],'max_tokens':128,'temperature':0,
                     'stream':True,'stream_options':{'include_usage':True},'chat_template_kwargs':{'enable_thinking':False}}
        result.append((spec,payload))
    return result
def probe(path,purpose):write(path,{'schema':'ft_r056_cpu_file_probe/v1','not_measurement':True,'purpose':purpose})
def prepare_request(directory,spec,payload,*,file_dry_run):
    directory.mkdir(parents=True,exist_ok=True);write(directory/'request.json',payload)
    write(directory/'inputs.json',{'schema':'ft_r056_request_input/v1',**spec,'payload_canonical_sha256':digest(payload),
                                  'payload_wire_sha256':wire_digest(spec,payload),
                                  'source_probe_sha256':PROBE_SHA,'source_perf_sha256':PERF_SHA,'source_agent_sha256':AGENT_SHA,
                                  'seed_sha256':SEED_SHA if spec['kind']=='cold87' else None})
    (directory/'stream.jsonl').open('x').close()
    if file_dry_run:probe(directory/'result.json','formal per-request performance result')


def prepare_service(d,directory,port,observe,*,start):
    prepared=module(FILE_PREP_SOURCE).prepare_server_files(d,directory,WT,port,None)
    env=prepared['env']
    for key in list(env):
        if key.startswith(('R055','R056')):env.pop(key)
    if any(key.startswith('FT_DEV') for key in env):raise RuntimeError('R056 production dev instrumentation leaked')
    env.update(R056_MODEL_MEMORY=str(directory/'model_memory.jsonl'),R056_OBSERVE_REQUESTS=str(int(observe)))
    prepared['argv']=['taskset','-c','1,3-47',str(VENV/'bin/python'),str(OBSERVER),*prepared['argv'][1:]]
    write(directory/'serve_argv.json',{'argv':prepared['argv']})
    record={key:env[key] for key in ('PYTHONPATH','VIRTUAL_ENV','CUDA_VISIBLE_DEVICES','R056_MODEL_MEMORY','R056_OBSERVE_REQUESTS')}
    (directory/'ENV.json').write_text(json.dumps(record,sort_keys=True)+'\n')
    (directory/'ENV.txt').write_text(''.join(f'{key}={record[key]}\n' for key in sorted(record)))
    (directory/'SERVE_CMD.txt').write_text('env '+' '.join(f'{key}={shlex.quote(value)}' for key,value in record.items())+' '+shlex.join(prepared['argv'])+'\n')
    if not start:
        for name in ('owned_process.json','health.json','serve_args.txt','model_memory.jsonl','startup_memory.json','memory_summary.json'):probe(directory/name,'formal service lifecycle/memory output')
        return prepared
    return module(FILE_PREP_SOURCE).start_prepared_server(d,directory,WT,port,prepared)
def memory_rows(directory,process,*,complete=False):
    rows=[json.loads(line) for line in (directory/'model_memory.jsonl').read_text().splitlines() if line.strip()]
    loaded=[row for row in rows if row.get('event')=='model_loaded']
    if len(loaded)!=1:raise RuntimeError('R056 actual model-loaded sample absent')
    base=loaded[0];owned=json.loads((directory/'owned_process.json').read_text())['birth'];stable=('pid','start_ticks','execution_id','pgid','session')
    if any(base['service_birth'].get(key)!=owned.get(key) for key in stable) or owned.get('pid')!=process.pid:raise RuntimeError('R056 model sample owned birth differs')
    if type(base.get('kv_storage_bytes')) is not int or base['kv_storage_bytes']<=0 or base.get('max_seq_len')!=98304:raise RuntimeError('R056 actual KV allocation/window sample differs')
    for row in rows:
        if (row.get('schema')!='ft_r056_model_memory/v1' or row.get('device')!=0 or row.get('service_birth')!=base['service_birth'] or row.get('worker_birth')!=base['worker_birth'] or 'error' in row or type(row.get('free_bytes')) is not int or type(row.get('total_bytes')) is not int or not 0<=row['free_bytes']<=row['total_bytes']):raise RuntimeError('R056 model-process memory identity/sample differs')
    if complete:
        before=[row for row in rows if row['event']=='request_before'];after=[row for row in rows if row['event']=='request_after']
        if len(before)!=1 or len(after)!=1 or not before[0].get('uid') or before[0]['uid']!=after[0]['uid'] or before[0]['time_ns']>=after[0]['time_ns']:raise RuntimeError('R056 87k real request-before/after boundary incomplete')
    return {'schema':'ft_r056_memory_summary/v1','model_loaded':base,'events':rows,'min_free_bytes':min(row['free_bytes'] for row in rows),
            'memory_jsonl_sha256':sha(directory/'model_memory.jsonl'),'request_complete':complete}
def startup(directory,process):
    text=(directory/'serve.log').read_text(errors='replace')
    for expected in ('memory_ratio=0.88','kv_reserve_tokens=98304','max_seq_len_override=98304'):
        if expected not in text:raise RuntimeError('R056 parsed production argument absent: '+expected)
    if 'Free memory after initialization:' not in text or 'R056_MODEL_LOADED' not in text:raise RuntimeError('R056 actual initialization/KV/free log evidence absent')
    if any(marker in text for marker in ('D0 instrumentation enabled','CUDA graph disabled for development route trace','D0 prefill')):raise RuntimeError('R056 production instrumentation marker leaked')
    summary=memory_rows(directory,process);write(directory/'startup_memory.json',summary);return summary


def positive(value):return type(value) in (int,float) and math.isfinite(value) and value>0
def check_result(spec,record):
    if record.get('prompt_tokens')!=spec['prompt_tokens'] or type(record.get('completion_tokens')) is not int or not 1<record['completion_tokens']<=spec['max_tokens'] or record.get('finish_reason') not in ('stop','length','tool_calls'):raise RuntimeError('R056 actual request usage/terminal shape differs')
    if spec['kind']=='cold87':
        if record.get('cached_tokens') not in (None,0):raise RuntimeError('R056 87k fresh service was not cold')
        if not positive(record.get('ttft_any_s')) or not positive(record.get('decode_any_tps')):raise RuntimeError('R056 87k any-delta timing incomplete')
    elif not positive(record.get('ttft_s')) or not positive(record.get('decode_tps')) or (spec['kind']!='short' and record.get('cached_tokens')!=0):raise RuntimeError('R056 T20 content timing/cold evidence incomplete')
    return record
def measure(directory,spec,payload,port):
    url=f'http://127.0.0.1:{port}/v1/chat/completions'
    if port==8095:raise RuntimeError('R056 forbidden endpoint')
    if spec['kind']=='cold87':
        agent=module(AGENT);times=[];t0=time.perf_counter()
        def stream():
            with (directory/'stream.jsonl').open('a',encoding='utf-8') as out:
                for event in agent.post_events(url,payload,1800):
                    when=time.perf_counter();out.write(json.dumps({'relative_seconds':when-t0,'event':event},ensure_ascii=False)+'\n')
                    for choice in event.get('choices') or []:
                        delta=choice.get('delta') or {}
                        if delta.get('reasoning_content') or delta.get('reasoning') or delta.get('content') or any((call.get('function') or {}).get('arguments') for call in delta.get('tool_calls') or []):times.append(when)
                    yield event
        result=agent.consume_stream(stream(),t0);usage=result.get('usage',{});details=usage.get('prompt_tokens_details') or {}
        count=usage.get('completion_tokens');record={**result,'prompt_tokens':usage.get('prompt_tokens'),'completion_tokens':count,
                'original_agent_ttft_any_s':result.get('ttft_any_s'),'ttft_any_s':round(times[0]-t0,3) if times else None,
                'cached_tokens':details.get('cached_tokens'),'cached_tokens_reported':'cached_tokens' in details,
                'fresh_process_cold_proof_required':True,'decode_any_tps':(count-1)/(times[-1]-times[0]) if type(count) is int and len(times)>=2 and times[-1]>times[0] else None,
                'metric_basis':'raw SSE arrival ttft_any/decode from reasoning/content/tool deltas; original agent ttft retained as observation; not T20 content-only timing',
                'stream_first_any_seconds':times[0]-t0 if times else None,'stream_last_any_seconds':times[-1]-t0 if times else None}
    else:
        perf=module(PERF);t0,events,usage,finish,text=perf.post_stream(url,payload)
        record={**perf.summarize(t0,events,usage),'finish_reason':finish,'completion_text':text,'metric_basis':'original T20 content-only',
                'relative_content_events':[when-t0 for when in events],'raw_usage':usage}
        with (directory/'stream.jsonl').open('a') as out:out.write(json.dumps({'relative_content_events':record['relative_content_events'],'usage':usage,'finish_reason':finish})+'\n')
    write(directory/'result.json',{**record,'request_payload_sha256':digest(payload),'spec':spec});return check_result(spec,record)


def comparison(records):
    old=sealed(BASELINE,BASELINE_SHA)['performance'];observations=[]
    for kind,source,key in (('cold32','cold32_excluding_first','ttft_s'),('cold32','cold32_excluding_first','decode_tps'),('cold64','cold64','ttft_s'),('cold64','cold64','decode_tps'),('short','short','ttft_s'),('short','short','decode_tps')):
        values=[record[key] for spec,record in records if spec['kind']==kind and (kind!='cold32' or spec['name']!='cold32_0')]
        current=statistics.median(values);historical=old[source].get(key)
        if historical is None:historical=statistics.median(row[key] for row in old[source]['values'])
        observations.append({'kind':kind,'metric':key,'current':current,'historical':historical,'relative_change':(current-historical)/historical})
    return {'schema':'ft_r056_cross_window_observation/v1','current_window':98304,'historical_window':73728,'historical_summary_sha256':BASELINE_SHA,
            'scope':'cross-window observation authorized by section twelve; no same-window benefit/7-percent verdict',
            'first_shot_current':records[0][1],'historical_first_shot':None,'historical_first_shot_nullreason':'bound small summary omits first shot; do not reopen raw or invent it',
            'observations':observations}


def canonical(wt,out):
    if wt!=WT or out!=ROUNDS or any(path.is_symlink() for p in (wt,out) for path in (p,*p.parents)):raise RuntimeError('R056 canonical worktree/output path differs')
def archive(directory):
    result=[]
    target=directory/'runtime_sources';target.mkdir()
    for source in source_paths():
        copy=target/source.name
        if source.is_symlink() or not source.is_file():raise RuntimeError('R056 runtime source absent')
        shutil.copyfile(source,copy);copy.chmod(0o600)
        result.append({'source':str(source),'sha256':sha(source),'copy':str(copy),'copy_sha256':sha(copy)})
    return result
def dry_directory(out):return out/'.dryrun_R056_v2_E2-R056'
def run_services(d,run,requests,*,file_dry_run):
    records=[]
    for name,selected in (('production',requests[:9]),('cold87_0',requests[9:10]),('cold87_1',requests[10:11])):
        directory=run/name;process=None;port=d.dynamic_fixture_port()
        if file_dry_run:
            prepare_service(d,directory,port,name!='production',start=False)
            for spec,payload in selected:prepare_request(directory/spec['name'],spec,payload,file_dry_run=True)
            continue
        try:
            process=prepare_service(d,directory,port,name!='production',start=True);startup(directory,process)
            for spec,payload in selected:
                request=directory/spec['name'];prepare_request(request,spec,payload,file_dry_run=False)
                if process.poll() is not None:raise RuntimeError('R056 owned performance service exited')
                record=measure(request,spec,payload,port);records.append((spec,record))
                write(run/f'completed_{spec["name"]}.json',{'schema':'ft_r056_incremental_request/v1','spec':spec,'result':str(request/'result.json'),'result_sha256':sha(request/'result.json'),'completed_requests':len(records)})
            summary=memory_rows(directory,process,complete=name!='production');write(directory/'memory_summary.json',summary)
        except BaseException as error:
            process=getattr(error,'owned_process',process);error.owned_process=process;raise
        finally:
            active=sys.exc_info()[1]
            if process is not None and not getattr(active,'owned_cleanup_failed',False):
                try:
                    lifecycle=d.load_owned_lifecycle();lifecycle.stop_owned_process(process)
                    if lifecycle.owned_group_alive(process.pid):raise RuntimeError('R056 owned group remains after cleanup')
                except BaseException as error:error.owned_process=process;error.owned_cleanup_failed=True;raise
    return records
def dry_run(wt=WT,out=ROUNDS):
    if sys.platform!='linux':raise RuntimeError('R056 file dry requires Linux')
    canonical(wt,out);admission=packet();requests=payloads();target=dry_directory(out)
    target.mkdir(mode=0o700,exist_ok=False);sources=archive(target);run_services(load_d07(),target,requests,file_dry_run=True)
    for spec,_ in requests:probe(target/f'completed_{spec["name"]}.json','formal incremental review receipt')
    for name in ('result.json','comparison.json','manifest.json','preflight.json','failed_harness.json','owned_cleanup.json','metadata/pre_d04.json'):probe(target/name,'formal round producer path')
    receipt={'schema':'ft_r056_file_dry/v2','rid':RID,'candidate_commit':CANDIDATE,'passed':True,'owner':{'path':str(Path(__file__).resolve()),'uid':os.getuid(),'user':os.environ.get('USER')},
             'cwd':os.getcwd(),'worktree':str(wt),'sources':{row['source']:row['sha256'] for row in sources},'packet_sha256':digest(admission),
             'service_started':False,'requests_sent':False,'gpu_lock_taken':False,'batch_allocated':False,'formal_rid_created':False}
    write(target/'dry_run_receipt.json',receipt);(target/'dry_run_receipt.json').chmod(0o444);return receipt
def admission_receipts(out):
    path=dry_directory(out)/'dry_run_receipt.json'
    if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o222:raise RuntimeError('R056 exact file dry receipt missing/writable')
    value=json.loads(path.read_text());owner={'path':str(Path(__file__).resolve()),'uid':os.getuid(),'user':os.environ.get('USER')}
    if value.get('schema')!='ft_r056_file_dry/v2' or value.get('rid')!=RID or value.get('candidate_commit')!=CANDIDATE or value.get('passed') is not True or value.get('owner')!=owner or value.get('cwd')!=str(ROOT) or value.get('worktree')!=str(WT) or value.get('sources')!={str(p):sha(p) for p in source_paths()} or any(value.get(key) is not False for key in ('service_started','requests_sent','gpu_lock_taken','batch_allocated','formal_rid_created')):raise RuntimeError('R056 exact file dry receipt identity/source differs')
    review=REVIEW_DIR/'review.json';pin=REVIEW_DIR/'pin.json'
    binding=sealed(pin,sha(pin));document=sealed(review,binding.get('review_sha256'))
    if binding.get('schema')!='ft_r056_review_pin/v2' or binding.get('rid')!=RID or document.get('schema')!='ft_r056_startup_review/v2' or document.get('rid')!=RID or document.get('candidate_commit')!=CANDIDATE or document.get('verdict')!='PASS' or document.get('source_execution_ready') is not True or document.get('sources')!=value['sources'] or document.get('dry_receipt_path')!=str(path) or document.get('dry_receipt_sha256')!=sha(path):raise RuntimeError('R056 independent startup review binding differs')
    return {'dry_path':str(path),'dry_sha256':sha(path),'review_path':str(review),'review_sha256':sha(review)}
def child_argv(batch,receipt):return [str(VENV/'bin/python'),str(Path(__file__).resolve()),'--run','--owned-child','--batch',str(batch),'--launch-receipt',str(receipt)]
def execute(*,owned_child=False,batch=None,launch_receipt=None):
    if sys.platform!='linux':raise RuntimeError('R056 requires Linux GPU host')
    canonical(WT,ROUNDS);d=load_d07()
    if not owned_child and (d.LOCK.exists() or d.LOCK.is_symlink()):raise RuntimeError('R056 foreign GPU lock; remain queued')
    preflight=packet();proof=admission_receipts(ROUNDS);requests=payloads()
    if (ROUNDS/RID).exists():raise RuntimeError('R056 round exists; no retry in place')
    if not owned_child:
        owned=d.load_owned_lifecycle();helper=owned.verified_module(ROOT/'runs/plan_batches/e2_launch.py',d.ATOMIC_HELPER_SHA,'r056_atomic')
        batch=helper.next_batch(ROUNDS);receipt=ROOT/'runs/dev_R056'/f'launch_{RID}_batch{batch}.json';receipt.parent.mkdir(parents=True,exist_ok=True);argv=child_argv(batch,receipt)
        reserved={'schema':'ft_r056_owned_launch/v1','state':'reserved','rid':RID,'batch':batch,'candidate_commit':CANDIDATE,'argv_sha256':d.argv_sha256(argv),'controller':d.process_birth()}
        launched=owned.reserve_process(helper,batch,RID,argv,receipt,reserved);birth=owned.process_identity(launched['batch_pid'])
        if birth is None:raise RuntimeError('R056 reserved child birth absent')
        child={key:birth[key] for key in ('pid','start_ticks','execution_id')};return d.publish_child_binding(receipt,launched,child,lifecycle=owned)
    if batch is None or launch_receipt is None:raise RuntimeError('R056 child requires reserved batch/receipt')
    d.require_child_receipt(launch_receipt,batch,WT,ROUNDS,rid=RID,expected_argv=child_argv(batch,launch_receipt),schema='ft_r056_owned_launch/v1')
    owner=d.take_d07_gpu_lock(RID,batch);run=None;preserve_lock=False
    try:
        gpu=d.require_gpu_idle();run=ROUNDS/RID;run.mkdir();archive(run);write(run/'preflight.json',{**preflight,'batch':batch,'gpu_owner':owner,'gpu_memory_mib':gpu,'startup_proof':proof})
        records=run_services(d,run,requests,file_dry_run=False);write(run/'comparison.json',comparison(records))
        manifest={path.relative_to(run).as_posix():sha(path) for path in run.rglob('*') if path.is_file()};write(run/'manifest.json',{'schema':'ft_r056_raw_manifest/v1','rid':RID,'candidate_commit':CANDIDATE,'files':manifest})
        result={'schema':'ft_r056_performance_raw/v1','round_id':RID,'candidate_commit':CANDIDATE,'batch':batch,'card':'long-context-release','verdict':'pending_review','proposed_verdict':'measured','memory_ratio':'0.88','window':98304,'requests':[{**spec,'record':record} for spec,record in records],'first_shot':records[0][1],'comparison':'comparison.json','manifest_sha256':sha(run/'manifest.json'),'performance_oom_requires_user_disposition':True}
        write(run/'result.json',result);write(run/'metadata/pre_d04.json',{'schema':'ft_r056_pre_d04/v1','round_id':RID,'candidate_commit':CANDIDATE,'verdict':'pending_review','proposed_verdict':'measured','result_sha256':sha(run/'result.json'),'canonical_round_created':False});return result
    except BaseException as error:
        preserve_lock=bool(getattr(error,'owned_cleanup_failed',False))
        if run is not None:write(run/'failed_harness.json',{'rid':RID,'batch':batch,'error':repr(error),'user_disposition_required':True,'raw_preserved':True,'owned_cleanup_failed':preserve_lock})
        raise
    finally:
        if not preserve_lock:d.release_d07_gpu_lock(owner)
        if run is not None:write(run/'owned_cleanup.json',{'rid':RID,'batch':batch,'lock_released':not preserve_lock,'owned_cleanup_failed':preserve_lock})
def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);choice=parser.add_mutually_exclusive_group();choice.add_argument('--run',action='store_true');choice.add_argument('--dry-run',action='store_true');parser.add_argument('--owned-child',action='store_true');parser.add_argument('--batch',type=int);parser.add_argument('--launch-receipt',type=Path);args=parser.parse_args(argv)
    value=execute(owned_child=args.owned_child,batch=args.batch,launch_receipt=args.launch_receipt) if args.run else dry_run() if args.dry_run else packet()
    print(json.dumps(value,ensure_ascii=False,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
