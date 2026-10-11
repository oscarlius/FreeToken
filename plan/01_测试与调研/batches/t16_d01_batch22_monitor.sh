set -eu
ps -o pid,pgid,lstart,args -p 866506 || true
tail -40 /data2/_shared/runs/ft_rounds/batch22.log 2>/dev/null || true
printf 'lock='; test -e /data2/_shared/gpu.lock && cat /data2/_shared/gpu.lock || echo absent
printf 'gpu='; nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits
ss -ltn | grep ':8095 ' || true
echo batch23
ps -o pid,pgid,lstart,args -p 879708 || true
tail -40 /data2/_shared/runs/ft_rounds/batch23.log 2>/dev/null || true
