set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import json,os,pathlib,signal,time
pid,parent=3624218,3624217
proc=pathlib.Path('/proc')/str(pid)
if not proc.exists():
 print(json.dumps({'pid':pid,'state':'already_absent'}));raise SystemExit
raw=proc.joinpath('stat').read_text().rpartition(') ')[2].split()
argv=[part.decode() for part in proc.joinpath('cmdline').read_bytes().split(b'\0') if part]
env=dict(part.split(b'=',1) for part in proc.joinpath('environ').read_bytes().split(b'\0') if b'=' in part)
assert argv==['/data2/FreeToken/venv/bin/python','-S','-'],argv
assert int(raw[1])==parent and int(raw[2])==parent and int(raw[3])==parent
assert pathlib.Path('/proc',str(parent),'cmdline').read_bytes().split(b'\0')[:2]==[b'bash',b'-s']
assert env[b'CUDA_VISIBLE_DEVICES']==b'' and env[b'OMP_NUM_THREADS']==b'4' and env[b'PYTHONDONTWRITEBYTECODE']==b'1'
identity={'pid':pid,'ppid':parent,'pgid':int(raw[2]),'sid':int(raw[3]),'starttime':int(raw[19]),'argv':argv}
record=pathlib.Path('/data2/FreeToken/runs/dev_D03/f506_cpu_input_interrupted_3624218.json')
with record.open('x') as stream:stream.write(json.dumps({'identity':identity,'action':'SIGINT owned CPU input producer','gpu_started':False},indent=2)+'\n')
fresh=proc.joinpath('stat').read_text().rpartition(') ')[2].split()
assert fresh[19]==raw[19] and fresh[1:4]==raw[1:4]
os.kill(pid,signal.SIGINT)
for _ in range(50):
 if not proc.exists() or proc.joinpath('stat').read_text().rpartition(') ')[2].startswith('Z'):break
 time.sleep(.1)
else:raise RuntimeError('owned CPU producer did not exit after SIGINT')
print(json.dumps({'identity':identity,'state':'interrupted_owned_cpu_only','record':str(record)}))
PY
