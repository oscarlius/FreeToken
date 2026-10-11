#!/usr/bin/env python3
"""CPU-only R052a UID trajectory parser; it sends no requests."""
import argparse
import json
import re
from pathlib import Path

ARCHIVE = re.compile(r"archived boundary (\d+) -> host slot")
DONATE = re.compile(r"\[D3-DONATE\] cached_len=(\d+) L=([^ ]+) ext=(\d+)")
RESUME = re.compile(r"resuming req (\d+) from host slot")
SEGMENT = re.compile(r"D0 seg: idx=(\d+) reason=([^ ]+) reqs=(\d+):(\d+)/(\d+)")


def analyze(text, full=13554, page=64, target_uid=7, followup_uid=8):
    """Bind retained log events to UID 7's target and UID 8's follow-up.

    The source-level conclusion is deliberately narrow: a final target length that
    is not page aligned cannot be finish-donated by the recorded cache branch, and
    decode does not build a track. The parser does not claim a log line alone
    proves that branch ran.
    """
    current_uid = None
    events = []
    for line_no, line in enumerate(text.splitlines(), 1):
        segment = SEGMENT.search(line)
        if segment:
            _, reason, uid, new_tokens, cached_tokens = segment.groups()
            current_uid = int(uid)
            events.append({"kind": "segment", "line": line_no, "uid": current_uid,
                           "reason": reason, "new_tokens": int(new_tokens),
                           "cached_tokens": int(cached_tokens)})
            continue
        resume = RESUME.search(line)
        if resume:
            events.append({"kind": "resume", "line": line_no, "uid": int(resume.group(1))})
            continue
        archive = ARCHIVE.search(line)
        if archive:
            events.append({"kind": "archive", "line": line_no, "uid": current_uid,
                           "boundary": int(archive.group(1))})
            continue
        donate = DONATE.search(line)
        if donate:
            cached_len, track_len, extend_len = donate.groups()
            events.append({"kind": "donate", "line": line_no, "uid": current_uid,
                           "cached_len": int(cached_len),
                           "track_len": None if track_len == "None" else int(track_len),
                           "extend_len": int(extend_len)})

    archive = next((x for x in events if x["kind"] == "archive" and x["boundary"] == 13376), None)
    target_resume = next((x for x in events if x["kind"] == "resume" and x["uid"] == target_uid), None)
    short_target = next((x for x in events if x["kind"] == "donate" and x["uid"] == target_uid
                         and x["cached_len"] == 13433 and x["track_len"] is None), None)
    followup_resume = next((x for x in events if x["kind"] == "resume" and x["uid"] == followup_uid), None)
    floor = full // page * page
    followup_track = next((x for x in events if x["kind"] == "donate" and x["uid"] == followup_uid
                           and x["track_len"] == floor), None)
    if archive is None or archive["uid"] != 6:
        raise ValueError("retained 13376 archive is not bound to UID 6")
    if target_resume is None or short_target is None:
        raise ValueError("retained target UID 7 short-prefill trajectory absent")
    if followup_resume is None or followup_track is None:
        raise ValueError("retained follow-up UID 8 trajectory to the x64 boundary absent")
    return {
        "target_uid": target_uid,
        "followup_uid": followup_uid,
        "full_tokens": full,
        "page_size": page,
        "floor_64": floor,
        "observed_cached": 13376,
        "gap": floor - 13376,
        "archive": archive,
        "target_short_prefill": short_target,
        "followup_track": followup_track,
        "source_control_flow": {
            "decode_builds_track": False,
            "finish_donate_requires_exact_page_alignment": True,
            "target_finish_is_page_aligned": full == floor,
        },
        "conclusion": (
            "UID 7's L=None is a prefill-only observation. The source path has no decode track and, "
            "for a 13554 final length, rejects finish donation at the 13504 floor because the final "
            "length is unaligned. UID 8 reaches L=13504 only after it already resumed from 13376."
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("serve_log", type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.serve_log.read_text(encoding="utf-8", errors="replace")), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
