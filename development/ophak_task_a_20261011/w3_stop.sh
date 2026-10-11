#!/bin/bash
# W3：停 481，按原指令 §4 W3 使用 restore10 的冻结控制器。输出写入本工装目录。
cd /data2/FreeToken/development/gemini_oom_hybrid_20261011/restore10
/data2/FreeToken/venv/bin/python stop_approved_restore.py > /data2/FreeToken/development/ophak_task_a_20261011/W3_stop.log 2>&1
echo "rc=$?" >> /data2/FreeToken/development/ophak_task_a_20261011/W3_stop.log
