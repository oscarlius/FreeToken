"""Install the external D10 observer, then execute the real server program."""
from __future__ import annotations

import argparse
import os
import runpy
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--program", type=Path, required=True)
    parser.add_argument("args", nargs=argparse.REMAINDER)
    value = parser.parse_args()
    if not value.program.is_file() or value.program.is_symlink():
        raise RuntimeError("D10 server program is unavailable")
    if not os.environ.get("FT_D10_BRANCH_EVENT"):
        raise RuntimeError("D10 branch event path is required")
    from d10_branch_probe_v3 import install
    install()
    sys.argv = [str(value.program), *value.args]
    runpy.run_path(str(value.program), run_name="__main__")


if __name__ == "__main__":
    main()
