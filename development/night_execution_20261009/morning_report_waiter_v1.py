#!/usr/bin/env python3
"""CPU-only bounded waiter; preserves the existing observer and production."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
SOURCE=HERE/'morning_report_readonly_v3.py'
INPUT=HERE/'MORNING_REPORT_INPUTS_V3.json'
PINS={'morning_report_readonly_v3.py': 'e7d023b01e9452ca95d509453c9977f989900e1d0532f246a069036881566456', 'MORNING_REPORT_INPUTS_V3.json': '9c371d2c23b4516f0f4a7b3e4c4281a0e686180c57e2fe39ecd3ed0d58b80cc6'}

def checked():
 for name,want in PINS.items():
  p=HERE/name
  if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=want:raise RuntimeError('waiter frozen source/input differs: '+name)
 cfg=json.loads(INPUT.read_text())
 if cfg['not_before']!='2026-10-10T09:00:00+08:00':raise RuntimeError('deadline differs')
 return cfg

def main():
 cfg=checked();deadline=dt.datetime.fromisoformat(cfg['not_before']).timestamp();terminal=Path(cfg['production_root'])/'overnight_observation/terminal.json'
 print(json.dumps({'at':dt.datetime.now().astimezone().isoformat(),'event':'morning_waiter_started','deadline':deadline,'generation_requests':0,'service_mutations':0,'push_executed':False}),flush=True)
 while time.time()<deadline:time.sleep(min(30,deadline-time.time()))
 while not terminal.is_file():
  if time.time()>deadline+180:raise RuntimeError('09 terminal absent for 180 seconds; no synthetic report')
  time.sleep(5)
 checked()
 result=subprocess.run([sys.executable,'-B',str(SOURCE),'--run'],cwd='/data2/FreeToken',timeout=180)
 print(json.dumps({'at':dt.datetime.now().astimezone().isoformat(),'event':'morning_waiter_completed','exit_code':result.returncode}),flush=True)
 raise SystemExit(result.returncode)

if __name__=='__main__':main()
