#!/usr/bin/env python
"""比两个落盘目录里同长度的 donate 状态：一次是「整段重算」，一次是「bank 恢复后继续算」。

用法：state_eq.py DIR_REF DIR_RESUME [--tol 0]
  1) 各读 index.jsonl，按 length 取 kind=donate 的记录（同一长度取最后一条）；
  2) 逐元素比 conv_states / recurrent_states / slot_*：先比 sha，再比 max/mean 绝对差；
  3) 输出每个长度的结论：逐位一致 / 差多少；并对 resume 目录里的 archive↔resume 做搬运保真检查。
失败关闭：目录里没有 donate 记录、长度对不上、npy 形状不一致 -> 直接报错退出，不返回"看起来一致"。
"""
import argparse
import json
import os
import sys

import torch


def load(d):
    p = os.path.join(d, "index.jsonl")
    if not os.path.exists(p):
        raise SystemExit("没有 index.jsonl：%s（钩子没触发或目录错了）" % d)
    rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    if not rows:
        raise SystemExit("index.jsonl 是空的：%s" % d)
    return rows


def donate_by_length(rows):
    """返回 {长度: [记录...]}（按 seq 升序）。同长度可能有多条：一条请求中途的完成捐赠、
    或另一条请求走到同一边界 —— 它们之间的差异就是「同进程重复计算的状态漂移」，
    必须先量出来，否则跨目录比出的差异没有基准。"""
    out = {}
    for r in rows:
        if r.get("kind") != "donate":
            continue
        L = r.get("length")
        if not L:
            continue
        out.setdefault(int(L), []).append(r)
    for v in out.values():
        v.sort(key=lambda r: r.get("seq", 0))
    if not out:
        raise SystemExit("没有任何 donate 记录 —— 完成捐赠点没触发？")
    return out


def intra_length_diff(d, by_len):
    """同长度多条 donate 之间的最大绝对差；返回 {长度: 差值或 'sha一致'}。"""
    res = {}
    for L, recs in by_len.items():
        if len(recs) < 2:
            continue
        shas = set()
        for r in recs:
            shas.add((r.get("recurrent_states_sha"), r.get("conv_states_sha")))
        if len(shas) == 1:
            res[L] = 0.0
            continue
        mx = 0.0
        base = tensors(recs[0], d)
        for r in recs[1:]:
            other = tensors(r, d)
            for name in set(base) & set(other):
                mx = max(mx, float((base[name].float() - other[name].float()).abs().max()))
        res[L] = mx
    return res


def tensors(rec, d):
    """按「角色名」（conv_states / slot:ple_conv / …）返回张量，不按文件名：
    文件名带每次落盘的 seq 计数器，两个臂各自计数不同，用文件名匹配会假失败。"""
    out = {}
    for key, fn in (rec.get("files") or {}).items():
        if not fn.endswith(".pt"):
            continue
        # bf16 到不了 numpy，全程留在 torch 里比
        out[key] = torch.load(os.path.join(d, fn), map_location="cpu")
    if not out:
        raise SystemExit("记录里没有 .pt：%s" % rec.get("kind"))
    return out


