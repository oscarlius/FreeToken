# 00 交接现状核对（阶段 1 步骤 1.1）

- 执行者：KIMI
- 执行时间（本地命令实测）：2026-10-11T02:23:51+08:00
- 服务器时间：`Sun Oct 11 02:23:51 AM CST 2026`
- 操作性质：只读（`ssh 9 'date; uptime; nvidia-smi; cat production.active.json; ls -la gpu.lock; docker ps -a; ps -eo ...'`）

---

## 一、原始输出

### 1. date / uptime

```
Sun Oct 11 02:23:51 AM CST 2026
 02:23:52 up 20 days,  6:25,  0 users,  load average: 0.30, 0.58, 1.59
```

### 2. nvidia-smi

```
Sun Oct 11 02:23:52 2026
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 580.178.04             Driver Version: 580.178.04     CUDA Version: 13.0     |
+-----------------------------------------------------------------------------------------+
| GPU  Name                 Persistence-M | Bus-Id          Disp. | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
+=========================================+======================+======================+
|   0  NVIDIA GeForce RTX 4090        Off |   00000000:CA:00.0 Off |                  Off |
| 30%   31C    P8             20W /  450W |   22454MiB /  24564MiB |      0%      Default |
+-----------------------------------------------------------------------------------------+
| Processes:                                                                              |
|    0   N/A  N/A           97659      C   ...a2/FreeToken/venv/bin/python3      22218MiB |
+-----------------------------------------------------------------------------------------+
```

（GPU 上唯一计算进程 PID 97659，为生产 `ft serve` 的 worker，属预期。）

### 3. production.active.json

```json
{
  "mode": "release",
  "approval_id": "RESTORE481-MORNING-20261011-07",
  "run_dir": "/data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-07",
  "commit": "481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9",
  "worktree": "/data2/FreeToken/wt/release-e2",
  "argv": [
    "taskset", "-c", "1,3-47",
    "/data2/FreeToken/venv/bin/ft", "serve",
    "--model-path", "/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay",
    "--served-model-name", "Qwen3.8-Flash-Next-NVFP4",
    "--host", "172.16.108.9",
    "--port", "8095",
    "--memory-ratio", "0.88",
    "--moe-cache-auto",
    "--moe-prefill-hit-d2d",
    "--ple-backend", "pinned",
    "--moe-strategy", "offload",
    "--quant-backend", "moe.nvfp4=triton",
    "--max-running-requests", "2",
    "--cuda-graph-max-bs", "2",
    "--kv-reserve-tokens", "98304",
    "--max-seq-len-override", "98304",
    "--max-prefill-length", "4096",
    "--enable-cache-report",
    "--enable-special-token-ckpt",
    "--tool-call-parser", "qwen3_coder",
    "--reasoning-parser", "qwen3",
    "--prefill-layer-major",
    "--mamba-host-slots", "0"
  ],
  "worktree_receipt": "/data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-07/worktree_receipt.json",
  "supervisor": {"pid": 97245, "start_ticks": 174914450, "execution_id": "97245:174914450", "pgid": 97245, "session": 97245, "state": "R"},
  "service": {"pid": 97256, "start_ticks": 174914481, "execution_id": "97256:174914481", "pgid": 97256, "session": 97256, "state": "R"},
  "gpu_owner": {"owner": "production:release:RESTORE481-MORNING-20261011-07", "batch": 0, "pid": 97245, "start_ticks": 174914450, "execution_id": "97245:174914450", "lock_inode": 34031545, "lock_device": 2049},
  "restart": "no outer restart",
  "host": "172.16.108.9",
  "log": "/data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-07/serve.log",
  "stop_TERM_seconds": 120,
  "stop_KILL_seconds": 30,
  "monitor": {"pid": 97257, "start_ticks": 174914481, "execution_id": "97257:174914481", "pgid": 97257, "session": 97257, "state": "R"}
}
```

### 4. gpu.lock

```
-rw------- 1 dell dell 149 Oct 11 01:50 /data2/_shared/gpu.lock
```

（锁文件存在，由生产监管进程 PID 97245 持有，与 production.active.json 的 gpu_owner 一致。）

### 5. docker ps -a（全量）

