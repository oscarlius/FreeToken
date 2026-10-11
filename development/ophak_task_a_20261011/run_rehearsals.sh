#!/bin/bash
# P1 演练：四项反向对照并行（R1 正向对照由单独命令启动）。只用 CPU 核心 0 和 2，不碰 8095，不占 GPU。
set -u
cd /data2/FreeToken/development/ophak_task_a_20261011
R=/data2/FreeToken/runs/dev_ophak_task_a_20261011/rehearsal
PY=/data2/FreeToken/evaluation/toolchain/venv-eval/bin/python
mkdir -p "$R"
run() {
  name="$1"; shift
  taskset -c 0,2 env PYTHONDONTWRITEBYTECODE=1 "$PY" -B task_a_runner.py rehearse --run-dir "$R/$name" "$@" \
    > "$R/$name.stdout" 2>&1
  echo "exit=$?" >> "$R/$name.stdout"
}
run R2a_role_packet --port 18310 --scale 0.05 &
run R2b_wrong_cached --port 18320 --scale 0.05 --inject-json '{"A1_on":{"wrong-cached":"seed_real/02"}}' &
run R2c_oom --port 18330 --scale 0.05 --inject-json '{"B1_off":{"oom-at":"seed_real/03"}}' &
run R2d_segments_mismatch --port 18340 --scale 0.05 --inject-json '{"B2_off":{"segments-override":"seed_real/05=2000,104"}}' &
wait
echo done > "$R/CONTROLS_DONE"
