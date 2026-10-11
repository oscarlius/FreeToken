"""Create V2 without mutating the immutable V1 config or packet."""
from __future__ import annotations
import ast, hashlib, json
from pathlib import Path
from r067d_cpu_prep import HERE, RID

def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> None:
    v1 = HERE / "R067D_RETRY1_PREPARED_RUNNER_PACKET.json"
    cfg = HERE / "R067D_RETRY1_CONFIG_CPU_ONLY.json"
    packet = json.loads(v1.read_text())
    child = packet["child_source"]
    assert "import r067d_cpu_prep as r067d_tools" in child
    child = child.replace("import r067d_cpu_prep as r067d_tools", "import r067d_retry1_v2_tools as r067d_tools", 1)
    marker = "def start_prepared_service(service,env,log,*,probe=None,popen=None):"
    guard = '''def verify_runtime_environment(service,arm):
 assert Path(service['service_dir'])==arm and Path(service['cwd'])==arm
 assert service['argv'][5]==str(arm/'t17_d14_startup.py') and d07.argv_sha256(service['argv'])==service['argv_sha256']
 assert 'E2-R067c-d20-short-tail-retry1' not in json.dumps((service['argv'],service['env']),sort_keys=True)
 actual=r067d_tools.actual_environment(service)
 for key in ('FT_DEV_STATE_DUMP','FT_T17_INPUT_RECEIPTS','FT_T17_OBSERVATIONS','PYTHONPATH'): assert str(arm) in actual[key]
 return actual
'''
    assert child.count(marker) == 1
    child = child.replace(marker, guard + marker, 1)
    old = "for key in ('FT_DEV_STATE_DUMP','FT_T17_INPUT_RECEIPTS','FT_T17_OBSERVATIONS','PYTHONPATH'):assert str(arm) in service['env'][key]"
    assert child.count(old) == 1
    child = child.replace(old, "env=verify_runtime_environment(service,arm)", 1)
    # The child uses this same renderer immediately before Popen.
    assert "env.update(r067d_tools.actual_environment(service))" in child
    ast.parse(child)
    out = dict(packet)
    out.update(schema="ft_r067d_retry1_prepared_runner/v2", config_sha256=sha(cfg),
               helper_sha256=sha(HERE / "r067d_retry1_v2_tools.py"), child_source=child,
               supersedes_packet_sha256=sha(v1),
               change_scope="V2 fixes only child preflight/launch environment rendering: four env paths bind to new RID service_dir; immutable config, argv, inputs, criteria, ports, 10 services, 14 calls and default parsed hybrid_radix remain unchanged")
    (HERE / "R067D_RETRY1_PREPARED_RUNNER_PACKET_V2.json").write_text(json.dumps(out, sort_keys=True, indent=2) + "\n")

if __name__ == "__main__": main()
