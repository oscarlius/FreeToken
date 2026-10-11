set -eu
date -Is
test ! -e /data2/_shared/gpu.lock || { cat /data2/_shared/gpu.lock; exit 3; }
ss -ltn 'sport = :8095'
nvidia-smi --query-gpu=index,memory.used --format=csv,noheader
ps -eo pid,args | grep -E '[f]t serve|[a]gent_trace.py (replay|generate)|[p]robe_ft|[f]t_probe|[c]old_eq.py|[b]atch[0-9]+_' || true
find /data2/_shared/runs/ft_rounds -maxdepth 3 -iname '*t1*' -print
find /data2/FreeToken/runs -maxdepth 3 -iname '*trace*.json' -print
find /data2/_shared/runs/ft_rounds -maxdepth 3 -iname '*trace*.json' -print
ls -l /data2/FreeToken/wt/e1r003/seed_45k.txt
du -sh /data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay
cat /data2/FreeToken/runs/dev_D01/pytest_final.log | tail -4
