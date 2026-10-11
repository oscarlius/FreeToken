import socket
import sys

import pytest


@pytest.mark.parametrize('address', [('127.0.0.1', 8095), ('192.0.2.1', 80)])
def test_cpu_stage_cannot_contact_unregistered_service(address):
    guard = sys.modules.get('sitecustomize')
    if not getattr(guard, 'FT_CPU_FIXTURE_NETWORK_GUARD', False):
        pytest.skip('requires the frozen CPU-stage startup guard')
    with socket.socket() as client:
        with pytest.raises(PermissionError, match='unregistered endpoint'):
            client.connect(address)
        with pytest.raises(PermissionError, match='unregistered endpoint'):
            client.connect_ex(address)


def test_closed_fixture_listener_does_not_authorize_port_reuse():
    guard = sys.modules.get('sitecustomize')
    if not getattr(guard, 'FT_CPU_FIXTURE_NETWORK_GUARD', False):
        pytest.skip('requires the frozen CPU-stage startup guard')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0)); listener.listen()
        address = listener.getsockname()
        with socket.socket() as client:
            client.connect(address)
            connection,_ = listener.accept(); connection.close()
    # The retained Python object is still alive but its descriptor is closed.
    with socket.socket() as client:
        with pytest.raises(PermissionError, match='unregistered endpoint'):
            client.connect(address)
