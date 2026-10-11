"""Deprecated future entrypoint; delegates only to the current full-tail runtime."""
from pathlib import Path
import hashlib, runpy
TARGET = Path(__file__).with_name("t16_candidate_runner_full_tail.py")
TARGET_SHA256 = "0451e41128b4d1e0c73f892b375b9fbe70b30a9fbac46bc022500bd3c1b6d8b8"
if TARGET.is_symlink() or hashlib.sha256(TARGET.read_bytes()).hexdigest() != TARGET_SHA256:
    raise RuntimeError("current T16 full-tail runner is unavailable or changed")
runpy.run_path(str(TARGET), run_name="__main__")
