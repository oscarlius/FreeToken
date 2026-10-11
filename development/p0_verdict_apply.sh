set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,importlib.util,json,os,pathlib,stat,tempfile
root=pathlib.Path('/data2/FreeToken')
stage=root/'runs/dev_D04/p0_verdict_9488951e'
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert digest(stage/'development/p0_verdict_batch.py')=='9488951eddeda12d392e4b7b258b78f0f54c0e1bb76e1be08b41b17a54f036ab'
assert digest(stage/'development/p0_verdict_proposal.json')=='65dbcb943410076282404c5dc2ff1da7166f645725e8a54b52113f52ebf7697a'
assert digest(stage/'scripts/round_json_append.py')=='67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff'
report=json.loads((stage/'cpu_report.json').read_text())
assert report['linux_pytest_returncode']==0 and report['private_real_rounds_appended']==14 and report['canonical_rounds_mutated'] is False
public=root/'scripts/round_json_append.py'
assert not public.is_symlink() and public.stat().st_uid==os.getuid()
assert digest(public)=='a4bd8b095bf718076f4d4b7f9ed8d6f5a96263b80e455ae2324d4f3c67601c91'
assert hashlib.md5(public.read_bytes()).hexdigest()=='88178a9a3c83dec204e90e6dcf8c4db9'
audit=root/'runs/dev_D04/p0_public_writer_67c36b2';audit.mkdir(exist_ok=False)
(audit/'previous_round_json_append.py').write_bytes(public.read_bytes())
(audit/'round_json_append.py').write_bytes((stage/'scripts/round_json_append.py').read_bytes())
old_mode=stat.S_IMODE(public.stat().st_mode)
fd,temporary=tempfile.mkstemp(prefix='.p0-writer-',dir=public.parent)
try:
 with os.fdopen(fd,'wb') as stream:
  stream.write((stage/'scripts/round_json_append.py').read_bytes());stream.flush();os.fsync(stream.fileno())
 os.chmod(temporary,old_mode);os.replace(temporary,public)
finally:
 pathlib.Path(temporary).unlink(missing_ok=True)
assert digest(public)=='67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff'
spec=importlib.util.spec_from_file_location('p0_verdict_batch',stage/'development/p0_verdict_batch.py')
batch=importlib.util.module_from_spec(spec);spec.loader.exec_module(batch)
proposal=json.loads((stage/'development/p0_verdict_proposal.json').read_text())
receipt=audit/'canonical_verdict_receipt.json'
result=batch.execute(batch.load_writer(public),pathlib.Path('/data2/_shared/runs/ft_rounds'),proposal,receipt,True)
publication={'schema':'ft_p0_d04_publication/v1','gpu_started':False,'public_writer':str(public),
 'old_sha256':digest(audit/'previous_round_json_append.py'),'new_sha256':digest(public),
 'batch_sha256':digest(stage/'development/p0_verdict_batch.py'),
 'canonical_receipt':str(receipt),'canonical_receipt_sha256':digest(receipt),
 'rounds_appended':len(result['rounds']),'all_committed':all(x['state']=='committed' for x in result['rounds'])}
(audit/'publication.json').write_text(json.dumps(publication,indent=2)+'\n')
for p in reversed([audit,*sorted(audit.rglob('*'))]):p.chmod(p.stat().st_mode&~0o222)
print(json.dumps(publication))
PY
