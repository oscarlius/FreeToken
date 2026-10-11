p = r"freetoken/plan/README.md"
lines = open(p, encoding="utf-8").read().splitlines()
for i, line in enumerate(lines):
    if line.startswith("| T11 |"):
        lines[i] = (
            "| T11 | 阶段 1 完成；阶段 2 阻塞（待 E2-base） | "
            "[results/T11-S-006_20261003.md](01_测试与调研/results/T11-S-006_20261003.md) | "
            "唯一短续算是 uid=8，按卡进入阶段 2 |"
        )
    if line.startswith("| Q1 |"):
        lines[i] = (
            "| Q1 | 2026-10-03 23:10 复查 `/data2/_shared/gpu.lock` 已不存在。"
            "先前记录的 `E1-R002-prep` 锁不再挡住 GPU 卡。GPU 卡仍等 E2-base 过门 | "
            "锁消失一事请总负责人确认是否为预期 |"
        )
open(p, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
print("updated")
