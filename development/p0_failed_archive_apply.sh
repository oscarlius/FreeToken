set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,importlib.util,json,os,pathlib,stat,sys,tempfile
from types import SimpleNamespace
root=pathlib.Path('/data2/FreeToken');rounds=pathlib.Path('/data2/_shared/runs/ft_rounds')
stage=root/'runs/dev_D04/failed_archive_83513d87316b'
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as stream:
  for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
assert sha(stage/'scripts/round_close.py')=='db7b278713f52b089a0079022cf73a46285ae1baef3fd7353da8194385f0585b'
assert sha(stage/'development/p0_failed_harness_close.py')=='1959c665e090f3e9dd2fc86e57ae2ed1805eb5083a1f2821d8078424b1797639'
report=json.loads((stage/'report.json').read_text())
assert report['pytest_returncode']==0 and len(report['rounds'])==7 and all(x['closed'] for x in report['rounds'])
assert report['canonical_rounds_mutated'] is False and report['gpu_started'] is False
spec=importlib.util.spec_from_file_location('p0_failed_archive',stage/'development/p0_failed_harness_close.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
plans=[]
for rid in helper.ROUND_IDS:
 directory=rounds/rid
 assert not any((directory/name).exists() for name in ('round.json','round_history','MANIFEST.sha256'))
 plan=helper.preview_one(directory,root/'runs/plan_batches')
 assert plan['arms'] and all(x['service_pid'] is not None and x['pid_terminated_now'] is True for x in plan['arms'])
 if (directory/'batch.sh').exists():
  assert (directory/'batch.sh').is_file() and not (directory/'batch.sh').is_symlink()
  plan['retained_batch']={'path':'batch.sh','sha256':sha(directory/'batch.sh'),'note':'original retained batch; preserved byte for byte'}
 original={}
 for path in [directory,*sorted(directory.rglob('*'))]:
  assert not path.is_symlink() and path.stat().st_uid==os.getuid()
  if path.is_file():original[path.relative_to(directory).as_posix()]=sha(path)
 plans.append((directory,plan,original))
public=root/'scripts/round_close.py'
assert not public.is_symlink() and public.stat().st_uid==os.getuid()
assert sha(public)=='e6fa3bc840c5c6e7c5fa43d4091bb5011932e6f856c2e0111ecdbe590f730c08'
audit=root/'runs/dev_D04/p0_failed_archive_db7b2787';audit.mkdir(exist_ok=False)
(audit/'previous_round_close.py').write_bytes(public.read_bytes())
(audit/'round_close.py').write_bytes((stage/'scripts/round_close.py').read_bytes())
def write_receipt(value):
 target=audit/'canonical_failed_receipt.json';temp=audit/'receipt.tmp'
 with temp.open('x',encoding='utf-8') as stream:
  json.dump(value,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
 os.replace(temp,target)
receipt={'schema':'ft_p0_failed_archive_batch/v1','gpu_started':False,'rounds':[
 {'round_id':plan['round_id'],'state':'planned','original_artifact_sha256':original,'failure':plan['status_failure']}
 for _,plan,original in plans]}
write_receipt(receipt)
fd,temp=tempfile.mkstemp(prefix='.p0-close-',dir=public.parent)
with os.fdopen(fd,'wb') as stream:
 stream.write((stage/'scripts/round_close.py').read_bytes());stream.flush();os.fsync(stream.fileno())
os.chmod(temp,stat.S_IMODE(public.stat().st_mode));os.replace(temp,public)
sys.path.insert(0,str(root/'scripts'))
import round_close as closer,round_json_append as writer
assert sha(public)=='db7b278713f52b089a0079022cf73a46285ae1baef3fd7353da8194385f0585b'
assert sha(root/'scripts/round_json_append.py')=='67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff'
for index,(directory,plan,original) in enumerate(plans):
 assert all(sha(directory/name)==digest for name,digest in original.items())
 assert all(helper.pid_terminated(x['service_pid']) is True for x in plan['arms'])
 receipt['rounds'][index]['state']='closing';write_receipt(receipt)
 if not (directory/'batch.sh').exists():
  with (directory/'batch.sh').open('xb') as stream:stream.write(pathlib.Path(plan['batch_source']['path']).read_bytes())
 doc=helper.metadata(plan)
 if 'retained_batch' in plan:doc['metadata_provenance']['retained_batch']=plan['retained_batch']
 doc.update(epoch=2,executor='Codex mainline owner',title='Archived harness failure; no accepted scientific measurement',
  card={'E2-R001':'T03','E2-R004':'T08','E2-R005':'T09','E2-R012':'T10','E2-R014':'T04','E2-R015':'T04','E2-R016':'T10'}[plan['round_id']],results={},sub_conclusions=[])
 with (directory/'round.json').open('xb') as stream:stream.write(writer.json_bytes(doc))
 manifest=closer.close(directory)
 _,old,_=writer.validate_history(directory/'round.json',directory/'round_history')
 new=writer.run_verdict(old,SimpleNamespace(new='failed_harness',reason=plan['status_failure']['error_excerpt'],
  evidence=[plan['status_failure']['path']],by='Codex mainline owner under CODEX_HANDOFF_20261004 §2 authorization'))
 receipt['rounds'][index].update(state='appending',planned_new_round_json_sha256=hashlib.sha256(writer.json_bytes(new)).hexdigest())
 write_receipt(receipt);writer.commit(directory,new)
 _,actual,versions=writer.validate_history(directory/'round.json',directory/'round_history')
 assert actual['verdict']=='failed_harness' and len(versions)==2
 assert all(sha(directory/name)==digest for name,digest in original.items())
 if plan['round_id']=='E2-R012':assert not (directory/'B1/serve_args.txt').exists()
 receipt['rounds'][index].update(state='committed',round_json_sha256=sha(directory/'round.json'),manifest_sha256=manifest,
  history_count=len(versions),original_bytes_preserved=True)
 write_receipt(receipt)
for p in reversed([audit,*sorted(audit.rglob('*'))]):p.chmod(p.stat().st_mode&~0o222)
print(json.dumps({'rounds':len(plans),'receipt':str(audit/'canonical_failed_receipt.json'),
 'receipt_sha256':sha(audit/'canonical_failed_receipt.json'),'all_committed':all(x['state']=='committed' for x in receipt['rounds'])}))
PY
