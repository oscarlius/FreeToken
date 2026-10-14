#!/usr/bin/env python3
"""任务 B 恢复包 restore13（op-hak，CPU）。流程与 build_restore12.py 相同，只换模板与身份：

1. 以 restore12 为模板复制（排除 EXECUTION_TIME_PREFLIGHT.json、__pycache__、.pytest_cache），文件改为可写。
2. 只替换两个精确字符串：RESTORE481-MORNING-20261011-12 → -13；ROLLBACK184-MORNING-20261011-12 → -13。
3. 身份说明：README.md 与 ROOT_FINAL_REVIEW.json 的 scope 改写为 Restore13；SOURCE_MANIFEST.json 的 package 字段改为新路径。
4. 按顺序重算（不能颠倒）：SOURCE_MANIFEST → DEPLOYMENT_APPROVAL（package_source_manifest_sha256）→ approval 的 SHA →
   ROOT_FINAL_REVIEW（approval_sha256、package_source_manifest_sha256，independent_review_sha256 = 任务 B 指令文件 SHA256，
   verdict PASS，pending_independent_review false）。
5. 验证：pytest 7 passed；门链打印 GATE_CHAIN_PASS RESTORE481-MORNING-20261011-13 2026-10-12T09:00:00+08:00。
6. diff -ru restore12 restore13 → WORK/diff_restore13.txt；全部文件 0444。

恢复的仍是 release-e2（481d3a7），不是候选。真正的放行是主会话在协调日志写"任务 B 放行"。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SRC = Path("/data2/FreeToken/development/ophak_task_a_20261011/restore12")
WORK = Path(__file__).resolve().parent
DST = WORK / "restore13"
RUN_DIR_NEW = Path("/data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-13")
INSTRUCTION = Path("/data2/FreeToken/plan/OPHAK_TASK_B_CUT_POLICY_20261011.md")
INSTRUCTION_SHA = "64394da69f58c2b9f4f9aa169e3883f243991a3e12efab2411cfe3070cdb4186"
PAIRS = (("RESTORE481-MORNING-20261011-12", "RESTORE481-MORNING-20261011-13"),
         ("ROLLBACK184-MORNING-20261011-12", "ROLLBACK184-MORNING-20261011-13"))
EXCLUDE = ("EXECUTION_TIME_PREFLIGHT.json", "__pycache__", ".pytest_cache")
PACKAGE_NEW = "ophak_task_b_20261011/restore13"
SCOPE_OLD = ("Identity-only Restore12 (op-hak task A H3 copy of Restore10 for the anchor-cut window), "
             "7 CPU tests, exact df77cb baseline, mandatory stop-before-rollback. No push.")
SCOPE_NEW = ("Identity-only Restore13 (op-hak task B copy of Restore12 for the min-tokens cut window), "
             "7 CPU tests, exact df77cb baseline, mandatory stop-before-rollback. No push.")
README_NEW = """Restore13: identity-only copy of Restore12 for the op-hak task B window (OPHAK_TASK_B_CUT_POLICY_20261011.md §4.2).
Same restore sources with identity substitutions only (-12 -> -13 approval/rollback/run_dir).
The restored build is release-e2 (481d3a7), not the candidate. observation_until unchanged (2026-10-12T09:00:00+08:00).
ROOT_FINAL_REVIEW.json binds the op-hak task B directive (independent_review_sha256 = 64394da69f58c2b9f4f9aa169e3883f243991a3e12efab2411cfe3070cdb4186).
Restore13 cannot run before the main session writes "任务 B 放行" in the coordination log.
"""


# freetoken-06 裁定（2026-10-12 凌晨）：user_authority 按此英文照录。其中 "user instruction 2026-10-12 00:50" 一句
# 是主会话在协调消息中转述的用户指示；op-hak 未直接见到该用户指示，授权表述由主会话负责。
NEW_AUTHORITY = ("User-confirmed OPHAK_TASK_B_CUT_POLICY_20261011.md (sha256 64394da69f58c2b9f4f9aa169e3883f243991a3e12efab2411cfe3070cdb4186) "
                 "GPU window: stop 481, run R0/C_A1/C_B1/C_B2/C_A2 (candidate m1/cut-min-tokens 9db0ee77, never deployed to production), "
                 "restore 481 to release-e2 481d3a7; user instruction 2026-10-12 00:50 'task B continue'; "
                 "main-session written release (COORDINATION_LOG '任务 B 放行') required before the window; no push; Ollama stays stopped.")


class BuildError(RuntimeError):
    pass


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, obj: dict) -> str:
    """与 restore12 的格式一致（indent=2，sort_keys，ensure_ascii=False，结尾换行）。"""
    data = (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def step_copy() -> None:
    if RUN_DIR_NEW.exists():
        raise BuildError(f"运行目录已存在：{RUN_DIR_NEW}")
    if INSTRUCTION_SHA != sha(INSTRUCTION):
        raise BuildError("指令文件 SHA 与本脚本内的常量不符")
    if DST.exists():
        raise BuildError(f"{DST} 已存在，不覆盖")
    shutil.copytree(SRC, DST, ignore=shutil.ignore_patterns(*EXCLUDE))
    for path in DST.rglob("*"):
        if path.is_file():
            os.chmod(path, 0o644)


def step_replace() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in sorted(DST.rglob("*")):
        if not path.is_file():
            continue
        text = path.read_bytes().decode("utf-8")
        n = 0
        for old, new in PAIRS:
            n += text.count(old)
            text = text.replace(old, new)
        if n:
            path.write_bytes(text.encode("utf-8"))
            counts[str(path.relative_to(DST))] = n
    return counts


def step_identity_text() -> None:
    (DST / "README.md").write_text(README_NEW, encoding="utf-8", newline="\n")
    review = json.loads((DST / "ROOT_FINAL_REVIEW.json").read_text(encoding="utf-8"))
    if review["scope"] != SCOPE_OLD:
        raise BuildError("ROOT_FINAL_REVIEW.json 的 scope 与模板不符，停止")
    review["scope"] = SCOPE_NEW
    dump(DST / "ROOT_FINAL_REVIEW.json", review)


def step_recompute() -> dict[str, str]:
    manifest_path = DST / "SOURCE_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["package"] = PACKAGE_NEW
    for name in manifest["files"]:
        manifest["files"][name] = sha(DST / name)
    manifest_sha = dump(manifest_path, manifest)

    approval_path = DST / "DEPLOYMENT_APPROVAL.json"
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["package_source_manifest_sha256"] = manifest_sha
    approval["user_authority"] = NEW_AUTHORITY
    approval_sha = dump(approval_path, approval)

    review_path = DST / "ROOT_FINAL_REVIEW.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review.update({
        "approval_id": approval["approval_id"],
        "approval_sha256": approval_sha,
        "independent_review_sha256": INSTRUCTION_SHA,
        "package_source_manifest_sha256": manifest_sha,
        "pending_independent_review": False,
        "reviewer_role": "root_independent_final_reviewer",
        "verdict": "PASS",
    })
    dump(review_path, review)
    return {"manifest": manifest_sha, "approval": approval_sha}


def run(cmd: list[str], env_extra: dict[str, str]) -> subprocess.CompletedProcess:
    env = dict(os.environ, **env_extra)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(cmd, cwd=DST, env=env, capture_output=True, text=True, timeout=600)


def step_verify() -> dict[str, str]:
    py = "/data2/FreeToken/venv/bin/python"
    tests = run(["taskset", "-c", "0,2", py, "-B", "-m", "pytest", "test_cpu_orchestration.py", "-q",
                 "-p", "no:cacheprovider"], {"CUDA_VISIBLE_DEVICES": ""})
    tail = (tests.stdout.strip().splitlines() or [""])[-1]
    gate = run([py, "-B", "-c",
                "import approved_attempt as a; d=a.load(); "
                "print('GATE_CHAIN_PASS', d['approval_id'], d['observation_until'])"],
               {"CUDA_VISIBLE_DEVICES": ""})
    return {"pytest_rc": str(tests.returncode), "pytest_tail": tail,
            "gate_rc": str(gate.returncode), "gate_stdout": gate.stdout.strip(), "gate_stderr": gate.stderr[-400:]}


def step_diff() -> None:
    diff = subprocess.run(["diff", "-ru", str(SRC), str(DST)], capture_output=True, text=True)
    (WORK / "diff_restore13.txt").write_text(diff.stdout, encoding="utf-8", newline="\n")


def step_seal() -> None:
    for cache in DST.rglob("__pycache__"):
        shutil.rmtree(cache)
    for cache in DST.rglob(".pytest_cache"):
        shutil.rmtree(cache)
    for path in DST.rglob("*"):
        if path.is_file():
            os.chmod(path, 0o444)


def main() -> int:
    step_copy()
    counts = step_replace()
    step_identity_text()
    hashes = step_recompute()
    verify = step_verify()
    step_diff()
    step_seal()
    print(json.dumps({"replacements": counts, "hashes": hashes, "verify": verify}, ensure_ascii=False, indent=1))
    ok = verify["pytest_rc"] == "0" and "7 passed" in verify["pytest_tail"] and verify["gate_rc"] == "0" \
        and verify["gate_stdout"].startswith("GATE_CHAIN_PASS RESTORE481-MORNING-20261011-13 2026-10-12T09:00:00+08:00")
    return 0 if ok else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BuildError as exc:
        print(f"BUILD STOP: {exc}", file=sys.stderr)
        raise SystemExit(2)
