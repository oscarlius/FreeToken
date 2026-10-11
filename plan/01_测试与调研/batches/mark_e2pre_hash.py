p = r"freetoken/plan/02_开发任务/README.md"
text = open(p, encoding="utf-8").read()
old = "| **第 2 代统一基线** | `e2/base` | 标签 `E2-pre` → `E2-base` |"
new = "| **第 2 代统一基线** | `e2/base` | 标签 `E2-pre`@`3db7b50`，`E2-base` 未打 |"
if old not in text:
    raise SystemExit("row not found")
text = text.replace(old, new, 1)
open(p, "w", encoding="utf-8", newline="\n").write(text)
print("ok")
