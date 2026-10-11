"""D10 R045-compatible AIPerf plan; execution is root-admission only."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

HERE=Path(__file__).resolve().parent
RID='E2-D10-T16-night-20261010'; CANDIDATE='22ff3a389eae3724cdca9a45f2e19577082a2032'
INPUT=HERE/'inputs_ignore_eos256.jsonl'; INPUT_SHA='a1fcedff4ec4d70ca8ecdebf2e704fc30475600ff668177f3715f11d569e64a5'
AIPERF='/data2/FreeToken/evaluation/toolchain/venv-aiperf/bin/aiperf'

def frozen_r045():
    command=json.loads((HERE/'r045_wave1_command.json').read_text())
    def value(flag): return command[command.index(flag)+1]
    if value('--request-count')!='2' or value('--concurrency')!='2': raise ValueError('R045 actual frozen request/concurrency differs')
    return {'record_sha256':'5f04c7d0547e66f907db625194b0ea6bb55cc765663f114282124928e0cdd7e4','request_count':2,'concurrency':2,'profiles':2,'calls':4}

def argv(endpoint, output):
    return [AIPERF,'profile','--model','Qwen3.8-Flash-Next-NVFP4','--endpoint-type','chat','--streaming','--url',endpoint,
            '--input-file',str(INPUT),'--custom-dataset-type','single_turn','--dataset-sampling-strategy','sequential',
            '--request-count','2','--concurrency','2','--wait-for-model-timeout','0','--request-timeout-seconds','300',
            '--no-server-metrics','--no-gpu-telemetry','--ui','none','--tokenizer','builtin','--use-server-token-count',
            '--use-legacy-max-tokens','--export-level','raw','--output-artifact-dir',output]

def filedry():
    if hashlib.sha256(INPUT.read_bytes()).hexdigest()!=INPUT_SHA: raise ValueError('frozen ignore_eos256 input hash differs')
    r=frozen_r045(); plan={'schema':'ft_d10_aiperf_filedry/v1','rid':RID,'candidate':CANDIDATE,'input_sha256':INPUT_SHA,
      'r045':r,'budget':{'services_max':1,'calls_max':8,'aiperf_calls':4},'command':argv('http://127.0.0.1:<root-owned-port>','<root-owned-run>/aiperf'),
      'service_started':False,'requests_sent':False,'gpu_started':False,'http_started':False,'independent_review_required':True}
    return plan

def main():
    p=argparse.ArgumentParser();p.add_argument('--filedry',action='store_true');p.add_argument('--run',action='store_true');a=p.parse_args()
    if a.filedry and not a.run: print(json.dumps(filedry(),sort_keys=True));return
    if a.run: raise SystemExit('root admission and owned service receipt required; direct execution denied')
    p.error('select --filedry')
if __name__=='__main__':main()
