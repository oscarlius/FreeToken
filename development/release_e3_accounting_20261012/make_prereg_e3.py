"""Seal PREREG_RELEASE_E3.json before the release window (main session freetoken-06, 2026-10-12).

Usage (server, CPU only): python3 -I make_prereg_e3.py OUT.json
Reads only sealed sources: the -13 production argv and the e2 smoke reference. Writes OUT.json once (refuses to overwrite).
"""
import datetime
import hashlib
import json
import sys
from pathlib import Path

ACTIVE = Path("/data2/FreeToken/run/production.active.json")
E2_REF = Path("/data2/FreeToken/runs/dev_release/release_e2_ops_v8_20261009_smoke_guarded/source/development/"
              "redeploy_smoke_fix_20261009/redeploy_expected_reference.json")
E3_COMMIT = "9db0ee776c25afa8d2719ab700b2de7ccc606142"
E2_COMMIT = "481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9"
FLAG = ["--prefill-anchor-cut-min-tokens", "32768"]
EXTENSIONS = {
    "python/freetoken/kernel/_cpu_moe.cpython-310-x86_64-linux-gnu.so":
        "10a2bd8311b9569bd03a6569db59da707699a44e67d7b677c35c3547d77855b4",
    "python/freetoken/kernel/_pinned_tensor.cpython-310-x86_64-linux-gnu.so":
        "07701be28030c4ebf63c210804b6eba2556cc0f4d2f1e5ed80b9d423ebfe7e68",
}


def rows(*new_tokens: int) -> list[dict]:
    return [{"new_sequences": 1, "new_tokens": n, "cached_tokens": 0} for n in new_tokens]


def main() -> None:
    out = Path(sys.argv[1])
    active = json.loads(ACTIVE.read_text())
    assert active["commit"] == E2_COMMIT and active["approval_id"].endswith("-13"), "production is not -13 / e2"
    e2_argv = active["argv"]
    assert FLAG[0] not in e2_argv
    ref = json.loads(E2_REF.read_text())
    short_ref, long_ref = ref["results"]["short"], ref["results"]["long"]
    assert short_ref["backend_cache_rows"] == rows(512) and long_ref["backend_cache_rows"] == rows(512, 7745)

    prereg = {
        "schema": "ft_prereg_release/v1",
        "id": "PREREG_RELEASE_E3",
        "created_at": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        "author": "main session freetoken-06",
        "user_authority": "2026-10-12 morning, user: 'OK，参数上生产' (--prefill-anchor-cut-min-tokens 32768)",
        "sealed_before_any_e3_data": True,
        "build": {
            "branch": "release/e3 (new, local only, never pushed; release/e2 untouched)",
            "commit": E3_COMMIT, "parent": E2_COMMIT + " = release/e2 = current production",
            "diff": "6 files +151/-2: config.py, prefill.py, scheduler.py, args.py + 2 tests (task B candidate, unchanged)",
            "worktree": "/data2/FreeToken/wt/release-e3",
            "extensions_regular_file_copies_of_release_e2": EXTENSIONS,
        },
        "argv": {"e2": e2_argv, "e3": e2_argv + FLAG, "rule": "e3 = e2 argv with exactly FLAG appended; nothing else differs"},
        "q1_cold_smoke": {
            "service": "one fresh e3 service, harness endpoint 127.0.0.1:8123 (only --host/--port differ from e3 argv); "
                       "the first two requests are smoke short then long via r066 collect_one, no warmup",
            "short": {
                "backend_cache_rows": rows(512),
                "usage": {"prompt_tokens": 512, "completion_tokens": 128, "total_tokens": 640},
                "finish_reason": "length",
                "sha256": short_ref["sha256"],
                "basis": ["segment_sim_v2 thresh32k gives [512], same as prod (smoke_thresh_sim_out.txt)",
                          "task B T16-lite: N=0 path bit-identical to e2 on 20 payloads",
                          "task B seed_real/00 (cold, segmentation unchanged): C_A1 and C_B1 outputs identical"],
                "on_mismatch": "build or argv is wrong: do not deploy",
            },
            "long": {
                "backend_cache_rows": rows(8257),
                "usage": {"prompt_tokens": 8257, "completion_tokens": 128, "total_tokens": 8385},
                "finish_reason": "length",
                "sha256": None,
                "sha256_report_only": {"e2": long_ref["sha256"],
                                       "note": "segmentation changes [512,7745] -> [8257]; task B T2/00 (cold, cut->no cut) "
                                               "kept identical 32-token output, but 128 tokens are not predicted"},
                "basis": ["segment_sim_v2 reproduces -13 serve.log [512, 7745] for prod; thresh32k gives [8257]"],
            },
        },
        "r_production_smoke": "the e3 package smoke must reproduce Q1 exactly: backend_cache_rows, usage, finish_reason, sha256 "
                              "for short and long (task B G3: thresh arm 20/20 rounds identical across two services)",
        "p_post_checks": ["serve.log 'Parsed arguments' has prefill_anchor_cut_min_tokens=32768",
                          "production.active.json commit == " + E3_COMMIT + " and argv == argv.e3",
                          "health status ok, maintenance serving"],
        "routing": {
            "q1_any_check_fails": "do not deploy; restore e2 with restore14",
            "r_smoke_fails_or_second_invalid": "stop e3; restore e2 with restore14; never start ROLLBACK184 from the e3 package",
            "p_check_fails": "stop e3; restore e2 with restore14",
            "restore14_smoke_fails": "restore14's own frozen path (stop, ROLLBACK184), then stop all GPU work",
        },
        "report_only_after_release": ["OOM / worker-exit markers in serve.log until 2026-10-13T09:00+08:00",
                                      "warm rounds (cached>0): number of prefill rows; rounds with remain<=32768 must be 1 row",
                                      "no TTFT claim from uncontrolled traffic"],
        "disclosures": [
            "output text can differ from e2 (task B, C_A1 vs C_B1 with max_tokens 32: 15/20 rounds differ, incl. 3 of the 4 "
            "rounds whose segmentation is unchanged (T2/02, 03, 09), via cached-state numerics; T2/00 and seed_real/00, 05 "
            "identical); no approximation; same version reproduces bit-exactly (G3 20/20)",
            "E1 root cause unproven; thresh arms: 0 OOM over 2 services x 20 rounds incl. 87-95K; 95K cold untested",
            "equivalence gate covers layer-major prefill (the production configuration) only",
        ],
        "sources": {"e2_reference_sha256": hashlib.sha256(E2_REF.read_bytes()).hexdigest(),
                    "production_active_sha256": hashlib.sha256(ACTIVE.read_bytes()).hexdigest()},
    }
    with out.open("x", encoding="utf-8") as handle:
        json.dump(prereg, handle, ensure_ascii=False, indent=1)
        handle.write("\n")
    print(hashlib.sha256(out.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
