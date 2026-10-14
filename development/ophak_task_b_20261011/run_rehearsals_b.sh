#!/bin/bash
# 任务 B CPU 演练：正向（缩放 1.0，五个服务完整跑）与五项反向对照（缩放 0.05）。
# 只用核心 0、2；不碰 8095；不占 GPU（构建门的探针在 CUDA_VISIBLE_DEVICES 为空时导入 freetoken）。
set -u
cd /data2/FreeToken/development/ophak_task_b_20261011
R=/data2/FreeToken/runs/dev_ophak_task_b_20261011/rehearsal
PY=/data2/FreeToken/evaluation/toolchain/venv-eval/bin/python
mkdir -p "$R"
run() {
  name="$1"; shift
  taskset -c 0,2 env PYTHONDONTWRITEBYTECODE=1 "$PY" -B task_b_runner.py rehearse --run-dir "$R/$name" "$@" > "$R/$name.stdout" 2>&1
  echo "exit=$?" >> "$R/$name.stdout"
}
run R_positive --port 18500 --scale 1.0 &
run R_a_output_tweak --port 18510 --scale 0.05 --inject-json '{"C_A1":{"output-tweak":"T2/03"}}' &
run R_b_param_missing --port 18520 --scale 0.05 --inject-json '{"C_B1":{"parsed-min-tokens":"0"}}' &
run R_c_wrong_pythonpath --port 18530 --scale 0.05 --inject-json '{"C_B2":{"pythonpath":"/data2/FreeToken/wt/release-e2/python"}}' &
run R_d_one_oom --port 18540 --scale 0.05 --inject-json '{"C_B1":{"oom-at":"T2/05"}}' &
run R_e_two_oom --port 18550 --scale 0.05 --inject-json '{"C_A1":{"oom-at":"T2/05"},"C_B1":{"oom-at":"T2/05"}}' &
run R_f_startup_oom_one --port 18560 --scale 0.05 --inject-json '{"C_A1":{"exit-before-ready":"oom"}}' &
run R_g_startup_two_plain --port 18570 --scale 0.05 --inject-json '{"C_A1":{"exit-before-ready":"plain"},"C_B1":{"exit-before-ready":"plain"}}' &
wait
echo done > "$R/ALL_DONE"
