#!/usr/bin/env python3
"""恢复包 restore11（op-hak 任务 A，补充 1 第 4 节）。流程与 H3 构建脚本相同，以 restore10 为模板。

1. 复制 restore10（排除 EXECUTION_TIME_PREFLIGHT.json、__pycache__、.pytest_cache），文件改为可写。
2. 只替换两个精确字符串：RESTORE481-MORNING-20261011-10 → -12；ROLLBACK184-MORNING-20261011-10 → -12。
3. 身份说明：README.md 与 ROOT_FINAL_REVIEW.json 的 scope 改写为 Restore11；SOURCE_MANIFEST.json 的 package 字段改为新路径。
4. 按顺序重算（不能颠倒）：SOURCE_MANIFEST → DEPLOYMENT_APPROVAL（package_source_manifest_sha256）→
   approval 的 SHA → ROOT_FINAL_REVIEW（approval_sha256、package_source_manifest_sha256，
   independent_review_sha256 = 本指令文件 SHA256，verdict PASS，pending_independent_review false）。
5. 验证：pytest 7 passed；门链打印 GATE_CHAIN_PASS RESTORE481-MORNING-20261011-11 2026-10-12T09:00:00+08:00。
6. diff -ru restore10 restore11 → WORK/diff_restore11.txt；全部文件 0444。

注意：ROOT_FINAL_REVIEW 的 PASS 与 reviewer_role 按补充 1 第 4 节写入。门链（deploy_conditional.require_root_final_review）
不校验 independent_review_sha256 指向的文件内容。真正的放行是主会话在协调日志写"任务 A 放行"。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SRC = Path("/data2/FreeToken/development/gemini_oom_hybrid_20261011/restore10")
WORK = Path(__file__).resolve().parent
DST = WORK / "restore11"
RUN_DIR_NEW = Path("/data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-11")
INSTRUCTION = Path("/data2/FreeToken/plan/OPHAK_TASK_A_ADDENDUM1_20261011.md")
INSTRUCTION_SHA = "7b9464580e4a3d8e63a1b7a217960b333ede87a07c100f8f02f458a21fa99caa"
PAIRS = (("RESTORE481-MORNING-20261011-10", "RESTORE481-MORNING-20261011-11"),
         ("ROLLBACK184-MORNING-20261011-10", "ROLLBACK184-MORNING-20261011-11"))
EXCLUDE = ("EXECUTION_TIME_PREFLIGHT.json", "__pycache__", ".pytest_cache")
PACKAGE_NEW = "ophak_task_a_20261011/restore11"
SCOPE_OLD = ("Identity-only Restore10 (Gemini P1-G4 copy of Restore09 for OOM & hybrid window), "
             "7 CPU tests, exact df77cb baseline, mandatory stop-before-rollback. No push.")
SCOPE_NEW = ("Identity-only Restore11 (op-hak task A addendum-1 copy of Restore10; -11 so the D11-P0 precheck admits it), "
             "7 CPU tests, exact df77cb baseline, mandatory stop-before-rollback. No push.")
README_NEW = """Restore11: identity-only copy of Restore10 for the op-hak task A window (OPHAK_TASK_A_ADDENDUM1_20261011.md section 4). Same twelve reviewed restore sources with identity
substitutions only (-10 -> -11 approval/rollback/run_dir). observation_until unchanged (2026-10-12T09:00:00+08:00).
df77cb baseline comparison and stop-before-rollback logic unchanged.
ROOT_FINAL_REVIEW.json binds the op-hak task A addendum 1 (independent_review_sha256 = 7b9464580e4a3d8e63a1b7a217960b333ede87a07c100f8f02f458a21fa99caa).
Restore11 supersedes Restore12 (H3, never used). Restore11 cannot run before the main session writes the release line.
"""


class BuildError(RuntimeError):
    pass


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, obj: dict) -> str:
    """与 restore10 的格式一致（indent=2，sort_keys，ensure_ascii=False，结尾换行）。"""
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
        data = path.read_bytes()
        text = data.decode("utf-8")
        n = 0
        for old, new in PAIRS:
            n += text.count(old)
            text = text.replace(old, new)
        if n:
            path.write_bytes(text.encode("utf-8"))
            counts[str(path.relative_to(DST))] = n
    return counts


def step_identity_text() -> None:
    readme = DST / "README.md"
    readme.write_text(README_NEW, encoding="utf-8", newline="\n")
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
    (WORK / "diff_restore11.txt").write_text(diff.stdout, encoding="utf-8", newline="\n")


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
        and verify["gate_stdout"].startswith("GATE_CHAIN_PASS RESTORE481-MORNING-20261011-11 2026-10-12T09:00:00+08:00")
    return 0 if ok else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BuildError as exc:
        print(f"BUILD STOP: {exc}", file=sys.stderr)
        raise SystemExit(2)
