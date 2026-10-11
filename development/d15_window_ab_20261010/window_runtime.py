"""Non-invasive D15 telemetry: one nvidia-smi/ps snapshot per second."""
from __future__ import annotations
import json, subprocess, threading, time
from pathlib import Path

class Sampler:
 def __init__(self,path):self.path=Path(path);self.stop_event=threading.Event();self.thread=threading.Thread(target=self._run,daemon=True)
 def start(self):self.thread.start()
 def close(self):self.stop_event.set();self.thread.join(timeout=3);return not self.thread.is_alive()
 def _run(self):
  while not self.stop_event.is_set():
   now=time.time_ns()
   try:
    gpu=subprocess.check_output(['nvidia-smi','--query-gpu=memory.free,memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True,timeout=3).strip().splitlines()
    ps=subprocess.check_output(['ps','-eLo','pid,tid,stat,comm'],text=True,timeout=3).splitlines()[1:]
    row={'time_ns':now,'gpu':[[part.strip() for part in x.split(',')] for x in gpu],'rthread_count':sum(len(line.split())>=3 and line.split()[2].startswith('R') for line in ps),'uptime_s':float(Path('/proc/uptime').read_text().split()[0]),'uptime_text':subprocess.check_output(['uptime'],text=True,timeout=3).strip()}
   except Exception as e:row={'time_ns':now,'error':repr(e)}
   with self.path.open('a',encoding='utf8') as f:f.write(json.dumps(row,sort_keys=True)+'\n')
   self.stop_event.wait(max(0,1-(time.time_ns()-now)/1e9))
 def interval_min_free(self,start_ns,end_ns):
  rows=[json.loads(x) for x in self.path.read_text().splitlines() if x.strip()]
  vals=[int(g[0]) for r in rows if start_ns<=r.get('time_ns',0)<=end_ns for g in r.get('gpu',[]) if g and str(g[0]).isdigit()]
  return min(vals) if vals else None
