set -eu
grep -nE 'ready|Ready|ERROR|Traceback|ServerArgs|503|Scheduler|warmup|Warmup|Loading|load|D0|exiting' /data2/FreeToken/runs/dev_D01/cut_on/serve.log | tail -35
test ! -e /data2/_shared/gpu.lock
ss -ltn 'sport = :8095'
nvidia-smi --query-gpu=index,memory.used --format=csv,noheader
cat /data2/FreeToken/runs/dev_D01/gpu_selfcheck_error.json
grep -nE 'health|ready|readiness|503' /data2/FreeToken/wt/e1r008/python/freetoken/server/api_server.py | head -25
