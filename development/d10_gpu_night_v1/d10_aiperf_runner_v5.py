"""Frozen four-profile/eight-request AIPerf plan for D10 v4."""
from __future__ import annotations
import hashlib, json
from pathlib import Path

HERE=Path(__file__).resolve().parent
RID='E2-D10-T16-night-20261010'; CANDIDATE='22ff3a389eae3724cdca9a45f2e19577082a2032'
INPUT=HERE/'inputs_ignore_eos256.jsonl'; ORIGINAL=HERE/'inputs_r045.jsonl'
INPUT_SHA='a1fcedff4ec4d70ca8ecdebf2e704fc30475600ff668177f3715f11d569e64a5'; ORIGINAL_SHA='9ac31867b8d9303b2b00109828e3e66ecd66699ce6d109dc7b11e994c8ce1cc3'
AIPERF='/data2/FreeToken/evaluation/toolchain/venv-aiperf/bin/aiperf'
def argv(endpoint, output, input_file=INPUT):
 return [AIPERF,'profile','--model','Qwen3.8-Flash-Next-NVFP4','--endpoint-type','chat','--streaming','--url',endpoint,'--input-file',str(input_file),'--custom-dataset-type','single_turn','--dataset-sampling-strategy','sequential','--request-count','2','--concurrency','2','--wait-for-model-timeout','0','--request-timeout-seconds','300','--no-server-metrics','--no-gpu-telemetry','--ui','none','--tokenizer','builtin','--use-server-token-count','--use-legacy-max-tokens','--export-level','raw','--output-artifact-dir',output]
def filedry():
 if hashlib.sha256(INPUT.read_bytes()).hexdigest()!=INPUT_SHA or hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()!=ORIGINAL_SHA: raise RuntimeError('frozen inputs differ')
 return {'schema':'ft_d10_aiperf_filedry/v2','profiles':4,'budget':{'services_max':1,'aiperf_calls':8,'generation_calls':8},'commands':[argv('http://127.0.0.1:<api>',f'<run>/profile{i}',ORIGINAL if i<2 else INPUT) for i in range(4)],'http_started':False,'gpu_started':False}
def require_admission(path):
 if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o222: raise RuntimeError('sealed root admission required')
 doc=json.loads(path.read_text());
 if doc.get('admit') is not True or doc.get('calls_max')!=8 or doc.get('services_max')!=1: raise RuntimeError('admission budget differs')
 # The parent independently validates each terminal/manifest hash; a PASS verdict is never required.
 if not isinstance(doc.get('d09_completed_terminals'),list) or not doc['d09_completed_terminals']: raise RuntimeError('safe D09 terminal binding missing')
 return doc
