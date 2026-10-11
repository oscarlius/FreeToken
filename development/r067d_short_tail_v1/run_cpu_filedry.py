from __future__ import annotations
import argparse, json
from pathlib import Path
from prepare_runner_packet import main as prepare
from r067d_cpu_prep import filedry
p=argparse.ArgumentParser(); p.add_argument('--out', type=Path, required=True); p.add_argument('--run', action='store_true'); a=p.parse_args()
if a.run: raise RuntimeError('GPU/service execution is prohibited by R067d CPU preparation')
prepare()
print(json.dumps(filedry(a.out), sort_keys=True))
