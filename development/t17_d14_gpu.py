"""Real T17 donor/hit/fresh-process gate, using frozen T16 resource ownership."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shlex
import signal
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
import t17_d14_runner as helper
import t17_d14_artifacts as artifacts

BASE = HERE / 't16_full_tail_base_runner.py'
if helper.sha256(BASE) != helper.T16_BASE_SHA256:
    raise ValueError('frozen T16 lifecycle changed')
protocol = runpy.run_path(str(BASE), run_name='ft_t17_resource_protocol')
ROOT, ROUNDS = helper.ROOT, helper.ROUNDS
PY = str(ROOT / 'venv/bin/python')
WT = ROOT / 'wt/e2d14'
TRACE = ROUNDS / 'E1-R003-v2/trace_rev.json'
TRACE_SHA = '097b7a039e730d356985f47bc9fd747c86f4658fc6b89f1dec3243c0771b5e24'


def put(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def ids_sha(ids):
    return hashlib.sha256(struct.pack('<%di' % len(ids), *ids)).hexdigest()


def common_prefix(a, b):
    return next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))


def build_inputs():
    """Use the target frontend tokenizer for history prefixes and declared new suffixes."""
    sys.path[:0] = [str(WT / 'python'), str(WT)]
    import freetoken
    from freetoken.server.api_models import ChatCompletionRequest
    from freetoken.server.openai_api import chat_request_to_genspec
    from freetoken.message import TokenizeMsg
    from freetoken.tokenizer.tokenize import TokenizeManager
    from freetoken.utils import load_tokenizer
    if freetoken.__file__ != str(WT / 'python/freetoken/__init__.py') or helper.sha256(TRACE) != TRACE_SHA:
        raise ValueError('real history input/source binding differs')
    tokenizer = load_tokenizer(str(ROOT / 'models/Qwen3.8-Flash-Next-NVFP4-overlay'))
    manager = TokenizeManager(tokenizer)
    builder = runpy.run_path(str(ROOT / 'scripts/agent_trace.py'), run_name='ft_t17_input_builder')
    trace = json.loads(TRACE.read_text())
    thinking = bool(trace.get('meta', {}).get('params', {}).get('thinking', True))
    originals = []
    for index, record in enumerate(trace['rounds']):
        messages = record['messages']
        if builder['messages_digest'](messages) != record['record']['messages_sha']:
            raise ValueError('trace messages hash differs')
        payload = builder['build_payload'](messages, 'Qwen3.8-Flash-Next-NVFP4',
                    trace.get('tools') or builder['tool_specs'](), thinking, 32)
        spec = chat_request_to_genspec(ChatCompletionRequest.model_validate(payload), {})
        msg = TokenizeMsg(uid=index, text=spec.messages, sampling_params=spec.sampling_params,
                          chat_template_kwargs=spec.chat_template_kwargs, tools=spec.template_tools)
        ids = manager.tokenize([msg])[0].input_ids.tolist()
        originals.append((index, ids, record['record']['messages_sha']))
    cases = []
    for item in helper.BOUNDARY_PLAN:
        length = item['length']
        matches = [row for row in originals if len(row[1]) // 64 * 64 == length]
        if length == 8192:
            matches = [next(row for row in originals if len(row[1]) > length)]
        if len(matches) != 1:
            raise ValueError('unambiguous real prefix required: ' + str(length))
        index, original, messages_sha = matches[0]
        donor = original[:length+1]
        # New suffixes are explicitly constructed model inputs, not historical
        # text replay. Their prefix IDs are copied directly from the real trace.
        short = donor + tokenizer.encode(' X' * 1000, add_special_tokens=False)[:64]
        long = donor + tokenizer.encode(' Y' * 5000, add_special_tokens=False)[:4160]
        if len(short) != length+65 or len(long) != length+4161 or common_prefix(short, long)//64*64 != length:
            raise ValueError('query size or cross-query cache-isolation contract differs')
        expected = helper.exact_context(original, length)
        known = {12416: [1469, 17], 18944: [11, 4093], 12736: [198, 248068]}
        if length in known and expected != known[length]:
            raise ValueError('historical context identity differs')
        cases.append({**item, 'trace_index': index, 'messages_sha': messages_sha,
                      'original_ids_sha256': ids_sha(original), 'expected_ngram': expected,
                      'donor': donor, 'short': short, 'long': long,
                      'query_design': 'real trace prefix L+1, then target-tokenizer X/Y suffix; short=65, long=4161 remaining tokens'})
    return {'schema': 'ft_t17_real_inputs/v1', 'trace_sha256': TRACE_SHA,
            'candidate_commit': helper.CANDIDATE, 'cases': cases}


def validate_response(record, ids, cached, max_tokens):
    response = record['response']
    usage = response.get('usage', {})
    if (record['status'] != 200 or response.get('finished') is not True
            or response.get('input_ids_sha256') != ids_sha(ids)
            or usage.get('prompt_tokens') != len(ids) or usage.get('cached_tokens') != cached
            or type(usage.get('completion_tokens')) is not int or usage['completion_tokens'] != max_tokens):
        raise ValueError('terminal response/input/actual cache contract differs')
    return response


def tensor_comparison(left_dir, left, right_dir, right):
    import torch
    results = {}
    for role in helper.STATE_ROLES:
        a = torch.load(left_dir / left['files'][role], map_location='cpu', weights_only=True)
        b = torch.load(right_dir / right['files'][role], map_location='cpu', weights_only=True)
        compatible = a.shape == b.shape and a.dtype == b.dtype
        equal = compatible and artifacts.bit_equal(a, b)
        delta = (a.float()-b.float()).abs() if compatible else None
        results[role] = {'equal': equal, 'shape_left': list(a.shape), 'shape_right': list(b.shape),
                         'dtype_left': str(a.dtype), 'dtype_right': str(b.dtype),
                         'max_abs': float(delta.max()) if delta is not None and delta.numel() else None,
                         'left_sha256': helper.sha256(left_dir / left['files'][role]),
                         'right_sha256': helper.sha256(right_dir / right['files'][role])}
    return results


def ngram(directory, record):
    import torch
    return torch.load(directory / record['files']['slot:ple_ngram_ctx'], map_location='cpu', weights_only=True).flatten().tolist()


class Run(protocol['Runner']):
    def set_status(self, **values):
        super().set_status(rid=self.options.rid, card='T17', **values)

    def lock_take(self):
        self.token = json.dumps({'owner': self.options.rid, 'card': 'T17', 'pid': os.getpid(), 'since': time.strftime('%F %T %Z')})
        descriptor = os.open(protocol['LOCK'], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(self.token)
        self.lock_inode = protocol['LOCK'].stat().st_ino

    def request(self, arm, label, ids, cached, max_tokens):
        record = helper.exact_id_request('http://127.0.0.1:8095', ids, max_tokens,
                                        output_path=arm / (label+'.json'),
                                        observations_path=arm / 'observations.jsonl')
        response = validate_response(record, ids, cached, max_tokens)
        path = arm / 'inputs' / (str(response['uid'])+'.json')
        receipt = json.loads(path.read_text())
        if (receipt.get('uid') != response['uid'] or receipt.get('numel') != len(ids)
                or receipt.get('int32le_sha256') != ids_sha(ids)
                or receipt.get('sampling', {}).get('temperature') != 0
                or receipt.get('sampling', {}).get('max_tokens') != max_tokens
                or receipt.get('sampling', {}).get('ignore_eos') is not True):
            raise ValueError('actual tokenizer-worker input receipt differs')
        return response

    def ready_health(self, arm):
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError('service died during startup')
            try:
                with urllib.request.urlopen('http://127.0.0.1:8095/health', timeout=5) as response:
                    health = json.load(response)
                if health.get('status') == 'error':
                    raise RuntimeError('backend error: ' + repr(health))
                if health.get('status') == 'ok':
                    put(arm/'health.json', health)
                    return
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(5)
        raise TimeoutError('service readiness exceeded 600s')

    def service(self, name, operation, *, schedule=None, health_only=False, max_running_requests=2,
                mamba_host_slots=0):
        if type(max_running_requests) is not int or max_running_requests not in (2, 4):
            raise ValueError('service capacity must be exactly two or four requests')
        if type(mamba_host_slots) is not int or mamba_host_slots < 0:
            raise ValueError('host bank capacity must be a nonnegative integer')
        if schedule is not None:
            if not health_only or schedule.is_symlink() or not schedule.is_file() or schedule.stat().st_mode & 0o222:
                raise ValueError('scheduled reference requires a frozen file and health-only readiness')
        source = self.gate(WT, helper.CANDIDATE)
        extensions = self.compiled_extensions(WT)
        if hasattr(self, 'extensions') and self.extensions != extensions:
            raise ValueError('actually imported compiled extension binding changed between services')
        self.extensions = extensions
        arm = self.directory/name
        arm.mkdir()
        (arm/'inputs').mkdir()
        env = self.environment(WT, arm, True)
        env.update(CUDA_VISIBLE_DEVICES='0', FT_DEV_STATE_DUMP=str(arm/'dump'),
                   FT_T17_INPUT_RECEIPTS=str(arm/'inputs'), FT_T17_OBSERVATIONS=str(arm/'observations.jsonl'))
        if schedule is not None:
            env['FT_DEV_PREFILL_SCHEDULE'] = str(schedule)
        wrapper = self.startup_wrapper()
        for path in (wrapper, HERE/'t17_d14_exact_ids.py'):
            if not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o222:
                raise ValueError('test-only startup source is not frozen')
        argv = ['numactl', '--cpunodebind=0,1', '--interleave=all', PY, '-u', str(wrapper), 'serve',
                '--model-path', str(ROOT/'models/Qwen3.8-Flash-Next-NVFP4-overlay'),
                '--served-model-name', 'Qwen3.8-Flash-Next-NVFP4', '--host', '127.0.0.1', '--port', '8095',
                '--memory-ratio', '0.88', '--moe-cache-auto', '--moe-prefill-hit-d2d', '--ple-backend', 'pinned',
                '--moe-strategy', 'offload', '--quant-backend', 'moe.nvfp4=triton', '--max-running-requests', str(max_running_requests),
                '--cuda-graph-max-bs', str(max_running_requests), '--kv-reserve-tokens', '49152', '--max-seq-len-override', '49152',
                '--max-prefill-length', '4096', '--enable-cache-report', '--enable-special-token-ckpt',
                '--tool-call-parser', 'qwen3_coder', '--reasoning-parser', 'qwen3', '--prefill-layer-major',
                '--mamba-host-slots', str(mamba_host_slots)]
        put(arm/'environment.json', {k:v for k,v in env.items() if k.startswith(('FT_DEV_', 'FT_T17_', 'FT_D3_', 'FT_D16_')) or k in ('PYTHONPATH','CUDA_VISIBLE_DEVICES')})
        put(arm/'compiled_extensions.json', extensions)
        declared_env = {k: v for k, v in env.items()
                        if k.startswith(('FT_DEV_', 'FT_T17_', 'FT_D3_', 'FT_D16_'))
                        or k in ('PYTHONPATH', 'CUDA_VISIBLE_DEVICES', 'PATH', 'LD_LIBRARY_PATH', 'VIRTUAL_ENV')}
        (arm/'SERVE_CMD.txt').write_text(shlex.join(['env', *[k+'='+declared_env[k] for k in sorted(declared_env)], *argv])+'\n')
        (arm/'ENV.txt').write_text(source+'\n'+helper.CANDIDATE+'\n'
                                  +protocol['command'](['date', '--iso-8601=seconds'])+'\n'
                                  +protocol['command'](['nvidia-smi'])+'\n'
                                  +protocol['command'](['numactl', '-H'])+'\n'
                                  +protocol['command'](['free', '-m'])+'\n'
                                  +'\n'.join(protocol['command'](['ps', '-eo', 'pid,pcpu,pmem,comm', '--sort=-pcpu']).splitlines()[:9])+'\n')
        with (arm/'serve.log').open('x') as log:
            self.proc = subprocess.Popen(argv, env=env, cwd=WT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            self.set_status(state='loading', arm=name, service_pid=self.proc.pid)
            try:
                if health_only:
                    self.ready_health(arm)
                else:
                    self.ready(arm)
                args = self.parser(str(arm/'serve.log'))
                if args['_unique_suffix'] != repr('.pid='+str(self.proc.pid)) or args.get('mamba_host_slots') != str(mamba_host_slots):
                    raise ValueError('parsed owned PID or requested host bank configuration differs')
                (arm/'serve_args.txt').write_text(json.dumps(args,indent=2)+'\n')
                if hasattr(self, 'first_args'):
                    protocol['strict_args'](self.first_args, args, {})
                else:
                    self.first_args = args
                self.set_status(state='probing', arm=name, service_pid=self.proc.pid)
                return operation(arm)
            finally:
                self.stop()

    def startup_wrapper(self):
        return HERE/'t17_d14_startup.py'

    def execute(self):
        prerequisite = helper.t16_prerequisite()
        if self.directory.exists():
            raise FileExistsError('assigned T17 evidence already exists')
        inputs = json.loads((HERE/'real_inputs.json').read_text())
        if inputs.get('trace_sha256') != TRACE_SHA or inputs.get('candidate_commit') != helper.CANDIDATE or len(inputs.get('cases', [])) != 4:
            raise ValueError('frozen real input cases differ')
        helper.verify_t16_lifecycle(BASE, HERE/helper.T16_LAUNCH_PROTOCOL)
        self.gate(WT, helper.CANDIDATE)
        if not self.options.run:
            print(json.dumps({'preflight': 'PASS', 'prerequisite': prerequisite})); return
        self.lock_take()
        owned = False
        try:
            self.directory.mkdir(); owned = True
            put(self.directory/'prerequisite.json', prerequisite)
            put(self.directory/'real_inputs.json', inputs)
            for name in ('t17_d14_gpu.py','t17_d14_runner.py','t17_d14_startup.py','t17_d14_exact_ids.py','t17_d14_observe.py','t17_d14_artifacts.py','t16_full_tail_base_runner.py',helper.T16_LAUNCH_PROTOCOL):
                with (self.directory/name).open('xb') as stream:
                    stream.write((HERE/name).read_bytes())
            result = {'schema': 'ft_t17_real_gate/v1', 'rid': self.options.rid, 'batch': self.options.batch,
                      'gpu_started': True, 'candidate_commit': helper.CANDIDATE, 'mamba_host_slots': 0,
                      'cases': {}, 'default_path_gate': helper.T16_RID, 'acceptance': 'pending_review'}
            for case in inputs['cases']:
                length = case['length']; name = case['name']
                def warm(arm):
                    donor = self.request(arm, 'donor', case['donor'], 0, 2)
                    dumped = helper.load_dump_record(arm/'dump', kind='donate', length=length, uid=str(donor['uid']))
                    if ngram(arm/'dump', dumped) != case['expected_ngram']:
                        raise ValueError('donor ngram identity differs')
                    samples = {}
                    for variant in ('short','long'):
                        query = self.request(arm, variant, case[variant], length, 128)
                        resume = helper.load_dump_record(arm/'dump', kind='resume-device', length=length, uid=str(query['uid']))
                        resumed_ctx = artifacts.load_tensor(arm/'dump'/resume['files']['slot:ple_ngram_ctx'])[:,1].flatten().tolist()
                        if resumed_ctx != case['expected_ngram']:
                            raise ValueError('actual device restoration differs from donor state')
                        samples[variant] = {'response': query, 'resume': resume, 'donor_uid': donor['uid']}
                    return samples
                warm_name = name+'_warm'
                samples = self.service(warm_name, warm)
                for variant in ('short','long'):
                    cold_name = name+'_'+variant+'_cold'
                    cold = self.service(cold_name, lambda arm: self.request(arm, 'query', case[variant], 0, 128))
                    warm_arm, cold_arm = self.directory/warm_name, self.directory/cold_name
                    boundary = (len(case[variant])-1)//64*64
                    warm_dump = helper.load_dump_record(warm_arm/'dump',kind='donate',length=boundary,uid=str(samples[variant]['response']['uid']))
                    cold_dump = helper.load_dump_record(cold_arm/'dump',kind='donate',length=boundary,uid=str(cold['uid']))
                    roles = tensor_comparison(warm_arm/'dump',warm_dump,cold_arm/'dump',cold_dump)
                    same_text = samples[variant]['response']['text']==cold['text']
                    raw_case = {'name': name, 'length': length, 'trace_index': case['trace_index'],
                                'context': case['expected_ngram']}
                    raw = artifacts.validate_case(
                        raw_case, cold_arm, warm_arm,
                        tail=65 if variant == 'short' else 4161,
                        cold_request='query', hit_request=variant,
                        state_root=warm_arm/'dump')
                    put(warm_arm/(variant+'_restore_comparison.json'), raw['state_roles'])
                    row = {'length':length,'variant':variant,'actual_cached_tokens':raw['actual_cached_tokens'],'prompt_ids_sha256':raw['prompt_ids_sha256'],
                           'donor_ngram':raw['state_roles']['slot:ple_ngram_ctx']['observed_donor'],
                           'resume_ngram':raw['state_roles']['slot:ple_ngram_ctx']['observed_resume'],
                           'restore_roles':raw['state_roles'],'recompute_roles':roles,'full_text_equal':same_text,
                           'warm_response':str(warm_arm/(variant+'.json')),'cold_response':str(cold_arm/'query.json'),
                           'sampled_token_ids': {'cold': raw['cold_token_ids'], 'hit': raw['hit_token_ids']},
                           'raw_validator': raw}
                    put(self.directory/(name+'_'+variant+'_comparison.json'),row)
                    result['cases'][name+'_'+variant] = row
                    if not same_text or not raw['passed'] or not all(v['equal'] for v in roles.values()):
                        raise ValueError('hit versus whole recomputation differs; original output/state retained, gate not accepted')
            result['acceptance']='measurements_pass_pending_independent_review'
            put(self.directory/('gate_batch'+str(self.options.batch)+'.json'),result)
            self.set_status(state='complete_measurements_pending_review')
        except BaseException as exc:
            if owned:
                self.set_status(state='failed',error=repr(exc))
            raise
        finally:
            try:
                self.stop()
            finally:
                if self.proc is None:
                    self.lock_release()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-inputs',type=Path)
    parser.add_argument('--rid');parser.add_argument('--batch',type=int);parser.add_argument('--run',action='store_true')
    options=parser.parse_args()
    if options.build_inputs:
        put(options.build_inputs,build_inputs());return
    if sys.platform!='linux' or not re.fullmatch(r'E2-R\d{3}-gate-T17',options.rid or '') or type(options.batch) is not int or options.batch<1:
        parser.error('Linux and exact root-assigned T17 identity required')
    options.gate='T17'
    run=Run(options)
    for signum in (signal.SIGINT,signal.SIGTERM):
        signal.signal(signum,lambda signum,frame: (_ for _ in ()).throw(InterruptedError('owned batch signal '+str(signum))))
    run.execute()


if __name__=='__main__':
    main()
