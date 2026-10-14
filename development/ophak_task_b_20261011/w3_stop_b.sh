#!/bin/bash
# W3（任务 B）：停 481（-12），用 restore12 的冻结控制器（做法同 A2 的 w3_stop.sh）。输出写入本工装目录。
cd /data2/FreeToken/development/ophak_task_a_20261011/restore12
/data2/FreeToken/venv/bin/python stop_approved_restore.py > /data2/FreeToken/development/ophak_task_b_20261011/W3_stop_B.log 2>&1
echo "rc=$?" >> /data2/FreeToken/development/ophak_task_b_20261011/W3_stop_B.log
