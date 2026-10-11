"""R058 production-configuration concurrent-memory plan and execution adapter."""
from __future__ import annotations

import hashlib
import importlib.util
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Callable
import urllib.request
import time
import shlex

from r058_concurrent_request import RequestSpec, decode_then_third, simultaneous

HERE = Path(__file__).resolve().parent
PORT_SOURCE = HERE / "ft_batch_port_pair_v1.py"
from ft_batch_port_pair_v1 import dynamic_port, port_receipt
R056 = HERE / 'r056_long_context_prepare.py'
CANDIDATE = '0aa23431e5b800797543bdecbf35a01045131d7d'
SEED_SHA256 = '8fe6b36da6c19eabb4a259535a9835f20e41921d4d7023ec7aaa0063c8b50bf3'
WINDOW = 98304
MEMORY_RATIO = '0.88'
RID = 'E2-R058'
ROOT = Path('/data2/FreeToken')
ROUNDS = Path('/data2/_shared/runs/ft_rounds')
REVIEW_DIR = ROOT / 'runs/dev_R058/reviews/E2-R058-v2'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_r056():
    spec = importlib.util.spec_from_file_location('r058_r056_bound', R056)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def production_plan(payloads=None) -> dict:
    """Bind frozen R056 frontend payloads without shortening or regenerating them."""
    r056 = load_r056()
    pairs = payloads if payloads is not None else r056.payloads()
    values = {spec['name']: (spec, payload) for spec, payload in pairs}
    required = ('cold87_0', 'cold32_0', 'cold32_1', 'cold32_2', 'cold64_0')
    if set(required) - values.keys():
        raise RuntimeError('R058 requires R056 frozen 87K/32K/64K frontend payloads')
    result = {name: RequestSpec(name, values[name][0]['prompt_tokens'], values[name][1])
              for name in required}
    if result['cold87_0'].prompt_tokens != 87100 or result['cold32_0'].prompt_tokens != 32064:
        raise RuntimeError('R058 frozen 87K or 32K prompt token binding differs')
    if result['cold64_0'].prompt_tokens != 65424:
        raise RuntimeError('R058 frozen 64K prompt token binding differs')
    for original, alias in (('cold32_0','decode_left'),('cold32_1','decode_right')):
        payload=json.loads(json.dumps(result[original].payload,ensure_ascii=False)); payload['max_tokens']=2048
        result[alias]=RequestSpec(alias,result[original].prompt_tokens,payload)
    if any(x.prompt_tokens+x.payload['max_tokens']>WINDOW for x in (result['decode_left'],result['decode_right'])): raise RuntimeError('R058 decode budget exceeds window')
    return {'candidate_commit': CANDIDATE, 'window': WINDOW, 'memory_ratio': MEMORY_RATIO,
            'seed_real_sha256': SEED_SHA256, 'd0_enabled': False, 'route_trace_enabled': False,
            'pause_endpoint_enabled': False, 'requests': result,
            'scenarios': (
                ('concurrent_87k_32k', 'cold87_0', 'cold32_0'),
                ('concurrent_32k_32k', 'cold32_1', 'cold32_2'),
                ('decode_then_64k', 'decode_left', 'decode_right', 'cold64_0'),
            )}


def observer_environment(memory_log: Path) -> dict:
    """The launch wrapper receives only external R058 observer variables."""
    return {'R058_MODEL_MEMORY': str(memory_log), 'R058_OBSERVE_REQUESTS': '1'}


def execute(plan: dict, send: Callable[[RequestSpec], object],
            stream: Callable[[RequestSpec, Callable[[], None]], object]) -> dict:
    """Execute all three required concurrency shapes via caller-owned transport."""
    req = plan['requests']
    return {
        'concurrent_87k_32k': simultaneous(req['cold87_0'], req['cold32_0'], send),
        'concurrent_32k_32k': simultaneous(req['cold32_1'], req['cold32_2'], send),
        'decode_then_64k': decode_then_third(req['decode_left'], req['decode_right'], req['cold64_0'], stream, send),
    }


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as out:
        json.dump(value, out, ensure_ascii=False, indent=2, sort_keys=True)
        out.write('\n')


