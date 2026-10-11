"""R067e entrypoint: load the pinned route startup in every spawn process."""
from __future__ import annotations
import hashlib, importlib.util, json, multiprocessing, os, subprocess, sys
from pathlib import Path

def _sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def _pin(path: Path, expected: str) -> None:
    if path.is_symlink() or not path.is_file() or _sha(path) != expected: raise RuntimeError(f"R067e source pin differs: {path}")
def _pin_worktree() -> Path:
    root=Path(os.environ["FT_DEV_R067E_WORKTREE"]); commit=os.environ["FT_DEV_R067E_WORKTREE_COMMIT"]
    if subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()!=commit: raise RuntimeError("R067e worktree commit differs")
    if subprocess.check_output(["git","-C",str(root),"status","--porcelain","--untracked-files=all"],text=True): raise RuntimeError("R067e worktree must be clean")
    _pin(root/"python/freetoken/engine/engine.py",os.environ["FT_DEV_R067E_ENGINE_SHA256"]); sys.path.insert(0,str(root/"python")); return root
def create_app():
    """Load the exact pinned FastAPI route module and return its real app object."""
    _pin_worktree(); source=Path(os.environ["FT_DEV_R067E_ROUTE_SOURCE"]); _pin(source,os.environ["FT_DEV_R067E_ROUTE_SOURCE_SHA256"]); sys.path.insert(0,str(source.parent))
    spec=importlib.util.spec_from_file_location("r067e_pinned_route_startup",source)
    if spec is None or spec.loader is None: raise RuntimeError("cannot load R067e route startup")
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    from freetoken.server import api_server
    routes=[(route.path,sorted(route.methods or ())) for route in api_server.app.routes]
    if ("/internal/t17/exact-ids",["POST"]) not in routes: raise RuntimeError("pinned exact-ID route was not registered")
    return api_server.app
app=create_app()
def _spawn_route_probe(queue) -> None:
    routes=[(route.path,sorted(route.methods or ())) for route in app.routes]
    queue.put({"route_present":("/internal/t17/exact-ids",["POST"]) in routes,"cuda_initialized":__import__("torch").cuda.is_initialized()})
if __name__ == "__main__":
    if sys.argv[1:] == ["--cpu-startup-probe"]:
        context=multiprocessing.get_context("spawn"); queue=context.Queue(); process=context.Process(target=_spawn_route_probe,args=(queue,)); process.start(); proof=queue.get(timeout=60); process.join(60)
        if process.exitcode!=0 or not proof["route_present"] or proof["cuda_initialized"]: raise RuntimeError("spawned R067e route probe failed")
        print(json.dumps({"schema":"ft_r067e_startup_spawn/v1","gpu_started":False,"route_present":True,"worker":proof},sort_keys=True))
    else:
        from freetoken.cli import main
        sys.argv=["ft",*sys.argv[1:]]; main()
