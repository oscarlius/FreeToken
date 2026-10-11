"""Synchronize current delivery documents after the sealed independent review.

This only edits documentation and the mutable release proposal. It never edits
sealed evidence, model data, product code, or operational approval flags.
"""
from pathlib import Path
import hashlib
import json
from datetime import datetime, timezone, timedelta

FT = Path(__file__).resolve().parents[1]
DEV = FT / "development"
REVIEW = "FTD-20261009-1_AND_PAPER_V5_REVIEW_20261009_v1.json"
REVIEW_SHA = "16bea91f531c1fc65805578f405aa1acb020b37c2826c5cc3f34a4e2ba380ba3"
FTD_SHA = "cff4e114ba6f661878a601f353756dc0367d478dda487787e32f8ec64cd95840"
HTML_SHA = "2e2b3c726b94107dde542f091ee0a31c694b5c3ccf6f73aa7d1504e71cadfa0d"
STAMP = datetime.now(timezone(timedelta(hours=8))).isoformat()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, text):
    path.write_text(text, encoding="utf-8", newline="\n")


def replace_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new, 1)


assert digest(DEV / REVIEW) == REVIEW_SHA
review = json.loads((DEV / REVIEW).read_text(encoding="utf-8"))
assert review["verdict"] == review["data_verdict"] == review["paper_verdict"] == "PASS"
assert digest(FT / "plan/data_releases/FTD-20261009-1.json") == FTD_SHA
assert digest(FT / "paper/FreeToken_MultiGPU_CoExec_v5.0.html") == HTML_SHA

proof = (
    f"\n\n最终独立复核已封存 **数据 PASS / 论文 PASS**：[{REVIEW}]({REVIEW})，"
    f"SHA256 `{REVIEW_SHA}`，远端0444、本地同字节只读。浏览器验证使用"
    "[最终v3回执](paper_v5_validation_20261009_v3/render_validation.json)；"
    "独立R复核该回执及绑定，未另行运行浏览器。复核通过仅适用于数据和论文交付，"
    "不授予建分支、部署或推送权限。\n"
)
proposal_path = DEV / "RELEASE_PROPOSAL_E2_20261009.md"
proposal = proposal_path.read_text(encoding="utf-8")
proposal = replace_once(proposal, "最终产物独立复核收尾中", "最终产物独立复核已封存PASS")
proposal = replace_once(proposal, "10:36原快照、12:24闭门后再次只读核验", "10:36原快照、12:24闭门后及12:32:57最终只读核验")
proposal += proof
proposal += (
    "\n## Strata后续范围（未批准）\n\n"
    "发布门已闭合，现重新报告[准备包](../../strata/r002_prepare/README.md)及"
    "[v3具体范围](../../strata/r002_prepare/r002_execution_scope_v3.json)："
    "F、S1各5服务/105调用，S2、S3、S4各4服务/45调用，合计**22服务/345调用**。"
    "仅F/S1含quality60；S2/S3/S4仅performance45。`approved=false`，未执行该范围GPU验收；"
    "执行环境、真实端点与cold/cache证据仍待准备和准入，不将静态输入包视为可执行验收。\n"
)
write(proposal_path, proposal)

audit_path = DEV / "RELEASE_GATE_EVIDENCE_AUDIT_20261009.md"
audit = audit_path.read_text(encoding="utf-8")
audit = replace_once(audit, "已关闭；FTD/v5 最终审阅待完成", "已关闭；FTD已发布，v5独立终审PASS")
audit = replace_once(audit, "## 5. 未完成的外部状态", "## 5. 已完成交付与待批准操作")
audit = replace_once(
    audit,
    "`data_release_published=false`。待根节点写入 FTD manifest 最终绑定后，仍须完成 FTD/v5 最终审阅；分支创建、部署、推送也分别需要独立批准。",
    "`data_release_published=true`。FTD manifest已只读发布，论文v5最终构建及独立复核已完成。分支创建、部署、推送分别待批准，均未执行；Strata22服务/345调用仍未批准。",
)
write(audit_path, audit + proof)

