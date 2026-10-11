#!/bin/bash
# A2 CPU 演练：正向（完整 T2 计划，缩放 1.0）与三项反向对照（缩放 0.05）。R_a_worker_exit 走请求结束后的复扫路径；
# R_a_hang 为挂起不断开，走请求进行中的实时监视路径。只用核心 0、2；不碰 8095；不占 GPU。
set -u
cd /data2/FreeToken/development/ophak_task_a_20261011
R=/data2/FreeToken/runs/dev_ophak_task_a2_20261011/rehearsal
PY=/data2/FreeToken/evaluation/toolchain/venv-eval/bin/python
mkdir -p "$R"
run() {
  name="$1"; shift
  taskset -c 0,2 env PYTHONDONTWRITEBYTECODE=1 "$PY" -B task_a_runner.py rehearse --run-dir "$R/$name" "$@" > "$R/$name.stdout" 2>&1
  echo "exit=$?" >> "$R/$name.stdout"
}
run R_positive --port 18400 --scale 1.0 --trajectories T2 &
run R_a_worker_exit --port 18410 --scale 0.05 --trajectories T2 --inject-json '{"B1_off":{"worker-exit-at":"T2/05"}}' &
run R_b_wrong_cached --port 18420 --scale 0.05 --trajectories T2 --inject-json '{"A1_on":{"wrong-cached":"T2/02"}}' &
run R_a_hang --port 18430 --scale 0.05 --trajectories T2 --inject-json '{"B1_off":{"worker-exit-at":"T2/05","worker-exit-hold-s":"30"}}' &
wait
echo done > "$R/ALL_DONE"
