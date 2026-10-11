"""Non-executing seam for a later root-approved runner.

The service argv is rendered exactly once by r067d_cpu_prep.actual_argv.  A
future launcher must call this function immediately before the bind probe and
must not consume serialized argv as an independent authority.
"""
from pathlib import Path
from r067d_cpu_prep import actual_argv, actual_environment, probe_or_capture, replay_readiness, verify_service_binding

def prestart_service(service: dict, evidence_dir: Path) -> list[str]:
    verify_service_binding(service)
    argv, env = actual_argv(service), actual_environment(service)
    assert env['MASTER_PORT'] == str(service['port_pair']['tcpstore'])
    probe_or_capture((service['port_pair']['api'], service['port_pair']['tcpstore']), evidence_dir, 120)
    return argv

def require_replay_admission(raw_dir: Path) -> None:
    readiness = replay_readiness(raw_dir)
    assert readiness['gpu_admitted'], readiness['blocker']
