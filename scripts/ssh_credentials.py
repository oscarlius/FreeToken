"""Environment-backed SSH connection settings for FreeToken operational scripts."""

from __future__ import annotations

import os
from collections.abc import Mapping


class SSHConfigurationError(ValueError):
    """Raised when the required non-secret SSH connection settings are absent."""


def ssh_connect_kwargs(environment: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return Paramiko connection settings without exposing a password in source.

    ``FT_SSH_HOST`` and ``FT_SSH_USER`` are required. ``FT_SSH_PASSWORD`` is
    optional so Paramiko can use its existing SSH-agent and key-file behavior.
    """

    environment = os.environ if environment is None else environment
    missing = [
        name
        for name in ("FT_SSH_HOST", "FT_SSH_USER")
        if not environment.get(name)
    ]
    if missing:
        raise SSHConfigurationError(
            "Missing required SSH environment variable(s): " + ", ".join(missing)
        )

    connection = {
        "hostname": environment["FT_SSH_HOST"],
        "username": environment["FT_SSH_USER"],
    }
    password = environment.get("FT_SSH_PASSWORD")
    if password:
        connection["password"] = password
    return connection