def source_paths() -> tuple[Path, ...]:
    r056 = load_r056()
    return (Path(__file__).resolve(), HERE/'r058_concurrent_request.py', HERE/'r058_concurrent_memory_observer.py', R056, HERE/'d07_g3g4_prepare.py', HERE/'d07_r046a_file_prepare_v1.py', PORT_SOURCE, r056.PROBE, r056.PERF, r056.AGENT, r056.SEED, r056.INPUT_REVIEW)

def source_bindings() -> dict:
    return {str(path): sha(path) for path in source_paths()}


def dry_directory(rounds: Path = ROUNDS) -> Path:
    return rounds / '.dryrun_R058_v2_E2-R058'


def file_dry_run(rounds: Path = ROUNDS) -> dict:
    """Create the real output shape through R056's file-preparation path only."""
    r056, plan, target = load_r056(), production_plan(), dry_directory(rounds)
    if target.exists() or (rounds / RID).exists():
        raise RuntimeError('R058 dry sibling or formal round already exists')
    target.mkdir(mode=0o700)
    d07 = r056.load_d07()
    sources = source_bindings()
    for scenario in plan['scenarios']:
        name, requested = scenario[0], scenario[1:]
        directory, port = target / name, dynamic_port()
        prepared = prepare_r058_service(d07, directory, port, start=False)
        for item in requested:
            spec = plan['requests'][item]
            r056.prepare_request(directory / item, {'name': spec.name, 'prompt_tokens': spec.prompt_tokens,
                                                     'kind': 'cold87' if spec.prompt_tokens == 87100 else 'cold32'},
                                spec.payload, file_dry_run=True)
        write(directory / 'r058_concurrency_plan.json', {'scenario': name, 'port': port,
              'requests': list(requested), 'port_pair': port_receipt(port), 'observer_environment': observer_environment(directory / 'model_memory.jsonl'),
              'production_args': {'memory_ratio': MEMORY_RATIO, 'window': WINDOW}, 'service_started': False})
        for name in ('model_memory.jsonl','stream.raw','events.jsonl','result.json','failure.json','owned_cleanup.json'):
            write(directory/name, {'schema':'ft_r058_dry_probe/v1','not_measurement':True,'path':name})
    write(target/'preflight.json', {'schema':'ft_r058_dry_probe/v1','not_measurement':True})
    write(target/'metadata/pre_d04.json', {'schema':'ft_r058_dry_probe/v1','not_measurement':True})
    write(target/'failed_harness.json', {'schema':'ft_r058_dry_probe/v1','not_measurement':True})
    write(target/'owned_cleanup.json', {'schema':'ft_r058_dry_probe/v1','not_measurement':True})
    receipt = {'schema': 'ft_r058_file_dry/v1', 'rid': RID, 'candidate_commit': CANDIDATE, 'script':str(Path(__file__).resolve()), 'cwd':os.getcwd(), 'uid':os.getuid(),
               'passed': True, 'sources': sources, 'seed_real_sha256': SEED_SHA256,
               'service_started': False, 'requests_sent': False, 'gpu_lock_taken': False,
               'batch_allocated': False, 'formal_rid_directory_created': False,
               'd0_enabled': False, 'route_trace_enabled': False, 'pause_endpoint_enabled': False}
    write(target / 'dry_run_receipt.json', receipt)
    write(target/'manifest.json', {'schema':'ft_r058_dry_manifest/v1','files':{p.relative_to(target).as_posix():sha(p) for p in target.rglob('*') if p.is_file()}})
    (target / 'dry_run_receipt.json').chmod(0o444)
    return receipt

