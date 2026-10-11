#!/usr/bin/env python3
"""把 ledger.json 编译成自包含的静态展台页 index.html。

设计约束：
  - 零外部依赖（无 CDN、无构建步骤），单文件可直接用浏览器打开；
  - **不碰 8099 监控的任何文件**（monitor.py / web/ 由 Codex 维护），独立目录独立产物，
    后续要并进 8099 时把本目录整体搬过去即可；
  - 校验：证据路径与 commit 逐个核对，核不到的不隐藏、标成「未核到」并计数，
    避免台账自己腐烂后没人知道。

用法：
    python build_exhibit.py [--ledger ledger.json] [--out index.html] [--no-verify]

在 /data2/FreeToken/exhibit/ 下运行可以核到真实证据路径与 git commit；
在本地跑则自动降级为「未核到」，页面仍可出。
"""

from __future__ import annotations

import argparse
import html
import json
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = "/data2/FreeToken/src/FreeToken"

STATUS_TEXT = {"done": "已完成", "partial": "部分过门", "planned": "未开始"}
VERDICT_TEXT = {"pass": "过门", "fail": "不过门"}


# ---------------------------------------------------------------- 校验


def verify(ledger: dict) -> dict:
    """核对证据路径与 commit。核不到只标记，不抛错。"""
    out = {"paths": {}, "commits": {}, "repo_reachable": False}

    paths = []
    for item in ledger.get("items", []):
        paths.extend(item.get("evidence") or [])
    paths.extend(ledger.get("baseline", {}).get("evidence") or [])
    for p in sorted(set(paths)):
        # 只有绝对远端路径才核；仓库内的相对路径（文档）交给人工
        if p.startswith("/"):
            out["paths"][p] = os.path.exists(p)

    commits = []
    for item in ledger.get("items", []):
        commits.extend(item.get("commits") or [])
    commits = sorted(set(commits))
    if commits and os.path.isdir(os.path.join(REPO, ".git")):
        out["repo_reachable"] = True
        for c in commits:
            r = subprocess.run(
                ["git", "cat-file", "-t", c],
                cwd=REPO, capture_output=True, text=True,
            )
            out["commits"][c] = r.stdout.strip() == "commit"
    return out


# ---------------------------------------------------------------- 片段


def esc(x) -> str:
    return html.escape(str(x))


def fmt_delta(m: dict) -> str:
    d = m.get("delta_pct")
    if d is None:
        return '<span class="delta none">—</span>'
    arrow = "▼" if d < 0 else ("▲" if d > 0 else "＝")
    cls = "good" if _is_good(m, d) else "bad"
    return f'<span class="delta {cls}">{arrow} {abs(d):.1f}%</span>'


def _is_good(m: dict, d: float) -> bool:
    """下降为好还是上升为好，取决于指标方向。"""
    if m.get("direction") == "lower_better":
        return d < 0
    if m.get("direction") == "higher_better":
        return d > 0
    return False


def badge(verdict: str) -> str:
    if verdict in VERDICT_TEXT:
        return f'<span class="badge {verdict}">{VERDICT_TEXT[verdict]}</span>'
    return f'<span class="badge unknown">{esc(verdict)}</span>'


def render_metrics(metrics: list) -> str:
    rows = []
    for m in metrics:
        base = m.get("baseline_value")
        cand = m.get("candidate_value")
        rounds = m.get("candidate_rounds") or []
        rounds_txt = " / ".join(str(r) for r in rounds) if len(rounds) > 1 else ""
        note = m.get("note") or ""
        proto = m.get("protocol") or ""
        rows.append(f"""
      <tr>
        <td class="metric">{esc(m['metric'])}<div class="sub">口径：{esc(proto)}</div></td>
        <td class="num">{esc(base) if base is not None else '—'}</td>
        <td class="num strong">{esc(cand)}{'<div class="sub">'+esc(rounds_txt)+'</div>' if rounds_txt else ''}</td>
        <td class="num">{fmt_delta(m)}</td>
        <td class="gate">{esc(m.get('gate', '—'))}</td>
        <td>{badge(m.get('verdict', 'unknown'))}</td>
      </tr>""")
        if note:
            rows.append(f'<tr class="noterow"><td colspan="6">{esc(note)}</td></tr>')
    return f"""
    <table class="metrics">
      <thead><tr>
        <th>指标</th><th class="num">基线</th><th class="num">候选</th>
        <th class="num">差值</th><th>验收门</th><th>判定</th>
      </tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>"""


