"""Private candidate-only hook. It is inert unless both explicit env switches are set."""
import os
import sys
from pathlib import Path

if os.environ.get("FT_PR_OOM_ARTIFACTS"):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from gpu_fault_probe import injection_enabled, install_backend_factory_observer, install_engine_fault
    from freetoken.server import api_server

    install_backend_factory_observer(api_server, os.environ["FT_PR_OOM_ARTIFACTS"])
    if injection_enabled():
        from freetoken.engine.engine import Engine
        install_engine_fault(Engine, os.environ["FT_PR_OOM_ARTIFACTS"])
    # Reuse the existing private CPU-side observer; it reads materialized token IDs and
    # does not synchronize or inspect CUDA tensors.
    observer_root = Path(__file__).resolve().parents[2] / "upstream_layer_major_pr_20261014"
    if observer_root.is_dir():
        sys.path.insert(0, str(observer_root))
        from freetoken.message import DetokenizeMsg, PromptAdmittedMsg
        from freetoken.scheduler.io import SchedulerIOMixin
        from native_observer import install

        install(SchedulerIOMixin, DetokenizeMsg, os.environ["FT_PR_OOM_ARTIFACTS"], PromptAdmittedMsg)
