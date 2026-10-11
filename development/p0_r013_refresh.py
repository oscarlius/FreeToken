"""Refresh the sealed R013 CPU classification without uploading files or using CUDA."""
import json
from pathlib import Path
import shlex
import subprocess

here = Path(__file__).resolve().parent
source = (here / "p0_r013_fork_classify.py").read_bytes()
program = r'''
import hashlib,json,os,pathlib,sys
sys.path.append('/data2/FreeToken/venv/lib/python3.10/site-packages')
source=sys.stdin.buffer.read()
module={'__name__':'ft_r013_readonly_refresh'}
exec(compile(source,'<frozen_r013_cpu_classification>','exec'),module)
report=module['classify'](pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R013'))
import torch
assert not torch.cuda.is_initialized()
summary={key:report[key] for key in ('schema','round_id','provenance','parent_token_binding','protocol','counts','limitations')}
summary.update(gpu_started=False,server_files_mutated=False,analysis_source_sha256=hashlib.sha256(source).hexdigest(),
               token_zero=[row for row in report['forks'] if row['fork_idx']==0])
print(json.dumps(summary,ensure_ascii=False,allow_nan=False))
'''
command = "CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 /data2/FreeToken/venv/bin/python -S -c " + shlex.quote(program)
result = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "9", command],
                        input=source, capture_output=True, timeout=180)
if result.returncode:
    print(result.stderr.decode(errors="replace"))
    raise SystemExit(result.returncode)
summary = json.loads(result.stdout.decode().splitlines()[-1])
(here / "p0_r013_refresh_receipt.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2))
