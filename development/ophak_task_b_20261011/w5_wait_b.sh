#!/bin/bash
# W5 第二步（任务 B）：等待 -13 服务 serving 并跑一次批准的冒烟（做法同 A2 的 w5_wait.sh，只换目录）。
cd /data2/FreeToken/development/ophak_task_b_20261011/restore13
CUDA_VISIBLE_DEVICES= /data2/FreeToken/venv/bin/python -u wait_release_and_smoke.py > /data2/FreeToken/development/ophak_task_b_20261011/W5_wait_B.log 2>&1
echo "rc=$?" >> /data2/FreeToken/development/ophak_task_b_20261011/W5_wait_B.log
