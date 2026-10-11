"""Build the v5.3 revision (decode targets from the cost model), reusing the frozen v5.1 figures and layout."""
from pathlib import Path
import re

import build_v51 as base

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "FreeToken_MultiGPU_CoExec_v5.3.html"


def main():
    body = (HERE / "body_v53.html").read_text(encoding="utf-8")
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
    tail = base.TAIL.replace("build_v51.py", "build_v53.py").replace("body_v51.html", "body_v53.html")
    tail = tail.replace("；配图坐标由数据直接计算。", "；配图坐标由数据直接计算。R045为本版§8新增独立证据，不在原FTD清单内。")
    head = base.HEAD.replace("（v5.1，数据版本 FTD-20261009-1）", "（v5.3，数据版本 FTD-20261009-1）")
    OUT.write_text(head + body + tail, encoding="utf-8", newline="\n")
    print(f"Built {OUT}; {len(used)} figures")


if __name__ == "__main__":
    main()
