#!/usr/bin/env python3
"""T00 execution draft: local static checks and an explicitly gated remote plan.

This file never opens SSH, starts a server, or allocates a GPU.  It documents
the exact remote preflight/collection contract that an approved runner must
implement only after its E2-base and gate-D00 evidence are supplied.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
PROBE = ROOT / "scripts" / "probe_ft_cold32k.py"
CKPT = ROOT / "scripts" / "ft_probe_ckpt_tax.py"
ARGS_DIFF = ROOT / "scripts" / "serve_args_diff.py"

# These names intentionally describe cases, never a configuration arm.  A
# whole-input comparison may therefore reuse a case id without encoding arm.
PLAN = {
    "production_d0_off": (("cold32", 4, 32052), ("short", 3, None), ("cold64", 2, 65412)),
    "d0_on": (("cold32", 2, 32052),),
    "ckpt_off": (("cold_process", 3, None), ("hot_per_process", 4, None)),
    "ckpt_on": (("cold_process", 3, None), ("hot_per_process", 4, None)),
}

UNRESOLVED_RUNTIME_CONTRACT = (
    "PROBE/CKPT must use /data2/FreeToken/scripts, not WT/scripts",
    "server process needs an explicit PYTHONPATH for the selected worktree",
    "v1/models is insufficient readiness; require health.status=ok plus sayok",
    "pid=$! names the wrapper shell while ft uses setsid; ownership/PGID must be proven",
    "each arm needs its own gate, expanded imports, strict Parsed-arguments diff, and readonly metadata",
    "cold raw-output declaration must avoid the prior unbound/raw-path failure",
    "max-prefill-length must retain the production 4096 contract; WIN is the window only",
    "D0-on versus checkpoint mode differences require an explicit approved matrix",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def check_sources() -> list[str]:
    errors: list[str] = []
    for path in (PROBE, CKPT, ARGS_DIFF):
        if not path.is_file():
            errors.append(f"missing required original probe: {path}")
    if errors:
        return errors
    probe = PROBE.read_text(encoding="utf-8", errors="replace")
    ckpt = CKPT.read_text(encoding="utf-8", errors="replace")
    if 'OUT_DIR = "/data2/FreeToken/runs/cold32k_20261002"' not in probe:
        errors.append("probe output location differs; do not assume raw-copy protocol")
    for required in ('"cached_tokens"', '"prompt_tokens"', '"cold_id"'):
        if required not in probe:
            errors.append(f"probe no longer emits required field {required}")
    if "REPS = 5" not in ckpt:
        errors.append("ckpt probe repetition count changed; re-review T00")
    return errors


def validate_probe_record(record: object, cold_id: str, target: int) -> None:
    """The checks a successful remote probe must pass before it is copied."""
    if not isinstance(record, dict):
        raise ValueError("record is not an object")
    if record.get("cold_id") != cold_id:
        raise ValueError("cold_id mismatch")
    if record.get("cached_tokens") != 0:
        raise ValueError("cold probe has cache hit")
    prompt = record.get("prompt_tokens")
    if not isinstance(prompt, int) or abs(prompt - target) >= 2000:
        raise ValueError("prompt_tokens outside target tolerance")
    if not isinstance(record.get("ttft_s"), (int, float)):
        raise ValueError("missing numeric ttft_s")


def self_test() -> None:
    good = {"cold_id": "case-01", "cached_tokens": 0, "prompt_tokens": 32052, "ttft_s": 1.0}
    validate_probe_record(good, "case-01", 32052)
    for bad in (
        {**good, "cached_tokens": 1}, {**good, "cold_id": "arm-on"},
        {**good, "prompt_tokens": 29900}, {**good, "ttft_s": None},
    ):
        try:
            validate_probe_record(bad, "case-01", 32052)
        except ValueError:
            continue
        raise AssertionError(f"bad record passed: {bad}")
    assert PLAN["ckpt_off"] == PLAN["ckpt_on"]
    assert PLAN["ckpt_on"][0][1] == 3 and PLAN["ckpt_on"][1][1] == 4


def render() -> str:
    return "# T00 RUNNER DRAFT — NOT EXECUTABLE\n# --run-remote always refuses.\n" + "\n".join(
        f"# TODO: {item}" for item in UNRESOLVED_RUNTIME_CONTRACT
    ) + "\n"
    return r'''#!/usr/bin/env bash
# Rendered candidate. It is executable only after required E2 evidence is passed.
set -euo pipefail
WT=/data2/FreeToken/wt/e2base; ROUND=/data2/_shared/runs/ft_rounds/E2-R000
RAW=/data2/FreeToken/runs/cold32k_20261002; LOCK=/data2/_shared/gpu.lock
CPUSET=1,3-47; WIN=73728; PORT=8095
export PATH=/usr/local/cuda-13.0/bin:/data2/FreeToken/venv/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-13.0/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
export VIRTUAL_ENV=/data2/FreeToken/venv
export PYTHONUNBUFFERED=1
FT=/data2/FreeToken/venv/bin/ft
PY=/data2/FreeToken/venv/bin/python
PROBE="$WT/scripts/probe_ft_cold32k.py"; CKPT="$WT/scripts/ft_probe_ckpt_tax.py"
DIFF="$WT/scripts/serve_args_diff.py"; : "${E2BASE_COMMIT:?}" "${T16_EVIDENCE:?}"
: "${REMOTE_PROBE_MD5:?}" "${REMOTE_CKPT_MD5:?}" "${T00_SHORT_TARGET:?}"
E2_TAG="E2-base@${E2BASE_COMMIT:0:7}"
die(){ echo "T00 FAIL: $*" >&2; exit 2; }
own="E2-R000 pid=$$"; tmp="${LOCK}.$$.tmp"; pid=""
cleanup(){ [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && kill -- -"$(ps -o pgid= -p "$pid" | tr -d ' ')" || :; [ -f "$LOCK" ] && grep -qxF "$own" "$LOCK" && rm -f "$LOCK"; rm -f "$tmp"; }
trap cleanup EXIT INT TERM

mkdir -p "$ROUND/preflight"; exec > >(tee "$ROUND/runner.log") 2>&1
git -C "$WT" rev-parse HEAD | grep -Fx "$E2BASE_COMMIT" || die bad-commit
git -C "$WT" describe --tags --exact-match | grep -Fx "$E2_TAG" || die no-E2-base
[ -z "$(git -C "$WT" status --porcelain --untracked-files=no)" ] || die dirty-tracked
grep -q 'gate-D00' "$T16_EVIDENCE" && grep -Eq 'PASS|passed|通过' "$T16_EVIDENCE" || die no-T16-proof
test -x "$FT" && "$FT" --help >/dev/null && command -v taskset && command -v numactl || die cpu-tools
md5sum "$PROBE" "$CKPT" | tee "$ROUND/preflight/probes.md5"; grep -q "$REMOTE_PROBE_MD5" "$ROUND/preflight/probes.md5" || die probe-md5; grep -q "$REMOTE_CKPT_MD5" "$ROUND/preflight/probes.md5" || die ckpt-md5
PYTHONPATH="$WT/python" "$PY" -c "import freetoken; assert freetoken.__file__ == '$WT/python/freetoken/__init__.py'; import freetoken.kernel" || die imports
nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | awk '$1>100{exit 1}' || die gpu-busy
ss -ltn | grep -q ":$PORT " && die port-busy; pgrep -af 'batch[0-9]+|replay|ft serve' && die competitor || :
printf '%s\n' "$own" > "$tmp"; ln "$tmp" "$LOCK" 2>/dev/null || die foreign-lock; rm -f "$tmp"
start(){ local arm=$1 ckpt=$2 d0=$3; local log="$ROUND/$arm/serve.log"; mkdir -p "$ROUND/$arm/raw_probe"; (cd "$WT"; [ "$d0" = on ] && export FT_DEV_D0=1 FT_DEV_D0_PATH="$ROUND/$arm/d0"; setsid taskset -c "$CPUSET" "$FT" serve --model-path /data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay --served-model-name Qwen3.8-Flash-Next-NVFP4 --host 127.0.0.1 --port "$PORT" --memory-ratio 0.88 --moe-cache-auto --moe-prefill-hit-d2d --ple-backend pinned --moe-strategy offload --quant-backend moe.nvfp4=triton --max-running-requests 2 --cuda-graph-max-bs 2 --kv-reserve-tokens "$WIN" --max-seq-len-override "$WIN" --max-prefill-length "$WIN" --prefill-layer-major $([ "$ckpt" = on ] && echo --enable-special-token-ckpt) >"$log" 2>&1) & pid=$!; for i in $(seq 1 360); do curl -fsS http://127.0.0.1:$PORT/v1/models >/dev/null && grep -q 'Parsed arguments' "$log" && return; kill -0 "$pid" || die serve-exited; sleep 5; done; die serve-timeout; }
stop(){ [ -n "$pid" ] || return; kill -0 "$pid" 2>/dev/null && kill -- -"$(ps -o pgid= -p "$pid" | tr -d ' ')" || :; wait "$pid" 2>/dev/null || :; pid=""; }
probe(){ local arm=$1 id=$2 target=$3 raw="$RAW/$id.json"; [ ! -e "$raw" ] || die existing-cold-id; "$PY" "$PROBE" "$id" "$target" 128 nothink >"$ROUND/$arm/$id.stdout" || die probe-rc; "$PY" -c "import json; r=json.load(open('$raw')); assert r['cold_id']=='$id' and r['cached_tokens']==0 and abs(r['prompt_tokens']-$target)<2000 and isinstance(r['ttft_s'],(int,float))" || die probe-fields; cp --preserve=mode,timestamps "$raw" "$ROUND/$arm/raw_probe/$id.json"; sha256sum "$raw" "$ROUND/$arm/raw_probe/$id.json" >>"$ROUND/$arm/raw_probe.sha256"; }
start prod off off; for n in 01 02 03 04; do probe prod "e2r000-case-$n" 32052; done; for n in 05 06 07; do probe prod "e2r000-case-$n" "$T00_SHORT_TARGET"; done; for n in 08 09; do probe prod "e2r000-case-$n" 65412; done; stop
start d0 on on; for n in 10 11; do probe d0 "e2r000-case-$n" 32052; done; grep -q 'seg_reason' "$ROUND/d0/d0_prefill.jsonl" || die missing-d0-metadata; stop
for mode in off on; do for p in 1 2 3; do arm="ckpt_${mode}_p$p"; start "$arm" "$mode" off; "$PY" "$CKPT" "$ROUND/$arm/ckpt.json" "$mode" >"$ROUND/$arm/ckpt.stdout" || die ckpt-rc; "$PY" -c "import json; r=json.load(open('$ROUND/$arm/ckpt.json')); assert r['reps']==5 and len(r['single'])==5 and len(r['multi'])==5" || die ckpt-fields; "$PY" -c "import json; r=json.load(open('$ROUND/$arm/ckpt.json')); json.dump({'cold_pair':0,'hot_pairs':[1,2,3,4],'single_cold':r['single'][0],'multi_cold':r['multi'][0],'multi_hot':r['multi'][1:]},open('$ROUND/$arm/classification.json','w'))"; stop; done; done
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render", action="store_true", help="print the remote runner outline")
    parser.add_argument("--self-test", action="store_true", help="run CPU-only validation tests")
    parser.add_argument("--run-remote", action="store_true", help="execute only on the verified Linux host")
    args = parser.parse_args()
    errors = check_sources()
    if args.render:
        if errors:
            print("STATIC-FAIL: " + "; ".join(errors), file=sys.stderr)
            return 2
        print(render())
        return 0
    if args.run_remote:
        print("REFUSED: T00 runner contract is incomplete; see --render TODOs.", file=sys.stderr)
        return 2
    print(f"probe_sha256={sha256(PROBE) if PROBE.exists() else 'MISSING'}")
    print(f"ckpt_sha256={sha256(CKPT) if CKPT.exists() else 'MISSING'}")
    print(f"probe_md5={md5(PROBE) if PROBE.exists() else 'MISSING'}")
    print(f"ckpt_md5={md5(CKPT) if CKPT.exists() else 'MISSING'}")
    print(f"plan={PLAN}")
    if args.self_test:
        self_test()
        print("CPU self-test passed")
    if errors:
        print("STATIC-FAIL: " + "; ".join(errors), file=sys.stderr)
        return 2
    print("Prepared only: rendered runner refuses execution without E2-base and gate-D00 evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
