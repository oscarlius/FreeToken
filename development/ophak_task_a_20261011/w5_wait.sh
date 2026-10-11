#!/bin/bash
# W5 第二步：等待 -11 服务 serving 并跑一次批准的冒烟（与 restore10 同一脚本，只换目录）。
cd /data2/FreeToken/development/ophak_task_a_20261011/restore11
CUDA_VISIBLE_DEVICES= /data2/FreeToken/venv/bin/python -u wait_release_and_smoke.py > /data2/FreeToken/development/ophak_task_a_20261011/W5_wait.log 2>&1
echo "rc=$?" >> /data2/FreeToken/development/ophak_task_a_20261011/W5_wait.log
