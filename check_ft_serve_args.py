#!/usr/bin/env python3
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(**ssh_connect_kwargs(), timeout=10)

test_script = """
import inspect
from freetoken import cli
from scripts.ssh_credentials import ssh_connect_kwargs
print("CLI file:", cli.__file__)
with open(cli.__file__) as f:
    print(f.read()[:2000])
"""

stdin, stdout, stderr = ssh.exec_command(f"/data2/FreeToken/venv/bin/python -c '{test_script}'")
print(stdout.read().decode('utf-8'))
print(stderr.read().decode('utf-8'))
ssh.close()
