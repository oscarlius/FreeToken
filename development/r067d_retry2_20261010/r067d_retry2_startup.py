"""R067d retry2 service entrypoint with task-owned source pins."""
from __future__ import annotations
import hashlib, importlib.util, json, os, subprocess, sys
from pathlib import Path

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def pin_file(path: Path, expected: str) -> None:
    assert path.is_file() and not path.is_symlink(), path
    assert sha(path) == expected, path

def pin_worktree() -> None:
    root=Path(os.environ['FT_DEV_R067D_WORKTREE']); commit=os.environ['FT_DEV_R067D_WORKTREE_COMMIT']
    assert root.is_dir() and (root/'python/freetoken/engine/engine.py').is_file()
    assert subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()==commit
    assert not subprocess.check_output(['git','-C',str(root),'status','--porcelain','--untracked-files=all'],text=True)
    pin_file(root/'python/freetoken/engine/engine.py',os.environ['FT_DEV_R067D_ENGINE_SHA256'])
    for relative, expected in json.loads(os.environ['FT_DEV_R067D_IMPORT_PINS']).items():
        pin_file(root/relative,expected)
    sys.path.insert(0,str(root/'python'))

def install_observer() -> None:
    source=Path(os.environ['FT_DEV_R067D_OBSERVER_SOURCE'])
    pin_file(source,os.environ['FT_DEV_R067D_OBSERVER_SHA256'])
    pin_file(Path(__file__),os.environ['FT_DEV_R067D_STARTUP_SHA256'])
    spec=importlib.util.spec_from_file_location('r067d_retry2_observer',source); assert spec and spec.loader
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); module.startup()

pin_worktree(); install_observer()
if __name__=='__main__':
    from freetoken.cli import main
    sys.argv=['ft',*sys.argv[1:]]; main()