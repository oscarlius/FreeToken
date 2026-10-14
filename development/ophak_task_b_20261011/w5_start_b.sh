#!/bin/bash
# W5 第一步（任务 B）：恢复 481 到 release-e2（481d3a7），用 restore13（审批 -13）。
# start_approved_release.py 自己做执行前检查（无计算进程、8095/8096 无监听、GPU 显存低、无 gpu.lock、运行目录不存在）。
cd /data2/FreeToken/development/ophak_task_b_20261011/restore13
/data2/FreeToken/venv/bin/python start_approved_release.py > /data2/FreeToken/development/ophak_task_b_20261011/W5_start_B.log 2>&1
echo "rc=$?" >> /data2/FreeToken/development/ophak_task_b_20261011/W5_start_B.log
