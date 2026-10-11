p = r"freetoken/plan/README.md"
lines = open(p, encoding="utf-8").read().splitlines()
repl = {
    "| T04 |": "| T04 | 阻塞（待 E2-base 过门）；阶段 2 另待 D03 | — | 2026-10-03 23:12 服务器只有标签 E2-pre，无 E2-base；锁不在、8095 空闲 |",
    "| T07 |": "| T07 | 阻塞（待 E2-base 过门） | — | 同上 |",
    "| T08 |": "| T08 | 阻塞（待 E2-base 过门） | — | 两路子项仍待 D06 |",
    "| T09 |": "| T09 | 阻塞（待 E2-base 过门） | — | 分解仍待 D08 |",
    "| T10 |": "| T10 | 阻塞（待 E2-base 过门）；阶段 2 另待 D03 | — | 同上 |",
}
for i, line in enumerate(lines):
    for key, new in repl.items():
        if line.startswith(key):
            lines[i] = new
open(p, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
print("ok")
