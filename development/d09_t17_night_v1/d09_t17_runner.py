"""D09 T17 same-structure runner; --run is a root-admitted GPU action."""
from __future__ import annotations

import argparse, hashlib, json, os, re, shutil, signal, socket, struct, subprocess, sys, time
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

HERE = Path(__file__).resolve().parent
RID = 'E2-D09-T17-night-20261009'
INPUTS = HERE / 'D09_T17_EXACT_INPUTS.json'
PROVENANCE = HERE.parent / 'd09_t16_night_v1' / 'd09_native_provenance_v1.json'
REMOTE = Path('/data2/FreeToken/development/d09_t17_night_v1')
RUN = Path(os.environ.get('FT_D09_T17_RUN_ROOT', '/data2/FreeToken/runs/dev_D09')) / RID
PORTS = (31401,31402,31403,31404,31405,31406,31407,31408,31409,31410,31411,31412)
ROW = re.compile(r'Prefill batch, #new-seq: (\d+), #new-token: (\d+), #cached-token: (\d+)')

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def ids_sha(ids): return hashlib.sha256(struct.pack('<%di' % len(ids), *ids)).hexdigest()
def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as h: json.dump(value,h,ensure_ascii=False,indent=2,sort_keys=True); h.write('\n')
def bind_probe(pair):
    held=[]
    try:
        for port in pair:
            s=socket.socket(); s.bind(('0.0.0.0',port)); held.append(s)
    finally:
        for s in held: s.close()
def rows(window): return [{'new_sequences':int(a),'new_tokens':int(b),'cached_tokens':int(c)} for a,b,c in ROW.findall(window)]

def services(inputs):
    answer=[]; index=0
    for cell in inputs['cells']:
        p,t=cell['boundary'],cell['tail']
        for kind in ('coldA','coldB','hot'):
            api,tcp=PORTS[index*2:index*2+2]; index+=1; name=f'{kind}_p{p}_t{t}'
            arm=RUN/'services'/name; wt='/data2/FreeToken/wt/d09-message-boundary-v1'
            argv=['numactl','--cpunodebind=0,1','--interleave=all','/data2/FreeToken/venv/bin/python','-u',str(arm/'t17_startup.py'),'serve','--port',str(api),'--model-path','/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay','--served-model-name','Qwen3.8-Flash-Next-NVFP4','--host','127.0.0.1','--memory-ratio','0.88','--moe-cache-auto','--moe-prefill-hit-d2d','--ple-backend','pinned','--moe-strategy','offload','--quant-backend','moe.nvfp4=triton','--max-running-requests','2','--cuda-graph-max-bs','2','--kv-reserve-tokens','49152','--max-seq-len-override','49152','--max-prefill-length','4096','--enable-cache-report','--enable-special-token-ckpt','--enable-message-boundary-ckpt','--tool-call-parser','qwen3_coder','--reasoning-parser','qwen3','--prefill-layer-major','--mamba-host-slots','0']
            reqs=[{'role':'target','ids':cell['target_ids'],'sha256':cell['target_ids_sha256']}]
            if kind=='hot': reqs=[{'role':'donor','ids':cell['donor_ids'],'sha256':cell['donor_ids_sha256']},*reqs]
            answer.append({'name':name,'kind':kind,'boundary':p,'tail':t,'port_pair':[api,tcp],'worktree':wt,'service_dir':str(arm),'argv':argv,'argv_sha256':hashlib.sha256(json.dumps(argv,separators=(',',':')).encode()).hexdigest(),'requests':reqs})
    return answer

def config():
    data=json.loads(INPUTS.read_text())
    assert len(data['cells'])==2 and sha(PROVENANCE)
    tooling={name:sha(HERE/'tooling'/name) for name in ('t17_exact_ids.py','t17_observe.py','t17_startup.py')}
    return {'schema':'ft_d09_t17_same_structure/v1','rid':RID,'candidate_commit':'c17b69a46cd512fbf3d127d3879bce92caae457b','base_commit':'481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9','inputs_sha256':sha(INPUTS),'native_provenance_sha256':sha(PROVENANCE),'runtime_dependencies':{'inputs':str(INPUTS),'native_provenance':str(PROVENANCE),'tooling_sha256':tooling},'services':services(data),'budget':{'services':6,'generation_calls':8},'admission':{'root_sha_required':True,'gpu_started':False}}

def install_files(arm, tooling_sha):
    source=HERE/'tooling'
    for name in ('t17_exact_ids.py','t17_observe.py','t17_startup.py'):
        assert sha(source/name) == tooling_sha[name]
        shutil.copyfile(source/name,arm/name)
        assert sha(arm/name) == tooling_sha[name]

def request(base, ids, max_tokens=32):
    payload=json.dumps({'input_ids':ids,'max_tokens':max_tokens}).encode()
    with build_opener(ProxyHandler({})).open(Request(base+'/internal/t17/exact-ids',data=payload,headers={'Content-Type':'application/json'}),timeout=1800) as r: return json.loads(r.read())

