#!/usr/bin/env python3
import paramiko
from scripts.ssh_credentials import ssh_connect_kwargs

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(**ssh_connect_kwargs(), timeout=10)

stdin, stdout, stderr = ssh.exec_command("sed -n '65,110p' /data2/FreeToken/qwen38_nvfp4.log")
print(stdout.read().decode('utf-8'))
ssh.close()
