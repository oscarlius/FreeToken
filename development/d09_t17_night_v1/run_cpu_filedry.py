from pathlib import Path
import os, subprocess, sys
here=Path(__file__).resolve().parent
run=here/'evidence_cpu_filedry_local_v3'/'runs'
if run.exists(): raise RuntimeError('local FILEdry evidence path already exists')
# FILEdry intentionally drives the runner loop with fake process/transport; no GPU, service, or HTTP starts.
env=os.environ.copy(); env['FT_D09_T17_RUN_ROOT']=str(run)
subprocess.run([sys.executable,str(here/'d09_t17_runner.py'),'--filedry'],check=True,env=env)