def transport_fidelity(rows, d):
    """archive/resume 的两侧 sha 是否一致：搬运本身有没有改 bit。"""
    bad, ok = [], 0
    for r in rows:
        if r.get("kind") not in ("archive", "resume"):
            continue
        pairs = [("conv_states_sha", "host_conv_states_sha"), ("recurrent_states_sha", "host_recurrent_states_sha")]
        for a, b in pairs:
            if a in r and b in r:
                if r[a] == r[b]:
                    ok += 1
                else:
                    bad.append((r["seq"], r["kind"], a, r[a], r[b]))
    return ok, bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir_ref")
    ap.add_argument("dir_resume")
    ap.add_argument("--label-ref")
    ap.add_argument("--label-test")
    ap.add_argument("--tol", type=float, default=0.0, help="允许的最大绝对差，默认 0（逐位）")
    a = ap.parse_args()

    ref, res = load(a.dir_ref), load(a.dir_resume)
    dl_ref, dl_res = donate_by_length(ref), donate_by_length(res)
    common = sorted(set(dl_ref) & set(dl_res))
    if not common:
        raise SystemExit("两边没有共同的 donate 长度：ref=%s resume=%s" % (
            sorted(dl_ref)[:8], sorted(dl_res)[:8]))

    i_ref, i_res = intra_length_diff(a.dir_ref, dl_ref), intra_length_diff(a.dir_resume, dl_res)
    if i_ref or i_res:
        print("同长度多条 donate 的自差（= 状态层噪声基准）：参照 %s 恢复 %s" % (
            {k: ("sha一致" if v == 0 else "%.3e" % v) for k, v in sorted(i_ref.items())},
            {k: ("sha一致" if v == 0 else "%.3e" % v) for k, v in sorted(i_res.items())}))
        print("  说明：跨目录比较每个长度取最后一条 donate；若同长度自差不为 0，则跨目录差异要对着这个基准读。")
    dl_ref = {k: v[-1] for k, v in dl_ref.items()}
    dl_res = {k: v[-1] for k, v in dl_res.items()}
    print("可比长度 %d 个：%s" % (len(common), common))
    worst = 0.0
    fails = []
    for L in common:
        t_ref, t_res = tensors(dl_ref[L], a.dir_ref), tensors(dl_res[L], a.dir_resume)
        shared = sorted(set(t_ref) & set(t_res))
        if not shared:
            raise SystemExit("长度 %d 两侧没有同名角色：%s / %s" % (L, sorted(t_ref), sorted(t_res)))
        only_ref = sorted(set(t_ref) - set(t_res))
        only_res = sorted(set(t_res) - set(t_ref))
        if only_ref or only_res:
            # 一侧多dump/少dump 都算不达标，不能只比交集然后说"一致"
            print("len=%-7d 角色集不一致 仅参照=%s 仅恢复=%s   <== 计入不达标" % (L, only_ref, only_res))
            fails.append(L)
        mx = 0.0
        bitsame = True
        for name in shared:
            x, y = t_ref[name], t_res[name]
            if x.shape != y.shape:
                raise SystemExit("长度 %d 形状不同 %s: %s vs %s" % (L, name, x.shape, y.shape))
            if not torch.equal(x, y):
                bitsame = False
            mx = max(mx, float((x.float() - y.float()).abs().max()))
        worst = max(worst, mx)
        line = "len=%-7d %s max|Δ|=%.3e  张量数=%d" % (L, "逐位一致" if bitsame else "有差异", mx, len(shared))
        if mx > a.tol:
            fails.append(L)
            line += "   <== 超容差 %.1e" % a.tol
        print(line)

    ok, bad = transport_fidelity(res, a.dir_resume)
    print("搬运保真（archive/resume 两侧 sha 相同）：%d 对一致，%d 对不一致" % (ok, len(bad)))
    for b in bad[:5]:
        print("   不一致：", b)

    from pathlib import Path

    label_ref = a.label_ref or "/".join(Path(a.dir_ref).resolve().parts[-2:])
    label_test = a.label_test or "/".join(Path(a.dir_resume).resolve().parts[-2:])
    resumed = any(row.get("kind") == "resume" for row in res)
    description = ("恢复侧与参照侧状态逐位一致" if resumed else "两侧状态逐位一致") if not fails else "有 %d 个长度不一致 %s" % (len(fails), fails)
    if resumed and fails:
        description = "恢复侧与参照侧" + description
    print("\n结论（%s 对 %s）：%s（最大绝对差 %.3e，容差 %.1e）" % (
        label_ref, label_test, description, worst, a.tol))
    return 0 if not fails and not bad else 1


if __name__ == "__main__":
    sys.exit(main())
