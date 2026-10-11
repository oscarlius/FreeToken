"""生成论文 v5.0 的单文件 HTML：python paper/src/build_v5.py

正文在 body_v5.html，配图由 figures.py 生成并替换 <!--FIG:名称--> 占位。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import figures  # noqa: E402

OUT = os.path.join(HERE, "..", "FreeToken_MultiGPU_CoExec_v5.0.html")

HEAD = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>主存卸载 MoE 多 GPU 协同执行</title>
<meta name="description" content="共享资源约束下主存卸载 MoE 的多 GPU 低延迟协同执行（v5.0，数据版本 FTD-20261009-1）">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;700&display=swap">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/KaTeX/0.16.9/katex.min.css" integrity="sha384-n8MVd4RsNIU0tAv4ct0nTaAbDJwPJzDEaqSD1odI+WdtXRGWt2kTvGFasHpSy3SV" crossorigin="anonymous">
<script defer src="https://cdnjs.cloudflare.com/ajax/libs/KaTeX/0.16.9/katex.min.js" integrity="sha384-XjKyOOlGwcjNTAIQHIpgOno0Hl1YQqzUOEleOLALmuqehneUG+vnGctmUb0ZY0l8" crossorigin="anonymous"></script>
<script defer src="https://cdnjs.cloudflare.com/ajax/libs/KaTeX/0.16.9/contrib/auto-render.min.js" integrity="sha384-+VBxd3r6XgURycqtZ117nYw44OOcIax56Z4dCRWbxyPt0Koah1uHoK0o4+/RRE05" crossorigin="anonymous"
  onload="renderMathInElement(document.body,{delimiters:[{left:'$$',right:'$$',display:true},{left:'$',right:'$',display:false}],throwOnError:false})"></script>
<style>
:root{
  --ink:#1a1a19; --ink-2:#52514e; --muted:#6b6a65; --rule:#1a1a19; --hair:#d9d8d3;
  --paper:#ffffff; --soft:#f6f5f1; --accent:#2a78d6;
}
*{box-sizing:border-box}
html{background:var(--paper)}
body{margin:0;background:var(--paper);color:var(--ink);
  font-family:"Noto Serif SC","Source Han Serif SC","Songti SC","SimSun",serif;
  font-size:16px;line-height:1.78;-webkit-font-smoothing:antialiased}
main{max-width:860px;margin:0 auto;padding:40px 16px 80px}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.title-block{text-align:center;margin-bottom:28px}
.title-block p{text-align:center}
.preprint{font-size:12px;letter-spacing:.06em;color:var(--muted);border-bottom:1px solid var(--hair);padding-bottom:10px;margin-bottom:26px}
h1{font-size:26px;line-height:1.4;margin:0 0 10px;font-weight:700}
.subtitle{font-size:17px;font-weight:400;margin:0 0 10px;color:var(--ink-2)}
.en-title{font-size:14px;font-style:italic;color:var(--muted);margin:0 0 16px;line-height:1.5}
.authors{font-size:15px;margin:0}
.affil{font-size:13px;color:var(--muted);margin:2px 0 0}
.abstract{margin:18px 40px;font-size:15px;line-height:1.72;text-align:justify}
.abstract h2{text-align:center;font-size:15px;letter-spacing:.2em;margin:0 0 8px;border:none}
.abstract.en{font-family:"Times New Roman",Georgia,serif;font-size:14.5px}
.keywords{font-size:14px;color:var(--ink-2)}
.toc{margin:24px 40px;padding:12px 20px;background:var(--soft);border-radius:4px;font-size:14px}
.toc h2{font-size:14px;margin:0 0 4px;border:none}
.toc ol{margin:0;padding-left:22px;columns:2;column-gap:32px}
section{margin-top:34px}
section > h2{font-size:19px;margin:0 0 12px;padding-bottom:4px;border-bottom:1px solid var(--hair)}
h3{font-size:16px;margin:24px 0 8px}
p{margin:10px 0;text-align:justify}
ul,ol{padding-left:24px}
li{margin:4px 0}
code{font-family:"JetBrains Mono",Consolas,monospace;font-size:13px;background:var(--soft);padding:1px 4px;border-radius:3px}
pre{font-family:"JetBrains Mono",Consolas,monospace;font-size:12.5px;background:var(--soft);padding:12px 14px;border-radius:4px;overflow-x:auto;line-height:1.5}
table.booktabs{border-collapse:collapse;width:100%;margin:16px 0 20px;font-size:14px;line-height:1.55;border-top:2px solid var(--rule);border-bottom:2px solid var(--rule)}
table.booktabs caption{caption-side:top;text-align:left;font-size:14px;padding:0 0 6px;font-weight:700}
table.booktabs thead th{border-bottom:1px solid var(--rule);text-align:left;padding:6px 8px;font-weight:700;vertical-align:bottom}
table.booktabs td{padding:5px 8px;vertical-align:top;border-top:1px solid #efeee9}
table.booktabs tbody tr:first-child td{border-top:none}
table.small{font-size:13px}
.table-wrap{overflow-x:auto}
figure{margin:24px 0 26px;text-align:center}
figure svg{display:block;margin:0 auto;height:auto}
figcaption{font-size:14px;line-height:1.6;text-align:justify;margin:10px auto 0;max-width:760px;color:var(--ink-2)}
figcaption b{color:var(--ink)}
.ev{display:inline-block;font-size:11px;line-height:1.5;padding:0 6px;border-radius:3px;vertical-align:2px;font-weight:700;letter-spacing:.04em;white-space:nowrap}
.ev.m{background:#e8f0fb;color:#1d5aa6}
.ev.d{background:#efeee9;color:#3d3c39}
.ev.p{background:#fdeee6;color:#a8461a}
.ev.t{background:#e3f5ed;color:#126b4b}
.refs ol{font-size:14px;line-height:1.6}
.appendix h2{margin-top:30px}
.katex-display{overflow-x:auto;overflow-y:hidden;padding:2px 0}
@media (max-width:640px){
  .abstract,.toc{margin:16px 0}
  .toc ol{columns:1}
  h1{font-size:22px}
  table.booktabs{display:block;overflow-x:auto}
}
@media print{
  main{max-width:none;padding:0}
  figure,table{break-inside:avoid}
  a{color:inherit}
  .toc{display:none}
}
</style>
</head>
<body>
<main>
"""