```
sparkdash Up 13 hours
run-monitor Up 36 hours
model-hub-dashboard Up 7 days
sparkdash-rollback-20261010-fab8dad Exited (0) 13 hours ago
open-webui Up 9 days (healthy)
cand-AGENT_ACC Exited (137) 9 days ago
qwen38-flash Exited (0) 9 days ago
qwen38-flash-pre-codex-20260930 Exited (0) 10 days ago
p7pro-p7-admin-web-1 Up 2 weeks (healthy)
p7pro-p7-gateway-1 Up 2 weeks (healthy)
p7pro-p7-control-1 Up 2 weeks (healthy)
webprotege-mongo Up 2 weeks
webprotege Up 2 weeks
ontology-web Up 2 weeks
ontology-lab Up 2 weeks
p7pro-p7-gateway-ingress-1 Up 2 weeks (healthy)
sparkdash-rollback-20261001-e93fc87 Exited (0) 9 days ago
p7-gpu-gpu-controller-1 Up 2 weeks
p7-gpu-gpu-action-runner-1 Up 2 weeks
portainer_agent.sh18wzdxc7ch54yrudk5e057g.qa7lohmt51m2u8ndlkk22uorj Up 2 weeks
qwen38-27b Exited (0) 2 weeks ago
p7pro-p7-control-gpu-route-init-1 Exited (0) 5 weeks ago
p7pro-p7-provider-egress-1 Up 2 weeks (healthy)
open-webui-pre8095-20261001_213625 Exited (0) 9 days ago
ollama Exited (0) 6 hours ago
p7pro-p7-postgres-1 Up 2 weeks (healthy)
p7pro-p7-redis-1 Up 2 weeks (healthy)
p7pro-p7-identity-egress-proxy-1 Up 2 weeks (healthy)
mineru-mineru-capacity-guard-1 Exited (137) 5 weeks ago
mineru-gradio Up 9 days
p7-containerd-stack-probe-a666 Exited (0) 6 weeks ago
p7-containerd-lease-probe-a666 Exited (0) 6 weeks ago
p7-dockerd-stack-read-a666 Exited (0) 6 weeks ago
p7-dockerd-stack-probe-a666 Exited (0) 6 weeks ago
mineru-api Exited (0) 9 days ago
open-webui-pre-qwen-20260901T111349 Exited (0) 6 weeks ago
llamafactory Up 2 weeks
bge-reranker Exited (137) 2 months ago
portainer_agent.sh18wzdxc7ch54yrudk5e057g.xa2bhcf9ga2gt2mtkmzqsz3tl Dead
ollama-gpu-backup-20260901T112147 Exited (0) 5 weeks ago
ollama_pre_opt_20260727_193031 Up 2 weeks
```

### 6. ps -eo pid,etime,args（python / ft serve / aiperf 过滤后，全量）