def render_files(files: list) -> str:
    if not files:
        return '<p class="none">配置层改动，不涉及代码文件。</p>'
    rows = "".join(
        f'<tr><td class="path">{esc(f["path"])}</td><td>{esc(f["what"])}</td></tr>'
        for f in files
    )
    return f'<table class="files"><tbody>{rows}</tbody></table>'


def render_commits(commits: list, v: dict) -> str:
    if not commits:
        return '<span class="none">无（配置层）</span>'
    out = []
    for c in commits:
        ok = v["commits"].get(c)
        cls = "ok" if ok else ("nocheck" if not v["repo_reachable"] else "missing")
        mark = {"ok": "✓", "nocheck": "?", "missing": "✗"}[cls]
        out.append(f'<span class="commit {cls}" title="{cls}">{esc(c[:7])} {mark}</span>')
    return " ".join(out)


def render_evidence(paths: list, v: dict) -> str:
    out = []
    for p in paths:
        if p.startswith("/"):
            ok = v["paths"].get(p)
            cls = "ok" if ok else "missing"
            mark = "✓" if ok else "✗"
        else:
            cls, mark = "doc", "·"
        out.append(f'<code class="path {cls}">{mark} {esc(p)}</code>')
    return "<br>".join(out) if out else '<span class="none">—</span>'


def render_item(it: dict, v: dict) -> str:
    st = it.get("status", "planned")
    rc = ""
    if it.get("root_cause"):
        r = it["root_cause"]
        rc = f"""
    <div class="rootcause">
      <div class="rc-title">根因定位</div>
      <p class="rc-claim">{esc(r['claim'])}</p>
      <p class="rc-where">位置：<code>{esc(r['where'])}</code></p>
      <pre class="rc-code">{esc(r['code'])}</pre>
      <p class="rc-proof">{esc(r['proof'])}</p>
      <p class="rc-block">阻塞：{esc(r['blocked_work'])}</p>
    </div>"""

    res = ""
    if it.get("residual"):
        res = f'<p class="residual"><b>剩余差距 / 后续：</b>{esc(it["residual"])}</p>'

    return f"""
  <article class="item s-{st}">
    <header>
      <span class="id">{esc(it['id'])}</span>
      <h3>{esc(it['name'])}</h3>
      <span class="badge status-{st}">{esc(STATUS_TEXT.get(st, st))}</span>
      <span class="kind kind-{esc(it['kind'])}">{'代码' if it['kind'] == 'code' else '配置'}</span>
      <span class="layer">{esc(it.get('layer', ''))}</span>
    </header>
    <p class="verdict-line">{esc(it.get('verdict', ''))}　<span class="gate">验收门：{esc(it.get('gate', '—'))}</span></p>
    <div class="method"><b>方法论 → 机制：</b>{esc(it.get('method', ''))}</div>
    <p class="why"><b>为什么改这里：</b>{esc(it.get('why_it_matters', ''))}</p>
    <div class="switch">开关：<code>{esc(it.get('switch', '—'))}</code></div>
    <h4>推理框架里改了哪几部分</h4>
    {render_files(it.get('files', []))}
    <div class="meta">提交：{render_commits(it.get('commits', []), v)}</div>
    <h4>改完之后测出什么（{len(it.get('metrics', []))} 项）</h4>
    {render_metrics(it.get('metrics', []))}
    {rc}
    {res}
    <h4>证据</h4>
    <div class="ev">{render_evidence(it.get('evidence', []), v)}</div>
  </article>"""


def render_rejected(rs: list) -> str:
    rows = "".join(
        f'<tr><td>{esc(r["name"])}</td>'
        f'<td><span class="badge {"config" if r["kind"] == "config" else "code"}">'
        f'{"配置" if r["kind"] == "config" else "代码"}</span></td>'
        f'<td class="num">{esc(r.get("result", ""))}</td>'
        f'<td class="whycell">{esc(r.get("why", ""))}</td></tr>'
        for r in rs
    )
    return f"""
  <table class="rej">
    <thead><tr><th>方案</th><th>层</th><th>实测</th><th>否决理由</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>"""


def render_not_started(ns: list) -> str:
    rows = "".join(
        f'<tr><td class="mono">{esc(n["id"])}</td><td>{esc(n["name"])}</td>'
        f'<td class="whycell">{esc(n["reason"])}</td></tr>'
        for n in ns
    )
    return f'<table class="rej"><tbody>{rows}</tbody></table>'


# ---------------------------------------------------------------- 主流程