def admission_receipts(rounds: Path = ROUNDS) -> dict:
    dry = dry_directory(rounds) / 'dry_run_receipt.json'
    if dry.is_symlink() or not dry.is_file() or dry.stat().st_mode & 0o222: raise RuntimeError('R058 sealed file-dry receipt missing')
    receipt = json.loads(dry.read_text())
    if receipt.get('schema') != 'ft_r058_file_dry/v1' or receipt.get('script') != str(Path(__file__).resolve()) or receipt.get('cwd') != str(ROOT) or receipt.get('uid') != os.getuid() or receipt.get('candidate_commit') != CANDIDATE or receipt.get('sources') != source_bindings() or receipt.get('passed') is not True or any(receipt.get(k) is not False for k in ('service_started','requests_sent','gpu_lock_taken','batch_allocated','formal_rid_directory_created')): raise RuntimeError('R058 file-dry binding differs')
    review, pin = REVIEW_DIR/'review.json', REVIEW_DIR/'pin.json'
    if any(p.is_symlink() or not p.is_file() or p.stat().st_mode & 0o222 for p in (review,pin)): raise RuntimeError('R058 sealed independent review missing')
    p, r = json.loads(pin.read_text()), json.loads(review.read_text())
    if p.get('schema') != 'ft_r058_review_pin/v1' or p.get('review_sha256') != sha(review) or r.get('schema') != 'ft_r058_startup_review/v1' or r.get('rid') != RID or r.get('verdict') != 'PASS' or r.get('sources') != source_bindings() or r.get('dry_receipt_sha256') != sha(dry): raise RuntimeError('R058 independent review binding differs')
    return {'dry_receipt': str(dry), 'dry_receipt_sha256': sha(dry), 'review': str(review), 'review_sha256': sha(review)}

def child_argv(batch, receipt):
    return [str(ROOT/'venv/bin/python'), str(Path(__file__).resolve()), '--run', '--owned-child', '--batch', str(batch), '--launch-receipt', str(receipt)]

def execute_owned(*, owned_child=False, batch=None, launch_receipt=None):
    """R056 reserve/publish-child boundary; only child may lock or create the RID directory."""
    if sys.platform != 'linux': raise RuntimeError('R058 requires Linux GPU host')
    proof = admission_receipts(); r056, d07 = load_r056(), load_r056().load_d07()
    d07.checked_worktree(ROOT/'wt/e2base1-ordinary-rewind'); d07.require_closed_round('E2-R056','measured')
    if not owned_child:
        if d07.LOCK.exists() or d07.LOCK.is_symlink(): raise RuntimeError('R058 foreign GPU lock; remain queued')
        owned = d07.load_owned_lifecycle(); helper = owned.verified_module(ROOT/'runs/plan_batches/e2_launch.py', d07.ATOMIC_HELPER_SHA, 'r058_atomic')
        batch = helper.next_batch(ROUNDS); receipt = ROOT/'runs/dev_R058'/f'launch_{RID}_batch{batch}.json'; receipt.parent.mkdir(parents=True, exist_ok=True)
        argv = child_argv(batch, receipt)
        reserved = {'schema':'ft_r058_owned_launch/v1','state':'reserved','rid':RID,'batch':batch,'candidate_commit':CANDIDATE,'argv_sha256':d07.argv_sha256(argv),'startup_proof':proof}
        launched = owned.reserve_process(helper,batch,RID,argv,receipt,reserved); birth = owned.process_identity(launched['batch_pid'])
        if birth is None: raise RuntimeError('R058 reserved child birth absent')
        return d07.publish_child_binding(receipt,launched,{k:birth[k] for k in ('pid','start_ticks','execution_id')},lifecycle=owned)
    if batch is None or launch_receipt is None: raise RuntimeError('R058 child requires reserved batch/receipt')
    d07.require_child_receipt(launch_receipt,batch,ROOT/'wt/e2base1-ordinary-rewind',ROUNDS,rid=RID,expected_argv=child_argv(batch,launch_receipt),schema='ft_r058_owned_launch/v1')
    owner = d07.take_d07_gpu_lock(RID,batch); run = None; preserve = False
    try:
        d07.require_gpu_idle(); run = ROUNDS/RID
        if run.exists(): raise RuntimeError('R058 formal round already exists')
        run.mkdir(); plan=production_plan()
        safe={k:v for k,v in plan.items() if k not in ('requests',)}; safe['requests']={k:{'name':v.name,'prompt_tokens':v.prompt_tokens} for k,v in plan['requests'].items()}
        write(run/'preflight.json',{'rid':RID,'batch':batch,'candidate_commit':CANDIDATE,'startup_proof':proof,'plan':safe})
        records=run_scenarios(d07,run,plan)
        write(run/'result.json',{'schema':'ft_r058_raw/v1','rid':RID,'batch':batch,'verdict':'pending_review','records':records,'oom_requires_user_disposition':True})
        write(run/'metadata/pre_d04.json',{'rid':RID,'result_sha256':sha(run/'result.json'),'verdict':'pending_review'})
        return records
    except BaseException as error:
        preserve = bool(getattr(error,'owned_cleanup_failed',False))
        if run is not None: write(run/'failed_harness.json',{'rid':RID,'batch':batch,'error':repr(error),'raw_preserved':True,'user_disposition_required':True})
        raise
    finally:
        if not preserve: d07.release_d07_gpu_lock(owner)
        if run is not None: write(run/'owned_cleanup.json',{'rid':RID,'batch':batch,'lock_released':not preserve,'owned_cleanup_failed':preserve})

