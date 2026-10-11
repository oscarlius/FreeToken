p = r"freetoken/plan/README.md"
lines = open(p, encoding="utf-8").read().splitlines()
for i, line in enumerate(lines):
    if line.startswith("| T16 |"):
        lines[i] = (
            "| T16 | 进行中（E2-pre-gate-D01） | — | "
            "D01 验收；父树 3db7b50，新树 f91054b；batch20 |"
        )
    if line.startswith("| D01 |"):
        lines[i] = (
            "| D01 | 已交付，待 01 验证 | "
            "[D00-D01_交付记录_20261003.md](02_开发任务/D00-D01_交付记录_20261003.md) | "
            "f91054b；T16 轮次 E2-pre-gate-D01 |"
        )
    if line.startswith("| D00 |"):
        lines[i] = (
            "| D00 | 前置已验证，待 D02 | "
            "[D00-D01_交付记录_20261003.md](02_开发任务/D00-D01_交付记录_20261003.md) | "
            "E2-pre@3db7b50；最终 E2-base 未打 |"
        )
open(p, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
print("ok")