def build(ledger: dict, v: dict) -> str:
    b = ledger["baseline"]
    s = ledger["subject"]
    items = ledger["items"]

    n_pass = sum(1 for i in items for m in i.get("metrics", []) if m.get("verdict") == "pass")
    n_fail = sum(1 for i in items for m in i.get("metrics", []) if m.get("verdict") == "fail")
    n_done = sum(1 for i in items if i.get("status") in ("done", "partial"))
    bad_paths = [p for p, ok in v["paths"].items() if not ok]
    bad_commits = [c for c, ok in v["commits"].items() if not ok]

    checkbar = ""
    if v["repo_reachable"]:
        state = "ok" if not (bad_paths or bad_commits) else "bad"
        checkbar = (
            f'<span class="check {state}">证据核验：'
            f'{len(v["paths"]) - len(bad_paths)}/{len(v["paths"])} 路径存在，'
            f'{len(v["commits"]) - len(bad_commits)}/{len(v["commits"])} commit 可达</span>'
        )
        if bad_paths:
            checkbar += f'<span class="check bad">缺：{esc(", ".join(bad_paths))}</span>'
        if bad_commits:
            checkbar += f'<span class="check bad">缺 commit：{esc(", ".join(bad_commits))}</span>'
    else:
        checkbar = '<span class="check warn">未核验（不在 FreeToken 仓库/远端路径下运行）</span>'

    return f"""<!doctype html>
<html lang="zh-CN" data-theme="dark"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FreeToken 改动地图 · 效果台账</title>
<style>
:root{{
  --bg:#0d1117; --panel:#161b22; --line:#30363d; --fg:#e6edf3; --dim:#8b949e;
  --acc:#58a6ff; --good:#3fb950; --bad:#f85149; --warn:#d29922;
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);
  font:14px/1.65 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}}
.wrap{{max-width:1240px;margin:0 auto;padding:28px 22px 70px}}
h1{{font-size:23px;margin:0 0 6px}}
h1 .sub{{color:var(--dim);font-weight:400;font-size:15px}}
h3{{font-size:17px;margin:0}}
h4{{font-size:12px;color:var(--dim);text-transform:uppercase;letter-spacing:.09em;
  margin:20px 0 8px;font-weight:600}}
code,.mono{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px}}
.stamp{{color:var(--dim);font-size:12.5px;margin-bottom:18px}}
.stamp b{{color:var(--fg);font-weight:600}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));gap:12px;margin:18px 0 8px}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:13px 15px}}
.card .label{{color:var(--dim);font-size:11.5px;text-transform:uppercase;letter-spacing:.07em}}
.card .value{{font-size:23px;font-weight:650;margin:5px 0 2px;font-variant-numeric:tabular-nums}}
.card .small{{color:var(--dim);font-size:11.5px;line-height:1.5}}
.v-good{{color:var(--good)}} .v-bad{{color:var(--bad)}} .v-acc{{color:var(--acc)}}
.baseline{{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--acc);
  border-radius:9px;padding:15px 18px;margin:16px 0 26px}}
.baseline h2{{font-size:15px;margin:0 0 8px}}
.baseline p{{margin:5px 0;color:var(--dim);font-size:13px}}
.baseline b{{color:var(--fg)}}
.item{{background:var(--panel);border:1px solid var(--line);border-radius:11px;
  padding:19px 21px;margin:0 0 18px}}
.item.s-partial{{border-left:3px solid var(--warn)}}
.item.s-done{{border-left:3px solid var(--good)}}
.item header{{display:flex;align-items:center;gap:11px;flex-wrap:wrap;margin-bottom:11px}}
.id{{background:#21262d;border:1px solid var(--line);border-radius:6px;
  padding:2px 9px;font-family:ui-monospace,monospace;font-size:13px;font-weight:600}}
.layer{{color:var(--dim);font-size:12.5px}}
.kind{{font-size:11px;padding:1px 7px;border-radius:4px;border:1px solid var(--line);color:var(--dim)}}
.kind-code{{color:var(--acc);border-color:#1f4b7a}}
.verdict-line{{margin:0 0 13px;font-size:14px}}
.method,.why{{margin:7px 0;color:#c9d1d9}}
.method b,.why b{{color:var(--dim);font-weight:600;font-size:12.5px}}
.switch{{margin:11px 0;color:var(--dim);font-size:12.5px}}
.switch code{{background:#21262d;padding:2px 7px;border-radius:4px;color:var(--acc)}}
table{{width:100%;border-collapse:collapse;margin:9px 0}}
th{{text-align:left;font-size:11.5px;color:var(--dim);text-transform:uppercase;
  letter-spacing:.06em;border-bottom:1px solid var(--line);padding:7px 9px;font-weight:600}}
td{{padding:9px;border-bottom:1px solid #21262d;vertical-align:top}}
.num{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
.strong{{font-weight:650;color:var(--acc)}}
.metric{{width:34%}}
.metric .sub,.td .sub{{color:var(--dim);font-size:11.5px;font-weight:400;margin-top:3px;white-space:normal}}
tr.noterow td{{color:var(--dim);font-size:12.5px;padding-top:0;border-bottom:1px solid #21262d}}
.gate{{color:var(--dim);font-size:12.5px;white-space:nowrap}}
td.gate{{white-space:normal;min-width:130px}}
.badge{{display:inline-block;font-size:11.5px;padding:1px 8px;border-radius:11px;
  border:1px solid var(--line);white-space:nowrap}}
.badge.pass{{color:var(--good);border-color:#1c6b30;background:#0f2b16}}
.badge.fail{{color:var(--bad);border-color:#7d2b28;background:#2d1211}}
.badge.status-done,.badge.done{{color:var(--good);border-color:#1c6b30}}
.badge.status-partial,.badge.partial{{color:var(--warn);border-color:#7a5c12}}
.badge.config{{color:var(--dim)}} .badge.code{{color:var(--acc);border-color:#1f4b7a}}
.delta{{font-weight:650}} .delta.good{{color:var(--good)}} .delta.bad{{color:var(--bad)}}
.delta.none{{color:var(--dim);font-weight:400}}
.path{{color:var(--acc);word-break:break-all}}
td.files path,.files .path{{width:44%}}
.files td{{font-size:12.5px;color:#c9d1d9}}
.meta{{margin-top:9px;font-size:12.5px;color:var(--dim)}}
.commit{{background:#21262d;border:1px solid var(--line);border-radius:4px;
  padding:1px 6px;margin-right:5px;font-size:12px}}
.commit.ok{{color:var(--good)}} .commit.missing{{color:var(--bad);text-decoration:line-through}}
.commit.nocheck{{color:var(--dim)}}
.ev code{{display:inline-block;margin:0 7px 5px 0}}
.ev code.ok{{color:var(--dim)}} .ev code.missing{{color:var(--bad)}}
.ev code.doc{{color:var(--acc)}}
.none{{color:var(--dim);font-size:12.5px}}
.rootcause{{background:#1a1410;border:1px solid #4a3416;border-radius:8px;
  padding:14px 16px;margin:16px 0}}
.rc-title{{color:var(--warn);font-weight:650;font-size:13px;margin-bottom:7px}}
.rc-claim{{margin:0 0 8px;font-size:14px;color:#f0d9b5}}
.rc-where{{margin:0 0 9px;color:var(--dim);font-size:12.5px}}
.rc-code{{background:#0d1117;border:1px solid var(--line);border-radius:6px;
  padding:11px 13px;overflow-x:auto;font-size:12px;color:#a5d6ff;margin:0 0 9px;white-space:pre-wrap}}
.rc-proof{{margin:0 0 7px;font-size:13px;color:#c9d1d9}}
.rc-block{{margin:0;font-size:12.5px;color:var(--dim)}}
.residual{{margin:13px 0 0;font-size:13px;color:#c9d1d9;
  border-left:2px solid var(--line);padding-left:11px}}
.whycell{{font-size:12.5px;color:var(--dim)}}
.rej td{{font-size:13px}}
.hyg{{background:#1a1410;border:1px solid #4a3416;border-radius:9px;padding:14px 18px;margin-top:22px}}
.hyg h2{{font-size:14px;margin:0 0 8px;color:var(--warn)}}
.hyg li{{margin:5px 0;color:#c9d1d9;font-size:13px}}
.foot{{margin-top:26px;color:var(--dim);font-size:12px;border-top:1px solid var(--line);padding-top:14px}}
.check{{display:inline-block;margin:0 9px 6px 0;font-size:12px;padding:2px 9px;
  border-radius:5px;border:1px solid var(--line)}}
.check.ok{{color:var(--good);border-color:#1c6b30}}
.check.bad{{color:var(--bad);border-color:#7d2b28}}
.check.warn{{color:var(--warn);border-color:#7a5c12}}
</style></head><body><div class="wrap">

<h1>FreeToken 改动地图 · 效果台账 <span class="sub">/ Qwen3.8-Flash-Next-NVFP4</span></h1>
<div class="stamp">
  主体 <b>{esc(s['model'])}</b> on {esc(s['framework'])}　·　机器 <b>{esc(s['gpu'])}</b> @ {esc(s['host'])}<br>
  代码库 <b>{esc(s['repo_remote'])}</b> 分支 <b>{esc(s['branch'])}</b>　·　数据观测于 {esc(s['observed_at'])}
</div>

<div class="cards">
  <div class="card"><div class="label">已测完的开发项</div>
    <div class="value">{n_done} <span style="font-size:14px;color:var(--dim)">/ {len(items)}</span></div>
    <div class="small">含部分过门项</div></div>
  <div class="card"><div class="label">过门的验收指标</div>
    <div class="value v-good">{n_pass}</div><div class="small">共 {n_pass + n_fail} 项有结论</div></div>
  <div class="card"><div class="label">不过门的指标</div>
    <div class="value v-bad">{n_fail}</div><div class="small">全部列在下方，不隐藏</div></div>
  <div class="card"><div class="label">已否决的方案</div>
    <div class="value">{len(ledger['rejected'])}</div><div class="small">负收益同样记录</div></div>
</div>

<div class="baseline">
  <h2>对照基线：{esc(b['title'])}</h2>
  <p>为什么是它：{esc(b['why'])}</p>
  <p>测量口径：{esc(b['protocol'])}</p>
  <p>基线值：冷 32K 首 token <b class="v-acc">{b['metrics']['ttft_cold32k_s']} s</b>　·
     解码 <b class="v-acc">{b['metrics']['decode_tps']} tok/s</b></p>
  {''.join(f'<p>⚠ {esc(c)}</p>' for c in b.get('caveats', []))}
</div>

<h2 style="font-size:18px;margin:30px 0 4px">一、改动地图：方法论 → 推理框架里改了哪几部分</h2>
<p class="stamp">每项列出机制、开关、以及实际动了哪些文件与函数。</p>
{''.join(render_item(i, v) for i in items)}

<h2 style="font-size:18px;margin:32px 0 4px">二、已否决的方案</h2>
<p class="stamp">实测为负或触发硬门，同样列出以免重复试。</p>
{render_rejected(ledger['rejected'])}

<h2 style="font-size:18px;margin:32px 0 4px">三、尚未开始</h2>
{render_not_started(ledger['not_started'])}

<div class="hyg">
  <h2>⚠ 仓库卫生提醒（会影响任何按改动量做的展示）</h2>
  <ul>{''.join(f'<li>{esc(h)}</li>' for h in ledger['hygiene'])}</ul>
</div>

<div class="foot">
  数据源 <code>ledger.json</code>，由 <code>build_exhibit.py</code> 编译；{checkbar}<br>
  本页独立于 8099 监控（不读写其任何文件），需并入时把 <code>freetoken/exhibit/</code> 整体搬过去即可。
</div>
</div></body></html>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default=str(HERE / "ledger.json"))
    ap.add_argument("--out", default=str(HERE / "index.html"))
    ap.add_argument("--no-verify", action="store_true")
    a = ap.parse_args()

    ledger = json.loads(Path(a.ledger).read_text(encoding="utf-8"))
    v = {"paths": {}, "commits": {}, "repo_reachable": False}
    if not a.no_verify:
        v = verify(ledger)

    Path(a.out).write_text(build(ledger, v), encoding="utf-8")

    npass = sum(1 for i in ledger["items"] for m in i.get("metrics", []) if m.get("verdict") == "pass")
    nfail = sum(1 for i in ledger["items"] for m in i.get("metrics", []) if m.get("verdict") == "fail")
    bad_p = [p for p, ok in v["paths"].items() if not ok]
    bad_c = [c for c, ok in v["commits"].items() if not ok]
    print(f"写出 {a.out}")
    print(f"  条目 {len(ledger['items'])} · 过门 {npass} · 不过门 {nfail} · 否决 {len(ledger['rejected'])}")
    if v["repo_reachable"]:
        print(f"  证据 {len(v['paths']) - len(bad_p)}/{len(v['paths'])} 存在"
              f" · commit {len(v['commits']) - len(bad_c)}/{len(v['commits'])} 可达")
        for p in bad_p:
            print(f"  ✗ 证据缺失: {p}")
        for c in bad_c:
            print(f"  ✗ commit 不可达: {c}")
    else:
        print("  未核验（不在远端仓库下运行）")


if __name__ == "__main__":
    main()