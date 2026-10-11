"""Build the v5.7 revision (hybrid W4A8 correction, code-research evidence in §8.4), reusing the frozen v5.1 figures and layout."""
from pathlib import Path
import re

import build_v51 as base

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "FreeToken_MultiGPU_CoExec_v5.7.html"


def main():
    body = (HERE / "body_v57.html").read_text(encoding="utf-8")
    used = set()

    def substitute(match):
        key = match.group(1)
        if key not in base.figures.V5:
            raise SystemExit(f"Unknown figure: {key}")
        used.add(key)
        return base.figures.V5[key]()

    body = re.sub(r"<!--FIG:([a-z0-9]+)-->", substitute, body)
    if used != set(base.figures.V5):
        raise SystemExit("Figure registry mismatch")
    body = re.sub(r'(<table class="booktabs[^\"]*">.*?</table>)',
                  r'<div class="table-wrap">\1</div>', body, flags=re.S)
    tail = base.TAIL.replace("build_v51.py", "build_v57.py").replace("body_v51.html", "body_v57.html")
    tail = tail.replace("；配图坐标由数据直接计算。", "；配图坐标由数据直接计算。2026-10-10 轮次名单见附录 A.5（FTD-20261010-1 草案，待服务器清单封存）。")
    head = base.HEAD.replace("（v5.1，数据版本 FTD-20261009-1）", "（v5.7，数据版本 FTD-20261009-1＋附录A.5）")
    OUT.write_text(head + body + tail, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
