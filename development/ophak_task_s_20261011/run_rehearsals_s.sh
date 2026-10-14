#!/bin/bash
# 任务 S P1 的 CPU 演练：正向与四项反向对照，全部按真实时间（缩放 1.0）。
# 零输出窗口（0.4 s / 0.2 s）与延迟同量级，缩放会失真，故控制组也不缩放；约 3 分钟。
# 只用核心 0、2；不碰 8095；不占 GPU（--no-gpu，桩服务不加载模型）。
set -u
cd /data2/FreeToken/development/ophak_task_s_20261011
PY=/data2/FreeToken/evaluation/toolchain/venv-eval/bin/python
R=/data2/FreeToken/runs/dev_ophak_task_s_20261011/rehearsal
PREREG=/data2/FreeToken/development/anchor_cut_accounting_20261011/PREREG_TASK_S_v2.json
INPUTS=/data2/FreeToken/development/ophak_task_a_20261011/INPUTS.json
TASK_A_DIR=/data2/FreeToken/development/ophak_task_a_20261011
L64=/data2/FreeToken/development/gemini_oom_hybrid_20261011/inputs/L64.json
TOKEN='{"owner": "rehearsal"}'
mkdir -p "$R"

one() {
  # 用法：one 名称 端口 缩放 "桩服务额外参数" "运行器额外参数"
  name="$1"; port="$2"; scale="$3"; stub_extra="$4"; tool_extra="$5"
  d="$R/$name"
  mkdir -p "$d"
  printf '%s' "$TOKEN" > "$d/gpu.lock"
  "$PY" -c "import json,sys; json.dump({'log': sys.argv[1], 'gpu_owner': {'lock_token': sys.argv[2]}}, open(sys.argv[3], 'w'))" \
    "$d/serve.log" "$TOKEN" "$d/active.json"
  taskset -c 0,2 env PYTHONDONTWRITEBYTECODE=1 "$PY" -u -B stub_stall_server.py --port "$port" \
    --serve-log "$d/serve.log" --prereg "$PREREG" --inputs "$INPUTS" --l64 "$L64" --time-scale "$scale" \
    $stub_extra > "$d/stub.stdout" 2>&1 &
  stub=$!
  for i in $(seq 1 60); do
    curl -s --noproxy '*' -o /dev/null "http://127.0.0.1:$port/health" && break
    sleep 0.5
  done
  taskset -c 0,2 env PYTHONDONTWRITEBYTECODE=1 "$PY" -u -B stall_runner.py run --run-dir "$d/run" \
    --endpoint "http://127.0.0.1:$port" --active-json "$d/active.json" --gpu-lock "$d/gpu.lock" \
    --stop-file "$d/NO_STOP.md" --prereg "$PREREG" --inputs "$INPUTS" --task-a-dir "$TASK_A_DIR" \
    --l64 "$L64" --time-scale "$scale" --no-gpu $tool_extra > "$d/tool.stdout" 2>&1
  echo "exit=$?" >> "$d/tool.stdout"
  kill "$stub" 2>/dev/null
  wait "$stub" 2>/dev/null
}

one R_positive 18600 1.0 "" "" &
one R_a_restart 18610 1.0 "" "--a-restart-s 1.5" &
one R_b_zero 18620 1.0 "--a-no-pause T2/03" "" &
one R_c_contaminate 18630 1.0 "--contaminate T2/05" "" &
one R_d_precheck 18640 1.0 "--completed-init 3" "" &
wait
echo done > "$R/ALL_DONE"
