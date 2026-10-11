"""D14-schedule declaration adapter over the pinned T16 lifecycle."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, re, signal, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHARED = HERE / 't16_candidate_runner_full_tail.py'
SHARED_SHA = '0451e41128b4d1e0c73f892b375b9fbe70b30a9fbac46bc022500bd3c1b6d8b8'
BASE_SHA = '379948776d42d5429304afb11dafb0d316e641638caf7cad15fb5b5e6be7340f'
CANDIDATE = 'a9dca443cd07e1f60d1533e0a678935a09d21636'
PARENT = 'e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7'
PROBE_SHA = 'b97190f589f7383972f0799ec0855bfd76e0f0b928e13ebc3696644d970de88b'
PROBE_MD5 = 'a027c1aa8a0b85d6bb94ce9860d7fa66'
D18 = HERE / 'd18_independent_cpu_receipt_20261005.json'
D18_LOG = HERE / 'd18_independent_cpu_receipt_20261005.log'
D18_TEST = HERE / 'tests/test_d18_client_params.py'
BENCH = Path('/data2/_shared/benchmark_client.py')

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
if sha(SHARED) != SHARED_SHA: raise RuntimeError('pinned shared T16 adapter source differs')
spec = importlib.util.spec_from_file_location('t16_schedule_shared', SHARED)
shared = importlib.util.module_from_spec(spec); sys.modules[spec.name] = shared; spec.loader.exec_module(shared)
if shared.BASE_SHA256 != BASE_SHA: raise RuntimeError('pinned base lifecycle differs')
CASE = {'card':'D14','parent_wt':'e2d14-schedule','new_wt':'e2d14-ordinary-rewind','parent_commit':PARENT,'new_commit':CANDIDATE,'ordinary_prefill':True}

def d18_binding():
    if D18.is_symlink() or not D18.is_file(): raise ValueError('D18 receipt must be regular')
    value = json.loads(D18.read_bytes())
    for key, expected in {'schema':'ft_d18_independent_cpu/v1','card':'D18','returncode':0,'gpu_started':False,'requests_sent':False}.items():
        if value.get(key) != expected: raise ValueError('D18 receipt status differs')
    if type(value['gpu_started']) is not bool or type(value['requests_sent']) is not bool: raise ValueError('D18 boolean status differs')
    sources, live = value.get('source_files'), value.get('live_source_files')
    if not isinstance(sources,dict) or sources.get('scripts/probe_ft_cold32k.py') != PROBE_SHA: raise ValueError('D18 probe source differs')
    observed = live.get('/data2/FreeToken/scripts/probe_ft_cold32k.py') if isinstance(live,dict) else None
    if not isinstance(observed,dict) or observed.get('sha256') != PROBE_SHA or observed.get('regular') is not True: raise ValueError('D18 live probe differs')
    if not isinstance(value.get('log_sha256'),str) or not re.fullmatch(r'[0-9a-f]{64}', value['log_sha256']): raise ValueError('D18 log binding missing')
    if not D18_LOG.is_file() or D18_LOG.is_symlink() or sha(D18_LOG) != value['log_sha256']: raise ValueError('D18 staged log differs')
    if value.get('test_summary') != '5 passed in 0.03s': raise ValueError('D18 test summary differs')
    for name, path in (('../_shared/benchmark_client.py', BENCH), ('tests/test_d18_client_params.py', D18_TEST)):
        if path.is_symlink() or not path.is_file() or sources.get(name) != sha(path): raise ValueError('D18 source differs: '+name)
    probe = shared.base['SCR'] / 'probe_ft_cold32k.py'
    if probe.is_symlink() or not probe.is_file() or sha(probe) != PROBE_SHA or hashlib.md5(probe.read_bytes()).hexdigest() != PROBE_MD5: raise ValueError('live probe differs')
    return {'receipt_sha256':sha(D18),'log_sha256':sha(D18_LOG),'probe_sha256':PROBE_SHA,'probe_md5':PROBE_MD5,'benchmark_sha256':sha(BENCH),'test_sha256':sha(D18_TEST)}

class Runner(shared.CandidateRunner):
    def __init__(self, options):
        shared.CASES['D14-schedule'] = CASE
        super().__init__(options); self.d18 = d18_binding()
    def execute(self):
        shared.__dict__['__file__'] = str(Path(__file__).resolve())
        tools = shared.base['TOOL_MD5']; old = tools['probe_ft_cold32k.py']; tools['probe_ft_cold32k.py'] = PROBE_MD5
        try: return super().execute()
        finally: tools['probe_ft_cold32k.py'] = old
    def run_arm(self, *args, **kwargs):
        for target, source in ((self.directory/'d18_independent_cpu_receipt.json',D18),(self.directory/'d18_independent_cpu_receipt.log',D18_LOG),(self.directory/'d18_probe_ft_cold32k.py',shared.base['SCR']/'probe_ft_cold32k.py')):
            raw=source.read_bytes()
            if target.exists():
                if target.is_symlink() or target.read_bytes()!=raw: raise ValueError('archived D18 evidence differs')
            else:
                with target.open('xb') as stream: stream.write(raw)
        binding=self.directory/'d18_binding.json'; raw=(json.dumps(self.d18,sort_keys=True,indent=2)+'\n').encode()
        if binding.exists():
            if binding.is_symlink() or binding.read_bytes()!=raw: raise ValueError('archived D18 binding differs')
        else:
            with binding.open('xb') as stream: stream.write(raw)
        return super().run_arm(*args, **kwargs)

def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--case',choices=('D14-schedule',),required=True); parser.add_argument('--rid',required=True); parser.add_argument('--batch',type=int,required=True); parser.add_argument('--candidate-commit',required=True); parser.add_argument('--run',action='store_true')
    options=parser.parse_args()
    if not re.fullmatch(r'E2-R[0-9]{3}-gate-D14',options.rid): parser.error('new D14 RID required')
    if sys.platform!='linux': parser.error('Linux test host required')
    Runner(options).execute()
if __name__=='__main__':
    for signum in (signal.SIGINT,signal.SIGTERM): signal.signal(signum,lambda *_: (_ for _ in ()).throw(InterruptedError('owned signal')))
    main()
