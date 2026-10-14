#!/bin/bash
# W5 第三步（任务 B）：起 -13 观察器（做法同 A2 的 w5_observer.sh，只换目录）。
# 截止时间为 approval 中的 observation_until（2026-10-12T09:00:00+08:00）；观察器只采样，不停服、不回滚。
cd /data2/FreeToken/development/ophak_task_b_20261011/restore13
setsid -f /data2/FreeToken/venv/bin/python post_night_observer.py > /data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-13/observer_outer_B.log 2>&1
