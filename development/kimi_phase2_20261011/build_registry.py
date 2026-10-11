# 合并 version_registry_raw.tsv 与人工档案核对结论，生成 VERSION_REGISTRY_20261011.md / .json。
# 人工结论来源：plan/02_开发任务 卡片、plan/COORDINATION_LOG.md、plan/01_测试与调研/results/ 的逐条命中
# （见 version_registry_xref.json）；查不到的一律"待核"，不推测。
import json, os

ROOT = os.path.dirname(os.path.abspath(__file__))
FT = os.path.abspath(os.path.join(ROOT, "..", ".."))

# worktree -> (关联卡片, T16/T17 状态（附批次号）, 实测效果或负结果, 备注)
A = {
 "d05-decode-align-481-20261011": ("D05",
   "未测（本轮 T16 候选 1，见 PHASE2_INTEGRATION_PLAN_20261011）",
   "CPU 修复已交付：16 项 CPU 测试通过，复用位置 13,376→13,504（2026-10-11 凌晨主会话/用户结论）；默认关闭",
   "基于 481d3a7 新建，与 D09 分支解耦（D05_D09_FIX_DIRECTIVE 第 64 行裁定）"),
 "d05_hbug_candidate_20261010": ("D05",
   "待核（本树 HEAD=bd57，即 D09 页守恒提交）",
   "无独立实测",
   "D05_D09_FIX_DIRECTIVE 指出此树挂在 bd57 上会让 D05 依赖 D09，已改为基于 481 另建 d05-decode-align-481-20261011；本树不再作 D05 候选"),
 "d09_fix_20261011": ("D09",
   "未测（本轮 T16 候选 2，见 PHASE2_INTEGRATION_PLAN_20261011）",
   "CPU 修复已交付：35 项 CPU 测试及真实回放通过，复用位置 20,160→20,282（2026-10-11 凌晨结论）；默认关闭",
   "包含 bd57（页守恒）"),
 "d09-message-boundary-v1": ("D09",
   "T17 batch153 failed_harness（3 服务 4 调用；热臂 P 边界状态与冷不同）——D09 卡片 07:55 修订记录",
   "候选 c17b69a4 的旧边界方案未过 T17",
   "已被 bd57 页守恒方案取代"),
 "d09-page-conservation-20261010": ("D09",
   "T16 batch163 kept（E2-D09-T16-reapply-bd57-20261010，8 服务 100 调用，8 臂 sequence/h2d 全 SAME，2026-10-10 20:49 独审封存）；T17 batch164 failed_harness（cached-token 期望 20,282 实际 20,160）",
   "T16 通过、T17 未过；T17 缺口即本次 D09 修复（7d8d389e）的动机",
   "现状不干净（3 处改动）；batch163 执行时为洁净状态，本表按现状如实记录"),
 "d10-cache-persistent": ("D10",
   "batch155 完成首个真实 AIPerf 组（1 服务 2 有效请求），资格门 true，判定 NOT_MET——D10 卡片记录",
   "错相位分支已进入但收益未达标",
   ""),
 "d10-eta-481-20261011": ("D10",
   "不适用（HEAD=481d3a7，即基线代码）",
   "D10 η 测量用树；2026-10-11 凌晨 η 工装失败（缓存映射未稳定），无有效 η，不能判断机制",
   "与 release-e2 / e2oom-protocol-restart 同一代码"),
 "d10-staggered-v1": ("D10", "待核", "待核", "不干净（4 处改动）；另有 4 个 d10-staggered-*.bundle 见 bundle 表"),
 "d10-step-metrics-20261010": ("D10", "待核", "待核", "步进指标序列 v1；不干净（1 处改动）"),
 "d10-step-metrics-20261010-v2": ("D10", "待核", "待核", "步进指标序列 v2"),
 "d10-step-metrics-20261010-v3": ("D10", "待核", "待核", "步进指标序列 v3"),
 "d10-step-metrics-20261010-v4": ("D10", "待核", "待核", "步进指标序列 v4"),
 "d10-step-metrics-20261010-v5": ("D10", "待核", "待核", "步进指标序列 v5；不干净（1 处改动）"),
 "d10-step-metrics-20261010-v6": ("D10", "待核", "待核", "步进指标序列 v6"),
 "d10-step-metrics-20261010-v7": ("D10",
   "batch162 clean 测量（2026-10-10 13:06–13:13）：not_met / valid_negative",
   "两路各 512 实际输出，预热 16 步后 495 共同 token/路，95.707 s，每路 5.172 tok/s，未严格 >30；正式负结果，不归因为实现缺陷（D10 卡片终态）",
   "D10 原型阶段已结束"),
 "d15_lag1_cpu_20261010": ("D15", "待核", "待核", "D15 lag-one CPU 适配序列；不包含 481"),
 "d15_lag1_cpu_20261010_76826f8": ("D15", "待核", "待核", "lag-one 修复提交"),
 "d15_lag1_cpu_20261010_7eba574": ("D15", "待核", "待核", "lag-one 测试加固提交"),
 "d15_lag1_cpu_20261010_v2": ("D15", "待核", "待核", ""),
 "d20_short_tail_v1": ("D20", "待核", "待核", "短尾 rewind 几何测试"),
 "e1ms": ("E2 基线", "同 e2base（同 HEAD 23f2e2ca）", "同 e2base", "与 e2base 同提交"),
 "e1r000": ("早期 E1", "待核", "待核", "与 upstream 同提交 3c8f2241"),
 "e1r000b": ("早期 E1", "待核", "待核", ""),
 "e1r001": ("早期 E1", "待核", "待核", ""),
 "e1r001b": ("早期 E1", "待核", "待核", ""),
 "e1r003": ("早期 E1", "待核", "待核", "不干净（3 处改动）"),
 "e1r003sd": ("早期 E1", "待核", "待核", ""),
 "e1r003st": ("D03",
   "T16 E2-R002-gate-D03（候选 c30ae0d7）；T16 R018-gate-D03 以其为父树",
   "T04 R014/R015、T10 R013/R016/R017 工具轮次均以此为代表",
   "D03 状态层工具"),
 "e1r008": ("T03", "T03 E2-R008 切段开关冷热四格（基线为 E2-base）", "待核", ""),
 "e2base": ("D00/E2 基线",
   "作为父树/基线出现在 T16 R002/R021/R022/R041 等门；自身经 T00 E2-R000 立项测量",
   "E2-base@23f2e2c：T03 R008、T04 R002、T08 R009、T10 R006 等多轮基线",
   "第 2 代统一基线"),
 "e2base1": ("D17",
   "无 T16/T17（CPU 复核 PASS：b9 observer CPU/默认关闭范围，协调日志 2026-10-05 19:32）",
   "D17 预集成 observer 树",
   ""),
 "e2base1-ordinary-rewind": ("D17/E2-base.1",
   "T16 E2-R041-gate-D17 候选（warm/cold 控制同列）；R050/R051/R055/R060b/R064 各门的比较基础",
   "前生产基线 E2-base.1@0aa23431；R058 并发显存测量（87K+32K 等三组合）",
   "后被 481d3a7 取代"),
 "e2base1-p1": ("D06",
   "T16 R055a-gate-D06 候选（六冷臂逐位复算通过）；T06 R046a（全程开暂停）",
   "暂停修复测量树 effb996；亦作 R050a/R063 等门的父版本",
   "T20 R040i/R040j 质量轮候选"),
 "e2d03-continuation": ("D03", "T16 E2-R018-gate-D03 候选", "D03 修复候选（Linux 26 PASS 记录于卡片）", ""),
 "e2d06": ("D06", "T16 E2-R024-gate-D07 的父树", "D06 多会话工装候选（交付记录 D06）", ""),
 "e2d07": ("D07", "T16 E2-R024-gate-D07 候选", "路由轨迹导出钩子", ""),
 "e2d07-trace-backpressure": ("D07",
   "T16 E2-R062-gate-D07：候选 4fc2320 对父 151ee718 在 trace/pause 关闭时 T16 通过",
   "T06 E2-R046g 候选（12,660 输入 ID 逐位一致 CPU 回归后启动）",
   ""),
 "e2d07-trace-lm": ("D07",
   "T16 E2-R059-gate-D07 候选；R062 中作为父树",
   "layer-major 预填分块 trace 保留",
   ""),
 "e2d08": ("D08",
   "T16 E2-R051-gate-D08 候选（对父 effb996）；T09 E2-R048/R048a 均 failed_harness",
   "hybrid 任务完成观察候选",
   ""),
 "e2d08-capture-trace": ("D08",
   "T16 E2-R051a（父 effb996 对 76af7584）；T09 E2-R048b batch111 判定 measured（独立 R 确认，D04 封存）",
   "hybrid trace 生命周期采集",
   ""),
 "e2d12-short-suffix": ("D12",
   "T16 E2-R063/R063a（候选 8f6a912e 对父 effb996，4 服务 48 调用，E3 独立分支，独立终审+D04 封存）",
   "短后缀按需搬运（threshold 0）",
   "未合入 481 发布候选"),
 "e2d13-dense-tp": ("D13", "待核（GPU 门待 G0）", "Linux 50 PASS/1 skip（含真实 build_expert_banks TP2/TP4）——开发卡记录", "dense TP 原型"),
 "e2d14": ("D14",
   "T16 E2-R021/R022-gate-D14 候选；T17 R023 及 R025/R027/R029/R030/R031 诊断轮",
   "层优先快照计划与前缀续算修复",
   ""),
 "e2d14-ordinary-rewind": ("D14",
   "T17 E2-R037 kept（R038 记录：retractions=[]）；T17 R038 通过（四类状态逐位一致）",
   "普通 donor rewind 几何保留",
   "亦作 R041 的 warm 控制"),
 "e2d14-schedule": ("D14",
   "T16 E2-R032-gate-D14 候选（T17 R033 的前提门）；T17 R033/R034/R034a/R035（含两轮 failed_harness 修复史）",
   "预填调度回放与等价 reader",
   ""),
 "e2d15": ("D15",
   "T16 E2-R050-gate-D15 候选；T21 R049/R049b/R049c 画像轮（R049b PA1 失败后清理通过）",
   "D15 预算/候选门",
   ""),
 "e2d15-adapt-lag1": ("D15", "T16 E2-R050a-gate-D15 候选（82565530 对父 effb996，四臂 b118）", "自适应 map 发布回滚验证", "与 e2d15-adapt-slot-move 同 HEAD"),
 "e2d15-adapt-slot-move": ("D15", "同 e2d15-adapt-lag1（同 HEAD 82565530）", "同左", ""),
 "e2d15-budget-guard": ("D15", "同 e2d15（同 HEAD 988c9e18）", "同左", "不干净（3 处改动）"),
 "e2d15-core-baseline": ("D15/E2 基线", "同 e2base（同 HEAD 23f2e2ca）", "同 e2base", ""),
 "e2d16-readers": ("D16", "待核", "D16 batch observer / DevPause lookup 交付（协调日志 2026-10-05 20:03）", ""),
 "e2d16-tools": ("D16", "待核", "待核", ""),
 "e2oom-openai-restart": ("OOM",
   "T16 E2-R064-gate-OOM 记录其为 481d3a7 的直接父",
   "openai 路由重启准入修复",
   "自身独立结果待核"),
 "e2oom-protocol-restart": ("OOM", "同 release-e2（同 HEAD 481d3a70）", "同 release-e2", "481 的原始开发树"),
 "e2oom-recovery": ("OOM", "T16 E2-R060b-gate-OOM：608251f0 对 0aa23431，D0 与生产口径全文/分段一致", "OOM 重启就绪超时修复", ""),
 "e2oom-recovery-r061fix": ("OOM", "待核", "待核", "名称指向 R061 修复"),
 "r047-anchor-debug-20261010": ("R047", "待核", "待核", "不干净（7 处改动）"),
 "r067d-retry2-hook": ("D12/R067e",
   "R067e 系列：batch165 pre_gpu_failed（0 服务 0 调用不扣额度，错误信息称 approved 候选 b86190d）；batch166 failed_harness（3 服务/7 派发/6 完成，donor@P 前置哈希不等）",
   "donor 逻辑状态绑定钩子",
   "D12 启用路径冻结中；与 r067e-20261010 同 HEAD"),
 "r067e-20261010": ("D12/R067e", "同 r067d-retry2-hook（同 HEAD b86190d7）", "同左", ""),
 "release-e2": ("发布基线",
   "T16 E2-R064-gate-OOM 候选（对 0aa23431）；OOM-E2-R061f batch122 注入式 OOM 恢复验收 measured 封存（2026-10-09 独审）",
   "当前生产版本：RESTORE481-MORNING-20261011-07 运行中（172.16.108.9:8095）；T20 R065/R066a/b/c SDK 系列均以此为代表",
   "本轮 T16 的父版本与 hybrid 基线"),
 "t03b-rolling64": ("T03b", "待核", "待核", "不干净（3 处改动）"),
 "t03b-uid-source-20261010": ("T03b", "待核", "待核", "不干净（8 处改动）；与 t03b-rolling64 同 HEAD"),
 "upstream": ("上游", "待核", "待核", "上游快照（D3 trace 提交 3c8f2241）；不干净（3 处改动）"),
}