def validate(service, role, raw, text):
    rs=rows(text); expected_cache=service['boundary'] if service['kind']=='hot' and role=='target' else 0
    expected_new=service['tail'] if expected_cache else len(next(x['ids'] for x in service['requests'] if x['role']==role))
    assert rs and all(r['new_sequences']==1 and r['cached_tokens']==expected_cache for r in rs)
    assert sum(r['new_tokens'] for r in rs)==expected_new
    u=raw['usage']; assert u['prompt_tokens']==expected_new+expected_cache and u['cached_tokens']==expected_cache and u['completion_tokens']==32
    return rs

def run(cfg, execute):
    if RUN.exists(): raise RuntimeError('RID directory already exists')
    RUN.mkdir(parents=True); (RUN/'services').mkdir(); write_new(RUN/'config.json',cfg)
    evidence={}; calls=0; process=None
    try:
        for service in cfg['services']:
            arm=Path(service['service_dir']); arm.mkdir(parents=True); install_files(arm,cfg['runtime_dependencies']['tooling_sha256']); bind_probe(service['port_pair'])
            assert service['argv'].count('--enable-message-boundary-ckpt') == 1
            if not execute:
                process=type('Dry',(),{'pid':-1,'poll':lambda self:None})()
            else:
                env=os.environ.copy(); env.update({'CUDA_VISIBLE_DEVICES':'0','MASTER_PORT':str(service['port_pair'][1]),'PYTHONPATH':str(arm)+':'+service['worktree']+'/python','FT_DEV_STATE_DUMP':str(arm/'state_dump'),'FT_T17_INPUT_RECEIPTS':str(arm/'input_receipts'),'FT_T17_OBSERVATIONS':str(arm/'observations.jsonl'),'PYTHONDONTWRITEBYTECODE':'1'})
                (arm/'state_dump').mkdir(); (arm/'input_receipts').mkdir()
                log=(arm/'serve.log').open('xb'); process=subprocess.Popen(service['argv'],cwd=arm,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                deadline=time.monotonic()+1800
                while True:
                    if process.poll() is not None: raise RuntimeError('service exited before health')
                    try:
                        with build_opener(ProxyHandler({})).open('http://127.0.0.1:'+str(service['port_pair'][0])+'/health',timeout=5) as h:
                            if json.loads(h.read()).get('status')=='ok': break
                    except OSError: pass
                    if time.monotonic()>deadline: raise TimeoutError('health timeout')
                    time.sleep(5)
            for item in service['requests']:
                calls+=1; assert ids_sha(item['ids'])==item['sha256']
                if execute:
                    offset=(arm/'serve.log').stat().st_size; raw=request('http://127.0.0.1:'+str(service['port_pair'][0]),item['ids']); window=(arm/'serve.log').read_text(encoding='utf-8',errors='strict')[offset:]; backend=validate(service,item['role'],raw,window)
                else:
                    cache=service['boundary'] if service['kind']=='hot' and item['role']=='target' else 0; fresh=service['tail'] if cache else len(item['ids']); raw={'usage':{'prompt_tokens':cache+fresh,'cached_tokens':cache,'completion_tokens':32},'text':'FILEDRY','sampled_token_ids':[0]*32}; window=f'Prefill batch, #new-seq: 1, #new-token: {fresh}, #cached-token: {cache}\n'; backend=validate(service,item['role'],raw,window)
                evidence[service['name']+'/'+item['role']]={'raw':raw,'backend_rows':backend,'input_sha256':item['sha256']}
            if execute: os.killpg(process.pid,signal.SIGTERM); process.wait(150)
            process=None
        cells=[]
        for cell in json.loads(INPUTS.read_text())['cells']:
            p,t=cell['boundary'],cell['tail']; a=evidence[f'coldA_p{p}_t{t}/target']; b=evidence[f'coldB_p{p}_t{t}/target']; h=evidence[f'hot_p{p}_t{t}/target']; stable=a['raw']['sampled_token_ids']==b['raw']['sampled_token_ids'] and a['raw']['text']==b['raw']['text']; same=stable and a['raw']['sampled_token_ids']==h['raw']['sampled_token_ids'] and a['raw']['text']==h['raw']['text']; cells.append({'boundary':p,'tail':t,'cold_stable':stable,'hot_equals_cold':same,'classification':'PASS' if same else 'not_met'})
        verdict='PASS' if all(x['classification']=='PASS' for x in cells) else 'not_met'; write_new(RUN/'terminal.json',{'rid':RID,'verdict':verdict,'services':6,'calls':calls,'cells':cells,'message_boundary_flag_services':6,'product_acceptance':execute and verdict=='PASS','r067d_conclusion':'not_met; this D09 package does not establish R067d acceptance','evidence':evidence}); return verdict
    finally:
        if process is not None and execute:
            os.killpg(process.pid,signal.SIGTERM); process.wait(150)

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--filedry',action='store_true'); parser.add_argument('--run',action='store_true'); args=parser.parse_args(); cfg=config()
    if args.filedry == args.run: parser.error('select exactly one of --filedry or --run')
    if args.run:
        admission=HERE/'ROOT_ADMISSION.json'
        if not admission.is_file(): raise RuntimeError('root admission required before GPU execution')
    print(json.dumps({'verdict':run(cfg,args.run),'filedry':args.filedry},sort_keys=True))
if __name__=='__main__': main()
