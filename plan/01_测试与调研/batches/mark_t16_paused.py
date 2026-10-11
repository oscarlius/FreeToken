p = r"freetoken/plan/README.md"
lines = open(p, encoding="utf-8").read().splitlines()
for i, line in enumerate(lines):
    if line.startswith("| T16 |"):
        lines[i] = (
            "| T16 | 暂停（用户要求先做 D02） | "
            "[results/T16-E2-pre-gate-D01_20261004.md](01_测试与调研/results/T16-E2-pre-gate-D01_20261004.md) | "
            "PARENT 臂已跑完；NEW 臂加载中被停。目录未关闭 |"
        )
open(p, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
print("ok")
