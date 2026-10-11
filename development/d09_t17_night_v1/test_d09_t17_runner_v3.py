import importlib.util
import socket
from pathlib import Path

import pytest

PATH = Path(__file__).with_name('d09_t17_runner_v3.py')
spec = importlib.util.spec_from_file_location('t17v3', PATH)
runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)


def test_pair_reservation_releases_both_ports():
    held = runner.reserve_pair((0, 0))
    ports = [s.getsockname()[1] for s in held]
    assert ports[0] != ports[1]
    runner.release_pair(held)
    for port in ports:
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', port))


def test_failed_second_port_bind_releases_first_port():
    with socket.socket() as occupied:
        occupied.bind(('127.0.0.1', 0)); port = occupied.getsockname()[1]
        with pytest.raises(OSError):
            runner.reserve_pair((0, port))
    # The first ephemeral socket from the failing attempt must already be closed.
    held = runner.reserve_pair((0, 0)); runner.release_pair(held)
