#!/bin/bash
# W5 第三步：起 -11 观察器（与 restore10 的 §5.5 同一命令，只换目录）。
cd /data2/FreeToken/development/ophak_task_a_20261011/restore11
setsid -f /data2/FreeToken/venv/bin/python post_night_observer.py > /data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-11/observer_outer.log 2>&1
