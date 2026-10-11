"""D10 R045-compatible AIPerf plan; execution is root-admission only."""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, time
from pathlib import Path

HERE=Path(__file__).resolve().parent
RID='E2-D10-T16-night-20261010'; CANDIDATE='22ff3a389eae3724cdca9a45f2e19577082a2032'
INPUT=HERE/'inputs_ignore_eos256.jsonl'; INPUT_SHA='a1fcedff4ec4d70ca8ecdebf2e704fc30475600ff668177f3715f11d569e64a5'
ORIGINAL=HERE/'inputs_r045.jsonl'; ORIGINAL_SHA='9ac31867b8d9303b2b00109828e3e66ecd66699ce6d109dc7b11e994c8ce1cc3'
AIPERF='/data2/FreeToken/evaluation/toolchain/venv-aiperf/bin/aiperf'

def frozen_r045():
    command=json.loads((HERE/'r045_wave1_command.json').read_text())
    def value(flag): return command[command.index(flag)+1]
    if value('--request-count')!='2' or value('--concurrency')!='2': raise ValueError('R045 actual frozen request/concurrency differs')
    return {'record_sha256':'5f04c7d0547e66f907db625194b0ea6bb55cc765663f114282124928e0cdd7e4','request_count':2,'concurrency':2,'profiles':2,'calls':4}

def argv(endpoint, output, input_file=INPUT):
    return [AIPERF,'profile','--model','Qwen3.8-Flash-Next-NVFP4','--endpoint-type','chat','--streaming','--url',endpoint,
            '--input-file',str(input_file),'--custom-dataset-type','single_turn','--dataset-sampling-strategy','sequential',
            '--request-count','2','--concurrency','2','--wait-for-model-timeout','0','--request-timeout-seconds','300',
            '--no-server-metrics','--no-gpu-telemetry','--ui','none','--tokenizer','builtin','--use-server-token-count',
            '--use-legacy-max-tokens','--export-level','raw','--output-artifact-dir',output]

def filedry():
    if hashlib.sha256(INPUT.read_bytes()).hexdigest()!=INPUT_SHA or hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()!=ORIGINAL_SHA: raise ValueError('frozen D10 input hash differs')
    r=frozen_r045(); plan={'schema':'ft_d10_aiperf_filedry/v1','rid':RID,'candidate':CANDIDATE,'input_sha256':INPUT_SHA,
      'r045':r,'budget':{'services_max':1,'calls_max':8,'aiperf_calls':8},'commands':[argv('http://127.0.0.1:<root-owned-port>',f'<root-owned-run>/aiperf/p{i}', ORIGINAL if i<2 else INPUT) for i in range(4)],
      'service_started':False,'requests_sent':False,'gpu_started':False,'http_started':False,'independent_review_required':True}
    return plan

def require_admission(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o222: raise RuntimeError('sealed root admission required')
    doc=json.loads(path.read_text()); expected={'admit':True,'rid':RID,'candidate':CANDIDATE,'t16_verdict':'kept','d09_gpu_terminal':'kept','calls_max':8,'services_max':1,'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    if any(doc.get(k)!=v for k,v in expected.items()): raise RuntimeError('root admission binding differs')
    return doc

def run(admission, endpoint, output):
    require_admission(admission); plan=filedry(); output.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ,CUDA_VISIBLE_DEVICES='',NO_PROXY='127.0.0.1,localhost',no_proxy='127.0.0.1,localhost')
    commands=[argv(endpoint, str(output/f'profile{i}'), ORIGINAL if i<2 else INPUT) for i in range(4)]
    for i,command in enumerate(commands):
        (output/f'profile{i}.command.json').write_text(json.dumps(command)+'\n')
        result=subprocess.run(command,env=env,timeout=1800)
        (output/f'profile{i}.exit.json').write_text(json.dumps({'exit_code':result.returncode,'at':time.time()})+'\n')
        if result.returncode: raise RuntimeError(f'AIPerf profile {i} failed')
    (output/'terminal.json').write_text(json.dumps({'calls':8,'profiles':4,'classification':'exports_pending_review','product_acceptance':False})+'\n')

def main():
    p=argparse.ArgumentParser();p.add_argument('--filedry',action='store_true');p.add_argument('--run',action='store_true');p.add_argument('--admission',type=Path);p.add_argument('--endpoint');p.add_argument('--output',type=Path);a=p.parse_args()
    if a.filedry and not a.run: print(json.dumps(filedry(),sort_keys=True));return
    if a.run:
        if not(a.admission and a.endpoint and a.output):p.error('--run requires sealed admission, endpoint and output')
        run(a.admission,a.endpoint,a.output);return
    p.error('select --filedry')
if __name__=='__main__':main()
