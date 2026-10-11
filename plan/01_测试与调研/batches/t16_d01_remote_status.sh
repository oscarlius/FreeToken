set -eu
echo 'BATCH21-SYNTAX:'
bash -n /data2/FreeToken/runs/plan_batches/batch21_E2-pre-gate-D01_resume.sh && echo SYNTAX-OK
echo 'BATCH21:'
ps -o pid,pgid,lstart,args -p 843692 || true
tail -30 /data2/_shared/runs/ft_rounds/batch21.log 2>/dev/null || true
echo 'BATCH22:'
ps -o pid,pgid,lstart,args -p 866506 || true
tail -30 /data2/_shared/runs/ft_rounds/batch22.log 2>/dev/null || true
echo 'ROUND:'
find /data2/_shared/runs/ft_rounds/E2-pre-gate-D01 -maxdepth 2 -type f -printf '%P %s\n' | sort
echo 'PROCESSES:'
ps -eo pid,pgid,lstart,args | grep -E '[f]t serve|[b]atch20_E2-pre-gate-D01|[b]atch21_E2-pre-gate-D01' || true
echo 'PORT:'
ss -ltnp | grep ':8095 ' || true
echo 'LOCK:'
test -e /data2/_shared/gpu.lock && cat /data2/_shared/gpu.lock || echo absent
echo 'GPU:'
nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits
echo 'BATCH20-TAIL:'
tail -40 /data2/_shared/runs/ft_rounds/batch20.log
echo 'PARENT-VERIFY:'
sha256sum /data2/_shared/runs/ft_rounds/E2-pre-gate-D01/PARENT/{SERVE_CMD.txt,serve.log,det.json,tax.json,prefill_seq.txt,d0_prefill.jsonl}
/data2/FreeToken/venv/bin/python - <<'PY'
import json
root = '/data2/_shared/runs/ft_rounds/E2-pre-gate-D01/PARENT'
print('det_keys', sorted(json.load(open(root + '/det.json'))))
print('det_record', json.load(open(root + '/det.json'))['record'])
print('tax_type', type(json.load(open(root + '/tax.json'))).__name__)
print('prefill_lines', sum(1 for _ in open(root + '/prefill_seq.txt')))
print('d0_lines', sum(1 for _ in open(root + '/d0_prefill.jsonl')))
PY
grep -m1 -A1 'Parsed arguments' /data2/_shared/runs/ft_rounds/E2-pre-gate-D01/PARENT/serve.log
echo 'ARGS-DIFF-TOOL:'
sed -n '1,220p' /data2/FreeToken/scripts/serve_args_diff.py
