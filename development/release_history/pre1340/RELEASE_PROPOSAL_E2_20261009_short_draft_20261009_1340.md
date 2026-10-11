# E2 发布提案（13:40 OPSv2 更新，仍待部署批准）

`release/e2` 指向 `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9`。分支创建不等于部署：部署、推送、生产服务和生产 endpoint 调用均未批准、未执行。旧文档已逐字归档至 `release_history/pre1340/`。

## 当前操作包与边界

唯一操作包来源为 `development/release_e2_ops_v2`；服务器封存为 `/data2/FreeToken/runs/dev_release/release_e2_ops_v4_20261009_1340/source`，同级 `evidence/CPU_pytest.txt` 为 **39 passed、0 skipped**（H1、M1–M4、LOW、H3）。这只是 CPU 证据，不证明 GPU、服务或生产冒烟。

环境按 OPSv2 copy/remove/set：复制宿主环境，删除 `FT_*`、`PYTHONPATH`、`CUDA_VISIBLE_DEVICES`，然后设置工作树 Python、FT venv/PATH、`PYTHONDONTWRITEBYTECODE=1`、`PYTHONUNBUFFERED=1`、GPU0 与 `MASTER_PORT=8096`。release 是 98,304、layer-major/4096；rollback 是 `184c965…` 的普通 8192 / 49,152，不开 layer-major。R056 argv 与环境差异已归档；R056 87K 历史样本不是现场冒烟。

## H1 / H2 / H3

H1 正、反 rollback 冒烟均完整导出六项：`RELEASE_SMOKE_BASE`、`RELEASE_SMOKE_MODE`、`RELEASE_SMOKE_RUN_DIR`、`RELEASE_SMOKE_SERVE_LOG`、`RELEASE_SMOKE_OWNER`、`RELEASE_SMOKE_EXCLUSIVE_APPROVAL`。`run_smoke.py` 的 JUnit 门必须恰好 **1 passed、0 skipped**。

H2 当前阻断 rollback：只读检查 HEAD=`184c965…`、完整 argv + `--help` 合法，R066 `cached_rows()` 正则在历史日志匹配 68 条 Prefill；但 `git status --porcelain --untracked-files=all --ignored` before/after 都非空（ignored `.pytest_cache`、egg-info、`__pycache__` 等）。不清理、不绕过、不启动。历史日志没有 API usage 的 `prompt_tokens` / `completion_tokens` / `total_tokens`，不能替代 R066 SDK usage。证据：`release_e2_ops_v2/rollback_preflight_evidence/h2_deep_check.json`。

H3 资源释放最多等待 60 秒；停止总上限 220 秒。TERM/INT/HUP 在锁前登记；`finally` 仅释放 own lock / 未替换 active。清理失败写 quarantine，quarantine 阻断新启动。monitor 每 60 秒 health，一连 3 次失败或 supervisor 退出写 alert。外来 Prefill 为 `smoke_invalid`、exit 75：同版重启重测，不回滚。所有子进程 cwd 为 run_dir，argv/env diff 已归档。

## 队列与限制

- R058 双会话约 378 MiB 仅为场景采样；R061f 仅 chat 一次 OOM 注入。默认 128 / 900 是一致性记录，非压测或全面恢复证明。
- R045：旧 v18 已停止；新 `481` AIPerf CPU 计划为 2 服务 / 4 generation calls，部署后需新 admission。
- R067：已批准待实际范围仅 `P8192/P8256 × T1/T64` 4 格、最多 10 服务 / 14 调用；hot 原样 `481`，cold 为 D20 `d50` one-shot 8 fresh。`≤64` 等四格 ALLPASS；not_met 记已知缺陷，E2 发布继续。
- E3 禁用 8095/8096；Strata 22/345 未批准。部署、推送、停服、回滚仍均待独立批准。
