set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import datetime,hashlib,json,os,pathlib,signal,stat,subprocess,sys,tempfile
from types import ModuleType
root=pathlib.Path('/data2/FreeToken')
dev=root/'runs/dev_D06'
stage=dev/'d06_selfcheck_195aa332'
source=stage/'d06_gpu_selfcheck.py'
source_sha='195aa332d220cf43955a50c25d68276e39ac66a67002e9be0d25497b8df38a10'
def pinned(path,digest):
 data=path.read_bytes()
 if path.is_symlink() or hashlib.sha256(data).hexdigest()!=digest:raise ValueError('frozen artifact changed: '+str(path))
 return data
code=pinned(source,source_sha)
pinned(stage/'cpu_validation.log','5840cf779db65feb0a92c66268ad6aa3127ea1a4da96d7a42c48b8487351e48d')
cpu=json.loads((stage/'cpu_validation.json').read_text())
if any(s['returncode'] for s in cpu['steps']) or cpu['gpu_started'] is not False:raise ValueError('exact-source Linux CPU proof differs')
round_dir=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R020-gate-D06')
pinned(round_dir/'gate_batch48.json','b90f82b9484205ca8bdeba4edb60fb419b43e723d235ee4f6df7afb4532326a0')
review=dev/'t16_r020_raw_review.json'
pinned(review,'67a895cc4e6913e6e5530fa3a4b20ed13e9a1d2fc4bfeabde4713c98375c3dc4')
status=json.loads((round_dir/'status_batch48.json').read_text())
if status.get('state')!='complete_measurements_pending_review' or status.get('batch_pid')!=3817162:raise ValueError('T16 measurements not terminal')
pid=pathlib.Path('/proc/3817162/stat')
if pid.exists() and pid.read_text().rpartition(') ')[2].split()[0]!='Z':raise ValueError('T16 batch is still active')
helper_path=dev/'t16_full_tail_launcher_7e1c05a_289327f/t16_candidate_launch_full_tail.py'
helper_code=pinned(helper_path,'7e1c05a79b856b6a99c3f8d9422afd7013b9ef0215c78e17427d205f78384dcf')
helper=ModuleType('approved_receipt_lifecycle');helper.__file__=str(helper_path)
exec(compile(helper_code,str(helper_path),'exec'),helper.__dict__)
module=ModuleType('approved_d06_selfcheck');module.__file__=str(source)
exec(compile(code,str(source),'exec'),module.__dict__)
proof=module.gate()
output=module.OUT;receipt=dev/'gpu_selfcheck_launch_195aa332.json';log=dev/'gpu_selfcheck_195aa332.log'
if any(p.exists() or p.is_symlink() for p in (output,receipt,log)):raise FileExistsError('existing development evidence retained')
parent=pathlib.Path('/tmp');mode=parent.stat().st_mode
if parent.is_symlink() or not stat.S_ISDIR(mode) or mode&0o022 and not mode&stat.S_ISVTX:raise ValueError('unsafe private source parent')
private=pathlib.Path(tempfile.mkdtemp(prefix='ft-d06-selfcheck-source-',dir=parent))
private_source=private/source.name
with private_source.open('xb') as stream:stream.write(code)
private_source.chmod(0o444);private.chmod(0o555)
if private.stat().st_uid!=os.geteuid() or private_source.stat().st_uid!=os.geteuid():raise ValueError('private source owner differs')
pinned(private_source,source_sha)
argv=[sys.executable,'-u',str(private_source),'--run']
record={'schema':'ft_development_selfcheck_launch/v1','state':'reserved','observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'card':'D06','scope':'G3/G4 development selfcheck; not T05/T16 formal acceptance','candidate_commit':module.CANDIDATE_COMMIT,'parent_commit':module.PARENT_COMMIT,
 'source_stage':str(stage),'runner_sha256':source_sha,'cpu_log_sha256':cpu['log_sha256'],'prerequisite_round':round_dir.name,
 'prerequisite_gate_sha256':'b90f82b9484205ca8bdeba4edb60fb419b43e723d235ee4f6df7afb4532326a0','independent_raw_review_sha256':'67a895cc4e6913e6e5530fa3a4b20ed13e9a1d2fc4bfeabde4713c98375c3dc4',
 'argv':argv,'output':str(output),'log':str(log),'preflight':proof}
def launch_owned(argv,log,receipt,record,helper,root):
 interrupted=False
 def request_stop(_signum,_frame):
  # Record cancellation without interrupting Popen before it returns its handle.
  nonlocal interrupted
  interrupted=True
 previous={sig:signal.signal(sig,request_stop) for sig in (signal.SIGINT,signal.SIGTERM)}
 process=None
 try:
  helper.write_exclusive(receipt,record)
  identity=(receipt.stat().st_dev,receipt.stat().st_ino)
  if interrupted:raise InterruptedError('launcher cancelled before spawn')
  with log.open('xb') as sink:process=subprocess.Popen(argv,cwd=root,stdin=subprocess.DEVNULL,stdout=sink,stderr=subprocess.STDOUT,start_new_session=True,env={**os.environ,'CUDA_VISIBLE_DEVICES':'0'})
  record.update(state='launched',pid=process.pid,pgid=process.pid)
  if interrupted:raise InterruptedError('launcher cancelled after spawn')
  helper.publish_receipt(receipt,identity,record)
  if interrupted:raise InterruptedError('launcher cancelled during receipt publication')
  return record
 except BaseException as exc:
  cleanup_error=None
  for sig in previous:signal.signal(sig,signal.SIG_IGN)
  if process is not None:
   try:helper.stop_owned_process(process)
   except BaseException as error:cleanup_error=repr(error)
  failure={**record,'state':'cleanup_failure' if cleanup_error else 'launch_failed_owned_stopped','error':repr(exc),'cleanup_error':cleanup_error}
  helper.write_exclusive(receipt.with_name(receipt.name+'.failure.json'),failure)
  raise
 finally:
  for sig,handler in previous.items():signal.signal(sig,handler)
print(json.dumps(launch_owned(argv,log,receipt,record,helper,root)),flush=True)
PY