rows = []
with open(os.path.join(ROOT, "version_registry_raw.tsv"), encoding="utf-8") as f:
    for line in f:
        p = line.rstrip("\n").split("\t")
        if len(p) >= 6:
            rows.append(p[:6])

bundles = []
with open(os.path.join(ROOT, "bundle_sha256.txt"), encoding="utf-8") as f:
    for line in f:
        sha, path = line.split()
        bundles.append((os.path.basename(path), sha))

entries = []
for name, head, log, dirty, a481, abd57 in rows:
    card, t16, eff, note = A.get(name, ("待核", "待核", "待核", "未在登记表注释中覆盖"))
    ci = log[:25] if log != "ERROR" else log
    subj = log[26:] if len(log) > 26 else ""
    entries.append({
        "worktree": name, "head": head, "commit_time": ci, "subject": subj,
        "clean": (dirty == "0"), "dirty_lines": int(dirty),
        "contains_481": a481, "contains_bd57": abd57,
        "card": card, "t16_t17": t16, "effect": eff, "note": note,
    })

with open(os.path.join(FT, "development", "VERSION_REGISTRY_20261011.json"), "w", encoding="utf-8") as f:
    json.dump({
        "generated_by": "KIMI phase2 step 1.2",
        "generated_at_local": "见文件系统 mtime；协调日志行为准",
        "source_tsv_sha256": "见 STAGE1_SUMMARY",
        "reference_commits": {
            "481": "481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9",
            "bd57": "bd57cfdccc2a935d46cb0a89b8b36be7a18706de",
        },
        "worktrees": entries,
        "bundles": [{"file": b, "sha256": s} for b, s in bundles],
    }, f, ensure_ascii=False, indent=1)