candidate_path = FT / "plan/data_releases/E2_RELEASE_CANDIDATE_DRAFT_20261009.json"
candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
assert not any(candidate["activation"].values())
candidate["status"] = "release_gate_closed_FTD_published_paper_v5_reviewed_ready_three_operations_pending"
candidate["updated_at"] = STAMP
candidate["release_scope"]["remaining"] = ["branch approval", "deployment approval", "push approval"]
candidate["remaining"] = list(candidate["release_scope"]["remaining"])
candidate["code"]["live_readonly_verification"] = "2026-10-09 12:32:57 CST; candidate and rollback exact HEAD, both tracked clean"
candidate["branch_proposal"]["branch_and_worktree_absent_verified"] = "2026-10-09 12:32:57 CST"
candidate["proposed_runtime_entry"]["port_readonly_check"] = "2026-10-09 12:32:57 CST; 8095/8096 no LISTEN, no compute applications; recheck at execution"
candidate["downstream"].update({
    "FTD_and_paper": "FTD published read-only and paper v5 built/rendered; final independent data/paper PASS sealed",
    "R063": "R063 failed_harness preserved; R063a kept, E3 only, not a release gate",
    "all_GPU": "Authorized R066c completed 3 services/5 calls and D04 closed; no further GPU scheduled; Strata22/345 unapproved",
    "paper_final_independent_review": "PASS",
    "data_final_independent_review": "PASS",
    "final_review_path": "development/" + REVIEW,
    "final_review_server_path": "/data2/FreeToken/runs/dev_D16/" + REVIEW,
    "final_review_sha256": REVIEW_SHA,
})
candidate["accept_evidence"]["D16_R066c"] = {
    "report": "plan/01_测试与调研/results/T20-E2-R066c_20261009.md",
    "classification": "c",
    "grammar_anomalous_replies": 5,
    "root_D04_receipt": "development/r066c_b131_d04_closure_v1.json",
    "root_D04_receipt_sha256": "0ae04c2f120e2d9cff32479ac7688860764c03d7576bd85150733d1405bca220",
    "scope": "No product-failure marker observed; standalone cold grammar anomalies also occur. No universal task-compliance or concurrency claim.",
}
assert not any(candidate["activation"].values())
write(candidate_path, json.dumps(candidate, ensure_ascii=False, indent=2) + "\n")

readme_path = FT / "README.md"
readme = readme_path.read_text(encoding="utf-8")
title, history = readme.split("\n", 1)
current = (
    "\n\n## 当前交付（2026-10-09，最终复核完成）\n\n"
    "候选481d3a7的发布门已闭合。R066c实际3服务/5调用均为字面文法异常，单独冷请求同样异常，"
    "按11:45逐提示分类归c；未观察到对方完整口令、U+FFFD或非法控制字符。"
    "[五行结果及SHA对照](plan/01_测试与调研/results/T20-E2-R066c_20261009.md)与D04已封存，"
    "旧not_met/failed_harness保持；R063a kept只归E3。\n\n"
    f"[FTD-20261009-1](plan/data_releases/FTD-20261009-1.json)已服务器只读发布（SHA256 `{FTD_SHA}`）。"
    f"[论文v5全文](paper/FreeToken_MultiGPU_CoExec_v5.0.html)已完成（SHA256 `{HTML_SHA}`），"
    "原v4及源码保留，11图18表，桌面与窄屏渲染通过。"
    f"[独立数据/论文终审](development/{REVIEW})均PASS（SHA256 `{REVIEW_SHA}`）。\n\n"
    "T17的逐位等价证据覆盖现算尾段≥65 token；≤64（含1 token）走不写检查点的分支，正确性待证。"
    "论文§10拆为冷可复现/热与同结构冷参照一致/并发不保证，并新增已知限制。"
    "[发布方案](development/RELEASE_PROPOSAL_E2_20261009.md)含候选链、回滚、完整启动命令；"
    "建分支、部署、推送分别待批且未执行。Strata22服务/345调用未批准，"
    "[具体范围](../strata/r002_prepare/README.md)已重新报告。\n\n"
    "## 以下为历史状态（均由上方最终状态更新）\n"
)
write(readme_path, title + current + history)