def run_scenarios(d07, run: Path, plan: dict):
    """Each concurrency arm owns a fresh service; any error stops the chain."""
    records=[]
    for shape in plan['scenarios']:
        name, ids=shape[0],shape[1:]; directory=run/name; port=dynamic_port(); process=None
        try:
            process=prepare_r058_service(d07,directory,port,start=True); url=f'http://127.0.0.1:{port}/v1/chat/completions'
            def send(spec): return sse_sender(url,directory/spec.name,spec)
            def stream(spec, actual): return sse_sender(url,directory/spec.name,spec,actual)
            values=[plan['requests'][item] for item in ids]
            result=simultaneous(values[0],values[1],send,timeout=1800) if len(values)==2 else decode_then_third(values[0],values[1],values[2],stream,send,timeout=1800)
            write(directory/'result.json',{'scenario':name,'records':result}); records.append({'scenario':name,'result':str(directory/'result.json'),'sha256':sha(directory/'result.json')})
        except BaseException as error:
            write(directory/'failure.json',{'scenario':name,'error':repr(error),'raw_preserved':True,'stop_subsequent_scenarios':True})
            raise
        finally:
            if process is not None:
                lifecycle=d07.load_owned_lifecycle()
                try:
                    lifecycle.stop_owned_process(process)
                    if lifecycle.owned_group_alive(process.pid): raise RuntimeError('R058 owned service group remains')
                except BaseException as cleanup_error:
                    cleanup_error.owned_cleanup_failed = True
                    raise
    return records


def _token_delta(payload: dict) -> bool:
    choices = payload.get('choices') or []
    if not choices: return False
    delta = choices[0].get('delta') or {}
    if delta.get('content') or delta.get('reasoning') or delta.get('reasoning_content'): return True
    return any(((call.get('function') or {}).get('arguments')) for call in delta.get('tool_calls') or [])