TAIL = """
<footer style="margin-top:48px;padding-top:12px;border-top:1px solid var(--hair);font-size:12px;color:var(--muted)">
本文由 <code>paper/src/build_v5.py</code> 从 <code>body_v5.html</code> 与 <code>figures.py</code> 生成；配图坐标由数据直接计算。数据发布版本 FTD-20261009-1；manifest SHA256 <code style="overflow-wrap:anywhere">cff4e114ba6f661878a601f353756dc0367d478dda487787e32f8ec64cd95840</code>。
</footer>
</main>
</body>
</html>
"""


def main():
    body = open(os.path.join(HERE, "body_v5.html"), encoding="utf-8").read()
    used = set()

    def sub(m):
        key = m.group(1)
        if key not in figures.V5:
            raise SystemExit("未知配图：" + key)
        used.add(key)
        return figures.V5[key]()

    body = re.sub(r"<!--FIG:([a-z0-9]+)-->", sub, body)
    missing = set(figures.V5) - used
    if missing:
        raise SystemExit("有配图未被正文引用：%s" % sorted(missing))
    # 宽表包一层可横向滚动的容器，保证窄屏不撑破页面
    body = re.sub(r"(<table class=\"booktabs[^\"]*\">.*?</table>)", r'<div class="table-wrap">\1</div>', body, flags=re.S)
    html = HEAD + body + TAIL
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("写出", os.path.normpath(OUT), "%.1f KB" % (len(html.encode("utf-8")) / 1024), "配图", len(used))


if __name__ == "__main__":
    main()
