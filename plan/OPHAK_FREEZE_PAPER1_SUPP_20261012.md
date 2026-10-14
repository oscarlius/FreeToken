# op-hak 指令：补冻结 R045 为 FTD-20261012-2（2026-10-12 晚，op 会话）

- **授权**：阶段 1.2 审核发现 R045（v5.8 §8.1、表 12c、表 12f"两路短提示"行）不在任何冻结版本里。用户 10-12 晚选择"补冻结版本"：只封存，不重测。
- **性质**：只读盘点、哈希，然后去掉目录写权限。不占 GPU，不停服。
- **上一版**：FTD-20261012-1。

## F0 盘点（只读）

1. **结果目录**：`/data2/FreeToken/development/r045_production_aiperf_20261009/`。
   - 其中 `R045_RESULT.json` 的 4 行逐请求解码应为 22.425 / 22.531 / 22.030 / 22.206（request_id 前缀 b6eed489 / bdfa2cae / beffbd9f / a225d90a）。
2. **原始记录**：用 `EXECUTION_MANIFEST*.json`、`FINAL_EVIDENCE_MANIFEST.json`、`LAUNCH_RECEIPT*.json` 定位 R045 实际运行时的 AIPerf 原始导出（profile_export*.jsonl 等）和服务日志所在目录，一并纳入。
   - 只收 manifest 明确指向的路径。
   - 生产目录（`runs/production`）里的文件只做文件级登记，不改权限。
3. 写入检查与体量检查同上一份指令：查句柄与最后修改时间；超过 5 GB 先停下报告。
4. **判定原文**：照录 `R045_RESULT.json` 中的 classification（应为 not_met）与 criterion，不改判。

## F1 封存（F0 无异常即直接执行；下列情况先停下报告）

- 写入 `/data2/_shared/runs/ft_releases/FTD-20261012-2/manifest.json` 与 `SHA256SUMS`。文件权限 0444，目录 0555。
- 对清单中的目录执行 `chmod -R a-w`，只限这些目录本身。回执中记录改动前后的权限。
- 封存后复算全部哈希，必须一致。
- 把 manifest 与 SHA256SUMS 复制到本地 `freetoken/paper-en/audit/freeze/`，写协调日志，并发消息给 op。

**先停下报告的情况**：
- 找不到 AIPerf 原始导出；
- 4 个数值与上面不符；
- 有写句柄；
- manifest 指向的路径不存在。

## 复盘与自检（op）

| 项 | 处理 |
|---|---|
| 冻结范围有依据 | v5.8 §8.1 引用"R045独立结果"；目录与数值由 op 在 1.2 中核到 |
| 不改判 | 照录 classification |
| 安全 | 只改 R045 目录的写权限；生产目录只做文件级登记 |
| 可逆 | `chmod u+w` 即可恢复，回执记录原权限 |
| 停止条件 | 上面四种情况 |