def sse_sender(url: str, raw_directory: Path, spec: RequestSpec, actual_token=lambda: None) -> dict:
    """Persist every SSE line; role-only/empty deltas never unlock concurrent 64K."""
    raw_directory.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, data=json.dumps(spec.payload, ensure_ascii=False).encode(),
                                     headers={'Content-Type': 'application/json'}, method='POST')
    lines, token_seen, usage, finish, done = [], False, None, None, False
    stream_path = raw_directory / 'stream.raw'; events_path = raw_directory / 'events.jsonl'
    dispatch_ns=time.monotonic_ns()
    with stream_path.open('x', encoding='utf-8') as raw, events_path.open('x', encoding='utf-8') as events, urllib.request.urlopen(request, timeout=1800) as response:
        for bytes_line in response:
            when=time.time_ns(); line = bytes_line.decode('utf-8', errors='replace').rstrip('\r\n'); lines.append(line); raw.write(line+'\n'); raw.flush()
            events.write(json.dumps({'time_ns':when,'line':line},ensure_ascii=False)+'\n'); events.flush()
            if line == 'data: [DONE]': done=True
            if line.startswith('data: ') and line[6:] != '[DONE]':
                try:
                    event=json.loads(line[6:]); token_seen = token_seen or _token_delta(event)
                    usage=event.get('usage') or usage; choices=event.get('choices') or []; finish=(choices[0].get('finish_reason') if choices else finish)
                except json.JSONDecodeError as error: raise RuntimeError('R058 malformed SSE JSON') from error
                if token_seen: actual_token()
    if not done or not token_seen or not isinstance(usage,dict) or not finish in ('stop','length','tool_calls'): raise RuntimeError('R058 incomplete SSE stream')
    if usage.get('prompt_tokens') != spec.prompt_tokens: raise RuntimeError('R058 API prompt token binding differs')
    return {'dispatch_ns':dispatch_ns,'raw_path': str(stream_path), 'raw_sha256': sha(stream_path), 'events_path':str(events_path),'events_sha256':sha(events_path),
            'actual_token_seen': token_seen, 'usage':usage, 'finish_reason':finish}

def prepare_r058_service(d07, directory: Path, port: int, *, start: bool):
    """One identical FILE_PREP path for dry and live, with only R058 external observer."""
    r056=load_r056(); fileprep=r056.module(r056.FILE_PREP_SOURCE)
    prepared=fileprep.prepare_server_files(d07,directory,ROOT/'wt/e2base1-ordinary-rewind',port,None)
    env=prepared['env']
    for key in list(env):
        if key.startswith(('R055_','R056_','FT_DEV_')): env.pop(key)
    env.update(observer_environment(directory/'model_memory.jsonl'))
    prepared['argv']=['taskset','-c','1,3-47',str(ROOT/'venv/bin/python'),str(HERE/'r058_concurrent_memory_observer.py'),*prepared['argv'][1:]]
    (directory/'SERVE_CMD.txt').write_text('env '+shlex.join(prepared['argv'])+'\n')
    write(directory/'serve_args_diff.json',{'server_diff':{},'shared':{'memory_ratio':'0.88','kv_reserve_tokens':'98304','max_seq_len_override':'98304','d0':False,'route_trace':False,'pause':False},'workload_diff':'decode aliases only increase max_tokens to 2048'})
    return fileprep.start_prepared_server(d07,directory,ROOT/'wt/e2base1-ordinary-rewind',port,prepared) if start else prepared


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(); mode.add_argument('--dry-run', action='store_true'); mode.add_argument('--selftest', action='store_true'); mode.add_argument('--run', action='store_true')
    parser.add_argument('--owned-child', action='store_true'); parser.add_argument('--batch', type=int); parser.add_argument('--launch-receipt', type=Path)
    args = parser.parse_args(argv)
    if args.dry_run: value = file_dry_run()
    elif args.run: value = execute_owned(owned_child=args.owned_child,batch=args.batch,launch_receipt=args.launch_receipt)
    elif args.selftest: value = {'plan': production_plan(), 'cpu_only': True}
    else: value = production_plan()
    print(json.dumps(value, ensure_ascii=False, default=str, indent=2)); return 0


if __name__ == '__main__':
    raise SystemExit(main())
