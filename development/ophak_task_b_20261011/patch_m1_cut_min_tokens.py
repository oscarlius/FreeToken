#!/usr/bin/env python3
"""任务 B 的候选改动：--prefill-anchor-cut-min-tokens（默认 0），只改指令 §2 列出的位置。

用法：python3 patch_m1_cut_min_tokens.py <候选工作树根目录>
每一处替换都必须在目标文件中恰好命中一次，否则整体中止，不写入任何文件。
"""
from __future__ import annotations

import sys
from pathlib import Path

EDITS = [
    # 1. scheduler/config.py：第 21 行旁增加字段（ServerArgs 继承 SchedulerConfig，不在 ServerArgs 重复声明）
    ("python/freetoken/scheduler/config.py",
     "    prefill_anchor_cut: bool = True\n\n    # networking config\n",
     "    prefill_anchor_cut: bool = True\n    prefill_anchor_cut_min_tokens: int = 0\n\n    # networking config\n"),
    # 2. server/args.py：--no-prefill-anchor-cut 之后增加参数
    ("python/freetoken/server/args.py",
     '        help="Do not split prefill chunks at special-token anchors.",\n    )\n',
     '        help="Do not split prefill chunks at special-token anchors.",\n    )\n\n'
     "    parser.add_argument(\n"
     '        "--prefill-anchor-cut-min-tokens",\n'
     "        type=int,\n"
     '        dest="prefill_anchor_cut_min_tokens",\n'
     "        default=ServerArgs.prefill_anchor_cut_min_tokens,\n"
     '        help="只有本段待预填 token 数超过 N 时才按锚点切段；0 表示与原行为相同",\n'
     "    )\n"),
    # 3. scheduler/scheduler.py:141：构造 PrefillManager 时传入
    ("python/freetoken/scheduler/scheduler.py",
     "            prefill_anchor_cut=config.prefill_anchor_cut,\n        )\n",
     "            prefill_anchor_cut=config.prefill_anchor_cut,\n"
     "            prefill_anchor_cut_min_tokens=config.prefill_anchor_cut_min_tokens,\n        )\n"),
    # 4. scheduler/prefill.py：PrefillAdder 字段（约 68 行）
    ("python/freetoken/scheduler/prefill.py",
     "    # D01: only gates the prefill anchor scan; anchor matching and decode snapshots remain on.\n"
     "    prefill_anchor_cut: bool = True\n",
     "    # D01: only gates the prefill anchor scan; anchor matching and decode snapshots remain on.\n"
     "    prefill_anchor_cut: bool = True\n"
     "    # 任务 B：只有本段待预填 token 数（remain_len）超过它才按锚点切段；0 与原行为相同\n"
     "    prefill_anchor_cut_min_tokens: int = 0\n"),
    # 5. scheduler/prefill.py：PrefillManager 字段（约 362 行）
    ("python/freetoken/scheduler/prefill.py",
     "    # D01: gates only PrefillAdder's anchor scan; Scheduler leaves anchor_ids intact.\n"
     "    prefill_anchor_cut: bool = True\n",
     "    # D01: gates only PrefillAdder's anchor scan; Scheduler leaves anchor_ids intact.\n"
     "    prefill_anchor_cut: bool = True\n"
     "    # 任务 B：同 PrefillAdder.prefill_anchor_cut_min_tokens\n"
     "    prefill_anchor_cut_min_tokens: int = 0\n"),
    # 6. scheduler/prefill.py：179 行条件末尾加 remain_len 门（语义与原条件逐字相同，仅多一项）
    ("python/freetoken/scheduler/prefill.py",
     "        if self.prefill_anchor_cut and self.anchor_ids and chunk_size > self.cache_manager.page_size:\n",
     "        if (\n"
     "            self.prefill_anchor_cut\n"
     "            and self.anchor_ids\n"
     "            and chunk_size > self.cache_manager.page_size\n"
     "            and remain_len > self.prefill_anchor_cut_min_tokens\n"
     "        ):\n"),
    # 7. scheduler/prefill.py：schedule_next_batch 构造 PrefillAdder 处传递（_schedule_dev_prefill 不动）
    ("python/freetoken/scheduler/prefill.py",
     "            prefill_anchor_cut=self.prefill_anchor_cut,\n        )\n",
     "            prefill_anchor_cut=self.prefill_anchor_cut,\n"
     "            prefill_anchor_cut_min_tokens=self.prefill_anchor_cut_min_tokens,\n        )\n"),
    # 8. 既有接线测试的伪配置补上新字段（否则 Scheduler 读取该字段时 AttributeError；只补数据，不改断言）
    ("tests/scheduler/test_anchor_cut_scheduler_wiring.py",
     "special_token_ckpt=True, prefill_anchor_cut=cut, max_extend_tokens=8192,\n",
     "special_token_ckpt=True, prefill_anchor_cut=cut, prefill_anchor_cut_min_tokens=0,\n"
     "        max_extend_tokens=8192,\n"),
]


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    contents: dict[Path, str] = {}
    for rel, old, new in EDITS:
        path = root / rel
        text = contents.get(path)
        if text is None:
            text = path.read_text(encoding="utf-8")
        hits = text.count(old)
        if hits != 1:
            print(f"ABORT {rel}: 期望恰好命中 1 次，实际 {hits} 次", file=sys.stderr)
            return 2
        contents[path] = text.replace(old, new, 1)
    for path, text in contents.items():
        path.write_text(text, encoding="utf-8", newline="\n")
    print(f"applied {len(EDITS)} edits to {len(contents)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