L = []
L.append("# 版本登记表（2026-10-11，KIMI 阶段 1 步骤 1.2）\n")
L.append("- 数据源：服务器 `/data2/FreeToken/wt/` 现场只读采集（`version_registry_raw.tsv`，63 个工作树）+ 本地 `plan/02_开发任务/`、`plan/COORDINATION_LOG.md`、`plan/01_测试与调研/` 按提交号交叉检索（`version_registry_xref.json`）。")
L.append("- 规则：查不到档案记录的字段写\"待核\"，不推测；不修复、不清理任何工作树。")
L.append("- \"包含 481/bd57\"指对应提交是否为 HEAD 的祖先（merge-base --is-ancestor）。")
L.append("")
L.append("## 0.5 节四个关键版本核对\n")
L.append("| 名称 | 工作树 | 手册预期提交 | 实测 HEAD | 干净 | 含 481 | 含 bd57 | 一致 |")
L.append("|---|---|---|---|---|---|---|---|")
key4 = [
    ("发布版 481", "release-e2", "481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9"),
    ("D05 修复", "d05-decode-align-481-20261011", "730b58c9（前缀）"),
    ("D09 修复", "d09_fix_20261011", "7d8d389e（前缀，应含 bd57）"),
    ("D09 页守恒", "d09-page-conservation-20261010", "bd57cfdccc2a935d46cb0a89b8b36be7a18706de"),
]
byname = {e["worktree"]: e for e in entries}
for label, wt, expect in key4:
    e = byname[wt]
    if "前缀" in expect:
        ok = e["head"].startswith(expect[:8])
    else:
        ok = e["head"] == expect
    if label == "D09 修复":
        ok = ok and e["contains_bd57"] == "yes"
    L.append(f"| {label} | {wt} | {expect} | {e['head']} | {'是' if e['clean'] else '否（' + str(e['dirty_lines']) + ' 处）'} | {e['contains_481']} | {e['contains_bd57']} | {'✅' if ok else '❌'} |")
