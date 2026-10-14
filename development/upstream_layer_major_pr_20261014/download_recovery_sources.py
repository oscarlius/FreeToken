"""Download a read-only snapshot of current E3 controls for preparation/review."""
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "ops", HERE.parent / "r067c_retry2_production_control_20261009/ssh_ops.py"
)
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)
client = ops.connect()
try:
    sftp = client.open_sftp()
    sources = {
        'e3_package': '/data2/FreeToken/development/ophak_release_e3_20261012/release_e3_02',
        'frozen_ops': '/data2/FreeToken/runs/dev_release/release_e3_ops_v1_20261012/source/development/release_e2_ops_v2',
        'production': '/data2/FreeToken/runs/production/RELEASE-E3-20261012-02',
    }
    counts = {}
    for group, remote in sources.items():
        local = HERE/'recovery_source_snapshot'/group
        local.mkdir(parents=True, exist_ok=True)
        names = sftp.listdir(remote)
        selected = [n for n in names if n.endswith(('.py', '.json', '.md'))]
        for name in selected:
            target = local/name
            if target.exists():
                raise RuntimeError(f'Refuse overwrite: {target}')
            sftp.get(remote+'/'+name, str(target))
        counts[group] = len(selected)
    print(counts)
    sftp.close()
finally:
    client.close()
