#!/bin/bash
# 等模型真正就绪（PLE 100% + 1-token 探针 200），再跑指定组
set -e
GROUP="$1"
ROUND_DIR=/data2/_shared/runs/ft_rounds/_e1/E1-R000
LOG="$ROUND_DIR/serve_e1r000.log"
for i in $(seq 1 60); do
  if grep -q "Loading PLE table: 100%" "$LOG" 2>/dev/null; then
    CODE=$(curl -s -m 60 -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:8095/v1/chat/completions -H "Content-Type: application/json" -d '{"model":"Qwen3.8-Flash-Next-NVFP4","messages":[{"role":"user","content":"hi"}],"max_tokens":1,"stream":false}')
    if [ "$CODE" = "200" ]; then echo "READY probe=200 at try $i"; break; fi
    echo "probe=$CODE at try $i"
  fi
  sleep 10
done
bash /data2/FreeToken/scripts/ft_run_e1r000_group.sh "$GROUP"
