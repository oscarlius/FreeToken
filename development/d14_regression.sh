set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 TOKENIZERS_PARALLELISM=false /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,os,pathlib,re,subprocess,time
root=pathlib.Path('/data2/FreeToken')
stage=root/'runs/dev_D14'/('regression_e4f3202_'+time.strftime('%Y%m%d_%H%M%S'))
stage.mkdir(exist_ok=False)
tests=['tests/scheduler','tests/kvcache','tests/models/qwen4_exp/test_ple.py']
commits={'e2base':'23f2e2caa3395837c9474735ffc83321f3b9b5a1','e2d14':'e4f32022a5aa4d8734d87d9f6eb15e98c1edde42'}
results=[]
try:
 for name,commit in commits.items():
  wt=root/'wt'/name
  assert subprocess.check_output(['git','-C',str(wt),'rev-parse','HEAD'],text=True).strip()==commit
  assert not subprocess.check_output(['git','-C',str(wt),'status','--porcelain','--untracked-files=no'],text=True).strip()
  program='\n'.join([
   'import pathlib,sys',
   f'wt=pathlib.Path({str(wt)!r})',
   "sys.path[:0]=[str(wt/'python'),str(wt),'/data2/FreeToken/venv/lib/python3.10/site-packages']",
   'import freetoken,torch,pytest',
   "assert freetoken.__file__==str(wt/'python/freetoken/__init__.py')",
   f"result=pytest.main(['-q','-p','no:cacheprovider',*{tests!r}])",
   "assert not torch.cuda.is_initialized(),'CPU regression initialized CUDA'",
   'sys.exit(result)'])
  completed=subprocess.run([str(root/'venv/bin/python'),'-S','-c',program],cwd=wt,env=os.environ.copy(),capture_output=True,timeout=240)
  output=completed.stdout+completed.stderr
  log=stage/(name+'.log');log.write_bytes(output)
  text=output.decode(errors='replace')
  summary=[line for line in text.splitlines() if re.search(r'\d+ (?:failed|passed).* in \d',line)]
  failed=re.findall(r'(?m)^FAILED (\S+)',text)
  results.append({'tree':str(wt),'commit':commit,'returncode':completed.returncode,
    'failed_tests':failed,'summary':summary[-1:] ,'log':str(log),'log_sha256':hashlib.sha256(output).hexdigest()})
 known={'tests/scheduler/test_abort_inflight_prefill.py::test_prefix_commit_sentinel_guard',
        'tests/scheduler/test_abort_inflight_prefill.py::test_post_terminal_overlap_step_is_dropped'}
 if any(set(item['failed_tests'])!=known or item['returncode']!=1 for item in results):
  raise RuntimeError('broad CPU regression differs from the two documented baseline failures')
 report={'schema':'ft_d14_cpu_regression/v1','stage':str(stage),'gpu_started':False,'tests':tests,'results':results,'baseline_failures_unchanged':True}
 reportfile=stage/'report.json';reportfile.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({**report,'report_sha256':hashlib.sha256(reportfile.read_bytes()).hexdigest()},indent=2))
finally:
 for path in reversed([stage,*sorted(stage.rglob('*'))]):
  assert not path.is_symlink()
  path.chmod(path.stat().st_mode & ~0o222)
PY
