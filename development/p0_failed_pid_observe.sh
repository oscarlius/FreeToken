set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import importlib.util,json,pathlib,re
stage=pathlib.Path('/data2/FreeToken/runs/dev_D04/failed_archive_83513d87316b')
spec=importlib.util.spec_from_file_location('helper',stage/'development/p0_failed_harness_close.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
rounds=pathlib.Path('/data2/_shared/runs/ft_rounds')
rows=[]
for rid in helper.ROUND_IDS:
 plan=helper.preview_one(rounds/rid,pathlib.Path('/data2/FreeToken/runs/plan_batches'))
 for arm in plan['arms']:
  proc=pathlib.Path('/proc')/str(arm['service_pid'])
  log=(rounds/rid/arm['arm']/'serve.log').read_text(errors='replace')
  parsed=re.findall(r"_unique_suffix='\.pid=(\d+)'",log)
  rows.append({'rid':rid,'arm':arm['arm'],'helper_pid':arm['service_pid'],
   'pid_terminated_now':arm['pid_terminated_now'],'proc_exists':proc.exists(),
   'proc_state':(proc/'stat').read_text().rpartition(') ')[2].split()[0] if (proc/'stat').exists() else None,
   'logged_parsed_pids':sorted(set(map(int,parsed)))})
print(json.dumps(rows))
PY
