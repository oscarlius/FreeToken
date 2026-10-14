# op-hak 指令：第一篇论文的数据冻结（FTD-20261010-1 / FTD-20261012-1）（2026-10-12 晚，op 会话）

- **授权**：用户 10-12 晚批准《第一篇论文发布执行计划》阶段 0 由 op 执行，冻结范围选"加入任务 A/A2/B/S"。用户此前也说过"有些内容，你也可以直接让op-hak 去执行"。
- **性质**：只读盘点与哈希，最后去掉已完成轮次目录的写权限。不占 GPU，不停服，不是压力测试。
- **不碰**：生产与发布目录（`runs/production`、`development/ophak_release_e3_*`、运行中服务的日志）；`ft_rounds/`、`runs/`、`development/` 这些父目录本身（以后的新轮次还要在里面建目录）。

## F0 盘点（只读；完成后报告 op，等 op 回复"封存"）

1. **FTD-20261010-1 = v5.8 附录 A.5 表 A4 的全部行**（`paper/src/body_v58.html` 第 776 行起）：

   b148 D10 原型、b155、b156 T03b、b159 R044b、b162、b163 D09 T16、b164 D09 T17、R067e b160/b161/b166、Strata S1/S2r1/S3/S4、D15 窗口 A/B、D10 闭环 X/Y、D15 阶段 0。

   每行要写清：
   - 服务器目录（可多个）；
   - 判定原文出自哪个文件（路径加 sha256），不改判；
   - 文件数、总字节；
   - 每个文件的 sha256，写进 SHA256SUMS。
2. **FTD-20261012-1**：
   - 任务 A：`runs/dev_ophak_task_a_20261011`、`development/ophak_task_a_20261011`；
   - 任务 A2：`runs/dev_ophak_task_a2_20261011`、`development/anchor_cut_accounting_20261011`；
   - 任务 B：`runs/dev_ophak_task_b_20261011`、`development/ophak_task_b_20261011`，其中 RESULT_B.md 应为 9b00979ec571…，task_b_indep_judgement.json 应为 ef40b340b583…；
   - 任务 S：`runs/dev_ophak_task_s_20261011`、`development/ophak_task_s_20261011`；
   - **v5.8 正文引用、但既不在 FTD-20261009-1 也不在 A.5 里的其他 2026-10-11 轮次**，至少包括 hybrid 同窗口 A/B（`runs/dev_hybrid_verify_20261011`，§7.7 的 +21%/+55%）。名单的来源：扫描 v5.8 源文件里注明 10-11 的证据名，逐条对到目录。对不上的、拿不准的列出来交 op，你不要自己决定收不收。
3. **写入检查**：每个目录都报告最近一次修改时间，以及是否有进程正打开其中的文件（`lsof +D` 或 `fuser -vm`）。有写入迹象的目录，标出来，不封存。
4. **体量**：先报告总字节数。超过 50 GB 先停，报给 op 再继续。哈希一律用 `nice -n 19 ionice -c3`。

F0 产出：`development/ophak_freeze_paper1_20261012/INVENTORY.md`，外加两份清单草稿（JSON，字段对齐 FTD-20261009-1 的 `ft_data_release/v1`：release_id、created_at、previous_release、rounds[dir, verdict_source, files, bytes, sha256sums]、not_included、immutability）。

## F1 封存（收到 op 的"封存"后执行）

1. 清单写到 `/data2/_shared/runs/ft_releases/<ID>/manifest.json` 与 `SHA256SUMS`。文件权限 0444，目录 0555。
2. 对清单列出的轮次目录执行 `chmod -R a-w`，只限这些目录本身，不动父目录。写回执，逐项记录改动前后的权限。
3. 封存后再算一遍 SHA256SUMS，必须与清单一致。
4. 把两份 manifest 复制到本地 `freetoken/paper-en/audit/freeze/`，写协调日志，并发消息给 op。

## 复盘与自检（op，下发前）

| 项 | 处理 |
|---|---|
| 冻结范围有依据 | A.5 行名取自 v5.8 原文；任务 A/A2/B/S 由用户选定；10-11 轮次按正文引用扫描，拿不准的交 op 定 |
| 不改判 | 每轮只登记它原有封存或独审中的判定原文与来源 |
| 安全 | 只改已完成轮次目录的写权限；父目录与生产不动；先查写入迹象 |
| 可逆 | `chmod u+w` 即可恢复；回执记录了原权限 |
| 两步走 | F0 只读，op 核对后才进 F1 |
| 时间 | 估计以日志与 JSON 为主，体量小，F0 预计 1–2 小时；超过 50 GB 先报告 |