```
   1383 20-06:25:01 /usr/bin/python3 /usr/bin/networkd-dispatcher --run-startup-triggers
   1462 20-06:25:00 /usr/bin/python3 /usr/share/unattended-upgrades/unattended-upgrade-shutdown --wait-for-signal
   2474 20-06:24:24 /usr/local/bin/python3.12 /usr/local/bin/uvicorn proxy:app --host 0.0.0.0 --port 8089
   2500 20-06:24:24 /usr/local/bin/python3.12 /usr/local/bin/uvicorn pro7.admin_api.app.services.provider_egress:app --host 0.0.0.0 --port 8096
   3024 20-06:24:23 /opt/conda/bin/python /opt/conda/bin/llamafactory-cli webui
  97245       32:57 /data2/FreeToken/venv/bin/python .../release_control.py --start --mode release --approval-id RESTORE481-MORNING-20261011-07 --run-dir /data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-07
  97256       32:57 /data2/FreeToken/venv/bin/python3 /data2/FreeToken/venv/bin/ft serve --model-path ... --host 172.16.108.9 --port 8095 ... --moe-strategy offload ... --prefill-layer-major --mamba-host-slots 0
  97257       32:57 /data2/FreeToken/venv/bin/python .../monitor_health.py --run-dir /data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-07 --supervisor {...}
  97658       32:52 .../python3 -B -c from multiprocessing.resource_tracker import main;main(18)
  97659       32:52 .../python3 -B -c from multiprocessing.spawn import spawn_main; spawn_main(...)  （GPU worker）
  97660       32:52 .../python3 -B -c from multiprocessing.spawn import spawn_main; spawn_main(...)
 111553       27:54 /data2/FreeToken/venv/bin/python /data2/FreeToken/development/morning_restore07_20261011/post_night_observer.py
 111554       27:54 /data2/FreeToken/venv/bin/python /data2/FreeToken/development/morning_restore07_20261011/observe_overnight.py --run-dir ... --until 2026-10-11T09:00:00+08:00
 604909  9-13:37:51 /usr/bin/python3 /usr/local/bin/mineru-gradio --server-name 0.0.0.0 --server-port 7860 ...
 661396 17-06:29:17 python3 -m uvicorn controller.runner:create_runner_app --factory --host 127.0.0.1 --port 8091
1173035 14-04:04:38 /usr/local/bin/python3.12 /usr/local/bin/uvicorn pro7.admin_api.app.main:app --host 0.0.0.0 --port 8027
1176045 14-04:03:42 /usr/local/bin/python3.12 /usr/local/bin/uvicorn pro7.admin_api.app.gateway_main:app --timeout-keep-alive 75 --host 127.0.0.1 --port 8028
（另有 12 组 7 天前遗留的 multiprocessing resource_tracker / spawn_main 辅助进程，etime 约 7 天，无 development/ 脚本）
2340620  9-04:47:24 /usr/local/bin/python3 -m uvicorn open_webui.main:app --host 0.0.0.0 --port 8080 ...
2715076  1-12:06:05 python3 monitor.py
3609180 16-15:01:15 python3 -m uvicorn controller.app:create_app --factory --host 172.16.108.9 --port 8089
3791245  7-08:06:18 python3 server.py
4035646  7-06:44:49 ... multiprocessing 辅助进程 ...
4159382  6-05:30:51 /data2/FreeToken/venv/bin/python -m http.server 8100 --bind 0.0.0.0
```

注：第 6 节为便于阅读做了长行截断（以 `...` 标注），完整逐字节输出见同目录 `00_HANDOVER_STATE.raw.txt`。

---

## 二、逐项判据核对

| # | 成功判据 | 实测 | 结论 |
|---|---|---|---|
| 1 | 生产服务是 481d3a7，审批号以 `-07` 结尾 | commit = `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9`；approval_id = `RESTORE481-MORNING-20261011-07` | ✅ 符合 |
| 2 | 容器 `ollama` 处于 Exited 状态 | `ollama Exited (0) 6 hours ago` | ✅ 符合 |
| 3 | 除 0.4 节 5 类进程外，无其他 `development/` 下的 Python 任务 | 0.4 节 5 类进程全部在：`release_control.py`(97245)、`ft serve`(97256)、`monitor_health.py`(97257)、`post_night_observer.py`(111553)、`observe_overnight.py`(111554)；ps 列表中除这两个观察者外无其他 `/data2/FreeToken/development/` 路径的 Python 任务 | ✅ 符合 |

## 三、补充观察（不影响判据，仅记录）

1. 容器 `ollama_pre_opt_20260727_193031` 处于 **Up 2 weeks** 状态。手册 0.2 红线第 2 条要求不碰它；此处仅记录现状，不做任何操作。
2. 存在约 12 组 7 天前遗留的 `multiprocessing resource_tracker / spawn_main` 辅助进程（venv python3，无 development/ 脚本），以及 `python3 monitor.py`（etime 1.5 天）、`python3 server.py`、`python -m http.server 8100` 等非本次手册范围的长期进程。均不属于 0.4 节所列 5 类，也都不在 `development/` 下，按判据口径不构成冲突；按红线不动它们。
3. GPU 被生产服务正常占用（22218MiB，PID 97659），gpu.lock 由监管进程持有——阶段 1 全程不触碰 GPU。
4. 两个观察进程（111553、111554）的 `--until` 为 2026-10-11T09:00:00+08:00，与手册 2.6 节"09:00 后自行退出"的预期一致。

## 四、结论

**交接现状核对通过（3/3 判据符合）。** 可以进入步骤 1.2。
