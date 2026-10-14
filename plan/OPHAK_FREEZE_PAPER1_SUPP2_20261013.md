# op-hak 指令：补冻结三个目录为 FTD-20261013-1（2026-10-13 凌晨，op 会话）

- **授权**：非核心审核发现三个目录的数值与论文一致，但都不在任何冻结版本里。用户 10-13 凌晨选择"补冻结（推荐）"：只封存，不重测。
- **性质**：只读盘点、哈希，然后去掉目录写权限。不占 GPU，不停服，不碰生产目录。
- **上一版**：FTD-20261012-2（R045）。

## 冻结范围（只收下列目录）

| # | 目录 | 论文用途 | op 已核的数值 |
|---|---|---|---|
| 1 | `/data2/FreeToken/runs/dev_gemini_oom_hybrid_20261011/window01/` | §12 OOM 阶梯；§4.7 表 5c CPU 路径拟合的输入（**核心结论依赖**） | S4 单路 28.55 / 28.71 / 28.58、两路 18.86 / 18.88 / 18.95 / 18.96；S5 单路 30.94；S1 L87 87,128 成功、L95 OOM；S2 碎片 147.52 MiB；重载 235.42 s |
| 2 | `/data2/FreeToken/development/gemini_oom_hybrid_20261011/` | 上项的预登记与计划（`OOM_MEMORY_MODEL.md`、`PLAN.json`、`RESULT.md`） | 20 KB/token 的估算来源 |
| 3 | `/data2/FreeToken/development/d10_staggered_20261009/` | §8.1 D10 预登记预测（失败预测，按规则 9 保留） | `prediction_manifest.json` sha256 前缀 3216e155；理想 41.667、区间 33.12–40.03 |
| 4 | `/data2/FreeToken/development/d15_sim_20261010/strategy_predictability_2033_root_reviewed/` | §8.3 2,401 槽替换规则 | seed_real LRFU H=384 −1.673 pp、平局规则 −0.886 pp |

- `dev_gemini_oom_hybrid_20261011/` 下的 `rehearsal_R1–R3/` 不收（论文未引用），只在清单中登记为 not_included。
- op 在 10-13 00:03 做过只读预查：四处合计约 19 MB、约 930 个文件，10-12 以后没有新写入。

## F0 盘点（只读）

1. 逐文件列出路径、字节数、最后修改时间、sha256。
2. 写入检查：用 `/proc/*/fd` 查有没有进程持有这些目录里文件的写句柄；有就停下报告。
3. 体量检查：合计超过 5 GB 先停下报告。
4. 数值复核：按上表"op 已核的数值"逐项核对一次（只读 JSON/CSV），任何一项不符先停下报告。

## F1 封存（F0 无异常即直接执行）

- 写入 `/data2/_shared/runs/ft_releases/FTD-20261013-1/manifest.json` 与 `SHA256SUMS`，文件 0444、目录 0555。manifest 的 `scope_source` 写本指令的路径与 sha256。
- 对上表四个目录执行 `chmod -R a-w`，只限这些目录本身，不动父目录。回执记录改动前后的权限。
- 封存后复算全部哈希，必须一致。
- 把 manifest、SHA256SUMS 与回执复制到本地 `freetoken/paper-en/audit/freeze/`（文件名前缀 `FTD-20261013-1.`），写协调日志（服务器真实时间），并发消息给 op。

**先停下报告的情况**：有写句柄；体量超过 5 GB；目录不存在；F0 第 4 步数值不符。

## 复盘与自检（op）

| 项 | 处理 |
|---|---|
| 冻结范围有依据 | 四个目录的数值均由 op 在非核心审核中从原件复算（`paper-en/scripts/trace/g17、g21、g22、g24`），并写入 `audit/trace_report.md` |
| 只封存不重测 | 不启动服务、不发请求、不改任何文件内容 |
| 安全 | 只改这四个目录的写权限；不碰 `runs/production`、`development/ophak_release_e3_*` 与运行中的服务 |
| 可逆 | `chmod -R u+w` 即可恢复，回执记录原权限 |
| 停止条件 | 上面四种情况 |
| 与上一版的关系 | 与 FTD-20261012-2 同一格式；不修改任何已封存版本 |