summary_path = FT / "plan/MORNING_SUMMARY_20261009.md"
summary = summary_path.read_text(encoding="utf-8")
current_summary = (
    "# 当前进展摘要（2026-10-09，FTD/v5最终复核完成）\n\n"
    "| 类别 | 最终状态 |\n| --- | --- |\n"
    "| 发布门 | 481d3a7已闭合；T17、R041、OOM默认门/恢复及T20保留主体/补充证据绑定。R066c分类c并D04关闭。 |\n"
    "| R066c | 3服务/5调用均文法异常，单独冷请求也异常；无对方完整口令、U+FFFD、非法控制字符。Z两SHA与旧R066b第一对相同，仅观察，不作判据。 |\n"
    "| 已交付 | FTD-20261009-1服务器只读发布；v5完整源码构建、11图18表、桌面/窄屏验证通过；独立数据/论文终审均PASS。 |\n"
    "| 历史失败 | R040等原failed_harness、R040j/R065/R066a原not_met保持。R063 failed_harness保持；R063a kept只归E3。 |\n"
    "| 待批准 | 建release/e2、部署、推送三项分别待批，均未执行；Strata22服务/345调用仍未批准。 |\n\n"
    "**边界：**现算尾段≤64（含1）未与同结构冷参照逐位比对，正确性待证；T17证据覆盖已测≥65。"
    "分类c不证明普遍任务合规或任意并发正确性。\n\n"
    "**实验占用区间：**此前约200分钟，加R066c11:50:34.490800—12:03:41.772213约13分7秒，"
    "累计约213分钟（均含加载/测量/清理，非kernel忙时）。独立复核、封存与口径等待空档不计；"
    "GPU计算进程已清空，12:32:57只读复验候选/回滚tracked-clean、release分支/工作树不存在、8095/8096无监听。\n\n"
    "交付：[发布方案](../development/RELEASE_PROPOSAL_E2_20261009.md)、"
    "[R066c五行表](01_测试与调研/results/T20-E2-R066c_20261009.md)、"
    "[FTD](data_releases/FTD-20261009-1.json)、[v5全文](../paper/FreeToken_MultiGPU_CoExec_v5.0.html)、"
    f"[独立终审](../development/{REVIEW})。\n\n"
    "以下为历史快照；过去的在途、未生成或待审状态由上表更新。\n\n"
)
write(summary_path, current_summary + summary)

coord_path = FT / "plan/COORDINATION_LOG.md"
coord = coord_path.read_text(encoding="utf-8")
coord += (
    "\n\n### 2026-10-09 R066c终态、发布门闭合与FTD/v5最终交付\n\n"
    "R066c/b131实际3/5，五条均literal grammar anomaly，无other完整口令/U+FFFD/非法control，"
    "单独冷请求也异常，按11:45分类c；Z两SHA与R066b第一对相等仅记录。独立终审+D04已完成，"
    "50原件未改；测量11:50:34.490800—12:03:41.772213，D04关闭12:07:44.643764。"
    "root门closure v2 SHA7c2309bd1591bfe57163e7fcb1d2a5e2d3d504230a20fcb9c11f8f602f5ae006；"
    "R063a kept仅E3，原失败判词保留。\n\n"
    f"FTD只读发布 SHA{FTD_SHA}，论文v5 SHA{HTML_SHA}，最终v3桌面/窄屏回执通过；"
    f"独立数据/论文终审均PASS，[{REVIEW}](../development/{REVIEW}) SHA{REVIEW_SHA}。"
    "≤64热路径正确性待证，原v4/FTD03/04/erratum及旧轮证据保留。"
    "12:32:57只读回验候选/回滚tracked-clean、release/e2 ref与worktree不存在、8095/8096无监听、GPU无计算进程。"
    "分支/部署/推送分别待批且未执行；Strata22/345只报告具体范围，不启动。\n"
)
write(coord_path, coord)

print(json.dumps({"updated_at": STAMP, "review_sha256": REVIEW_SHA, "updated_files": [
    str(p.relative_to(FT)) for p in (proposal_path, audit_path, candidate_path, readme_path, summary_path, coord_path)
]}, ensure_ascii=False, indent=2))
