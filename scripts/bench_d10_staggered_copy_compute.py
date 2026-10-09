"""D10 CUDA feasibility harness for the two frozen R045 request shapes.

This is deliberately a *kernel-path feasibility harness*, not a model server
and not an AIPerf result.  It consumes exactly two request records, schedules
their pinned-host H2D copies and device matmuls through the D10 event/stream
prototype, and reports only that this CUDA path completed.  It must be run
only in the coordinator's GPU measurement window.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

from freetoken.moe.staggered_decode import StaggeredDecodeLane, StaggeredDecodePrototype


def load_two_requests(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if len(rows) != 2:
        raise ValueError(f"D10 requires exactly two R045 records, got {len(rows)}")
    if any(not isinstance(row.get("text"), str) or not row["text"] for row in rows):
        raise ValueError("D10 request records need non-empty text")
    return rows


def run(path: Path, *, layers: int, width: int, device: torch.device) -> dict:
    """Run the real CUDA copy/compute/event path once for the two input records.

    The host rows model distinct expert-bank source rows.  The two device
    staging rows are non-overlapping cache slots and the two vectors represent
    request-local decode state.  No model weight, sampler, HTTP server, or
    performance assertion is involved.
    """
    rows = load_two_requests(path)
    if device.type != "cuda" or not torch.cuda.is_available():
        raise RuntimeError("D10 feasibility harness requires an available CUDA device")
    if layers < 1 or width < 1:
        raise ValueError("layers and width must be positive")

    sources = [torch.randn((layers, width, width), pin_memory=True) for _ in rows]
    staging = torch.empty((2, width, width), device=device)
    states = [torch.randn((width,), device=device) for _ in rows]
    outputs = [torch.empty_like(state) for state in states]

    lanes = []
    for lane_id, _row in enumerate(rows):
        def copy(layer_id: int, slots: tuple[int, ...], *, lane_id=lane_id) -> None:
            staging[slots[0]].copy_(sources[lane_id][layer_id], non_blocking=True)

        def compute(_layer_id: int, slots: tuple[int, ...], *, lane_id=lane_id) -> None:
            torch.mv(staging[lane_id], states[lane_id], out=outputs[lane_id])
            states[lane_id].copy_(outputs[lane_id])

        lanes.append(StaggeredDecodeLane(
            name=f"r045-{lane_id}", cache_slots=(lane_id,), state_slots=(lane_id,),
            copy=copy, compute=compute,
        ))

    prototype = StaggeredDecodePrototype(device, enabled=True)
    done = prototype.run_step(layers, lanes)
    done.synchronize()  # one closure fence, outside the event hot path
    return {
        "status": "CUDA_PATH_COMPLETED_NOT_A_PERFORMANCE_RESULT",
        "requests": len(rows),
        "layers": layers,
        "width": width,
        "device": str(device),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-file", type=Path, required=True)
    parser.add_argument("--layers", type=int, default=2)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--device", default="cuda")
    parser.add_argument(
        "--development-fixture",
        action="store_true",
        help="required acknowledgement: this is not the target-Qwen/AIPerf D10 measurement",
    )
    args = parser.parse_args()
    if not args.development_fixture:
        raise SystemExit("REFUSED: D10 fixture is not a target-Qwen or AIPerf measurement")
    print(json.dumps(run(args.input_file, layers=args.layers, width=args.width,
                         device=torch.device(args.device)), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
