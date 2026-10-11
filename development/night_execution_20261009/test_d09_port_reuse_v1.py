"""Linux TCP lifecycle regression: TIME_WAIT permits reuse, LISTEN blocks it."""
import importlib.util
import socket
from pathlib import Path

import pytest


@pytest.mark.parametrize('packet,filename', [
    ('d09_t17_night_v1', 'd09_t17_runner_v7.py'),
    ('d09_replay_parent_night_v1', 'd09_replay_parent_v5.py'),
])
def test_time_wait_reuse_and_active_listener_exclusion(packet, filename):
    path = Path(__file__).resolve().parent.parent / packet / filename
    spec = importlib.util.spec_from_file_location(packet + '_port_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    reserve = (lambda port: module.reserve_pair((port, 0))) if hasattr(module, 'reserve_pair') else (lambda port: module.reserve_port_pair(port, 0))
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    listener.listen(1)
    try:
        with pytest.raises(OSError):
            reserve(port)
        with socket.create_connection(('127.0.0.1', port), timeout=2) as client:
            peer, _ = listener.accept()
            with peer:
                peer.shutdown(socket.SHUT_WR)
                assert client.recv(1) == b''
    finally:
        listener.close()
    # The accepted server endpoint actively closed and now owns TIME_WAIT.
    with socket.socket() as plain:
        with pytest.raises(OSError):
            plain.bind(('127.0.0.1', port))
    held = reserve(port)
    try:
        assert held[0].getsockname()[1] == port
    finally:
        for sock in held:
            sock.close()
