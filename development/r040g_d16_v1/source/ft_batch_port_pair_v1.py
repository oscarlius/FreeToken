"""Allocate the API/TCPStore port pair required by the current R057/R058 batches.

This probes binds without listening or connecting. The sockets close before
service launch, so admission must still reject an eventual startup collision.
"""
from __future__ import annotations

import random
import socket
from pathlib import Path


def ephemeral_range() -> tuple[int, int]:
    path = Path('/proc/sys/net/ipv4/ip_local_port_range')
    return tuple(map(int, path.read_text().split())) if path.is_file() else (32768, 60999)


def probe_pair(port: int) -> None:
    if type(port) is not int or not 1024 <= port < 65535 or {port, port + 1} & {8095, 8099}:
        raise ValueError('invalid private API/TCPStore pair')
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as api:
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            api.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        api.bind(('0.0.0.0', port))
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as store:
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                store.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            store.bind(('0.0.0.0', port + 1))


def dynamic_port() -> int:
    low, high = ephemeral_range()
    rng = random.SystemRandom()
    for _ in range(64):
        port = rng.randrange(12000, 30000)
        if low <= port <= high or low <= port + 1 <= high:
            continue
        try:
            probe_pair(port)
        except OSError:
            continue
        return port
    raise RuntimeError('no free API/TCPStore pair outside the ephemeral range')


def port_receipt(port: int) -> dict:
    probe_pair(port)
    return {'api': port, 'tcpstore': port + 1, 'kernel_ephemeral_range': list(ephemeral_range()),
            'probe': 'simultaneous wildcard bind; no listen/connect',
            'reservation_held_at_service_start': False}
