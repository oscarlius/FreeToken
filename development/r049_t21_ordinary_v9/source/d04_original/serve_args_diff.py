#!/usr/bin/env python
"""把两份 serve.log 的 `Parsed arguments` 逐字段对比，打印所有差异键。
起因：E1-R002 声称「只改 --moe-strategy」，实际 hybrid 腿解析到 max_extend_tokens=8192、对照腿 4096，
把分块尺寸的收益误记成了 hybrid 的收益。命令行没写的字段也会从服务端默认值解析出来，所以只能比解析行。"""
import re
import sys

KEY = re.compile(r"^\s*Parsed arguments", re.M)


def split_top(s):
    parts, depth, cur, i = [], 0, [], 0
    while i < len(s):
        c = s[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        if c == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    if cur:
        parts.append("".join(cur))
    return parts


def parse(path):
    txt = open(path, encoding="utf-8", errors="replace").read()
    k = txt.find("Parsed arguments")
    if k < 0:
        raise SystemExit("%s: 没有 Parsed arguments 行" % path)
    s = txt.find("ServerArgs(", k)
    if s < 0:
        raise SystemExit("%s: 没有 ServerArgs( 段" % path)
    depth = 0
    end = None
    for i in range(s + len("ServerArgs"), len(txt)):
        c = txt[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end is None:
        raise SystemExit("%s: ServerArgs 括号不平衡" % path)
    body = txt[s + len("ServerArgs") + 1:end]
    out = {}
    for part in split_top(body):
        if "=" not in part:
            continue
        name, _, val = part.partition("=")
        out[name.strip()] = val.strip()
    return out


def main():
    if len(sys.argv) < 3:
        raise SystemExit("用法：serve_args_diff.py A.log B.log [只报告的键数]")
    a, b = parse(sys.argv[1]), parse(sys.argv[2])
    cap = int(sys.argv[3]) if len(sys.argv) > 3 else 40
    shared = sorted(set(a) & set(b))
    diff = [k for k in shared if a[k] != b[k]]
    only_a = sorted(set(a) - set(b))
    only_b = sorted(set(b) - set(a))
    print("可比字段 %d，差异 %d，只在 A %d，只在 B %d" % (len(shared), len(diff), len(only_a), len(only_b)))
    for k in diff[:cap]:
        print("  %-28s A=%-40s B=%s" % (k, a[k][:40], b[k][:40]))
    if len(diff) > cap:
        print("  ...其余 %d 项未打印" % (len(diff) - cap))
    for k in only_a:
        print("  仅 A: %s=%s" % (k, a[k][:60]))
    for k in only_b:
        print("  仅 B: %s=%s" % (k, b[k][:60]))
    return 0 if diff else 0


if __name__ == "__main__":
    sys.exit(main())