L.append("")
L.append("结论：4 个版本的提交号均与 0.5 节一致；D09 修复确含 bd57。注意 D09 页守恒树**当前不干净**（3 处改动），batch163 执行时它是干净的，此处按现状记录。")
L.append("")
L.append("## 全量登记表（63 个工作树）\n")
L.append("| 工作树 | HEAD | 提交时间 | 标题 | 干净 | 含481 | 含bd57 | 关联卡片 | T16/T17 状态（批次） | 实测效果/负结果 | 备注 |")
L.append("|---|---|---|---|---|---|---|---|---|---|---|")
for e in entries:
    clean = "是" if e["clean"] else f"否({e['dirty_lines']})"
    row = [e["worktree"], "`" + e["head"][:8] + "`", e["commit_time"], e["subject"].replace("|", "\\|"),
           clean, e["contains_481"], e["contains_bd57"], e["card"],
           e["t16_t17"].replace("|", "\\|"), e["effect"].replace("|", "\\|"), e["note"].replace("|", "\\|")]
    L.append("| " + " | ".join(row) + " |")
L.append("")
L.append("## .bundle 文件（只记文件名与 SHA256）\n")
L.append("| 文件 | SHA256 |")
L.append("|---|---|")
for b, s in bundles:
    L.append(f"| {b} | `{s}` |")
L.append("")
L.append("## 完整 40 位哈希对照\n")
L.append("| 工作树 | HEAD（完整） |")
L.append("|---|---|")
for e in entries:
    L.append(f"| {e['worktree']} | `{e['head']}` |")
L.append("")

with open(os.path.join(FT, "development", "VERSION_REGISTRY_20261011.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(L))

print("entries:", len(entries), "bundles:", len(bundles))
missing = [e["worktree"] for e in entries if e["card"] == "待核" and e["worktree"] not in A]
print("无人工注释（全部待核字段）：", len(missing))
