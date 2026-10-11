#!/bin/bash
set -u
echo '====PID===='
ps -o pid,ppid,etime,user,pcpu,pmem,cmd -p 594391
echo '====CWD===='
ls -l /proc/594391/cwd 2>/dev/null
echo '====CMDLINE===='
tr '\0' ' ' < /proc/594391/cmdline; echo
echo '====ENV INTERESTING===='
tr '\0' '\n' < /proc/594391/environ 2>/dev/null | grep -Ei 'CUDA|VLLM|HF_|MODEL|GPU|NCCL|TORCH' | head -n 40
echo '====LISTEN===='
ss -lntp | grep -E ':8090|:8092|:8080|:8000|:3000|:1919|:11434|:8089' || true
echo '====PARENT===='
ppid=$(awk '{print $4}' /proc/594391/stat)
ps -o pid,ppid,etime,cmd -p "$ppid"
echo '====DOCKER ALL QWEN/VLLM===='
docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}\t{{.Image}}' | grep -Ei 'qwen|vllm|llama|open-webui|ollama' || true
echo '====COMPOSE DIRS===='
ls -la /home/dell/qwen38/deploy 2>/dev/null
ls /home/dell/qwen38 2>/dev/null
find /home/dell /data2 -maxdepth 3 -name 'compose*.yml' -o -name 'compose*.yaml' 2>/dev/null | grep -iE 'qwen|vllm' | head
