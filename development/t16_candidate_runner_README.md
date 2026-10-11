# 新候选的 T16 默认路径门

此适配器只用于新候选，不修改已有 T16 执行器或封存轮次。复用协议文件的 SHA256 固定为 `51d8216e14417a6d922c44f3048082f985dfb59d8872dfc78ac0984f027fcd16`。服务器安装时将原协议逐字节复制为同目录的 `t16_base_runner.py`；禁止转换换行后继续沿用该哈希。

| case | 父树 → 候选 | 覆盖 |
|---|---|---|
| D03-continuation | c30ae0d → f5067bb | 层优先四臂，加普通分块四臂；普通分块验证 2000 和 32052 token |
| D06 | 23f2e2c → 0369263 | 默认层优先四臂 |

每组均在独立新进程执行父树/候选的 D0 开、关对照。保留原协议的全文逐字一致、配置对照、预填事件序列、D02 尾段及 H2D/D2D 字节检查；准确完整提交、直接父提交和实际加载的编译扩展须一致。默认路径清除全部 `FT_DEV_*` 和 `FT_D3_*`，GPU 可见性固定为设备 0。

运行前先做 Linux CPU 回归和独立源码审查。现有单 GPU 测试结束后，主线负责人检查真实 PID、锁、端口和 GPU 释放，才分配新的 RID 与 batch。`--rid` 必须匹配 `E2-RNNN-gate-D03` 或 `E2-RNNN-gate-D06`。本文件不预留编号，不授权复用旧轮次。

```powershell
python -m pytest -q development/tests/test_t16_candidate_runner.py
python development/t16_candidate_runner.py --self-test
```

Linux CLI 要求显式 `--case`、`--rid`、`--batch` 和完整 `--candidate-commit`。不带 `--run` 只做资源、来源、工具、扩展预检，不创建轮次/锁，不启动模型。正式启动须使用原子的批次日志预约、独占新包装脚本与 `start_new_session`；不得手工复用旧包装脚本。

测量成功只写 `complete_measurements_pending_review` 和拟议判定；独立复核、D04 封存及正式 verdict 分开。最新准确 adapter 29fa24e 已在 Linux CPU 29 PASS；最终启动器 241cbccc 单独冻结后 Linux CPU 32 PASS（含真实进程组生命周期与权限回归）、原协议自检 PASS，独立源码与证据复核通过。旧源及记录只读保留。2026-10-04 已实际启动 E2-R018-gate-D03/b46，批次 PID/PGID 3451139；8臂测量进行中，结果不提前宣称通过。实时阶段以宿主机观察为准，完整记录见 development/t16_candidate_r018_progress.md。
