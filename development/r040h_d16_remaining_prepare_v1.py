"""Executable CPU preparation entry for the R040h warm2 + interleave6 retry."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from r040h_d16_runtime_prepare_v1 import RID, assemble_runtime, retained_proof, source_plan


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--retained-proof", type=Path, required=True)
    parser.add_argument("--prepare-runtime", type=Path)
    args = parser.parse_args(argv)
    # Always validate independent R bindings before creating an executable copy.
    retained_proof(args.retained_proof)
    if args.prepare_runtime is None:
        print(json.dumps(source_plan(), sort_keys=True))
        return source_plan()
    return assemble_runtime(args.prepare_runtime, args.retained_proof)


if __name__ == "__main__":
    main()
