import paramiko
from scripts.ssh_credentials import ssh_connect_kwargs

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(**ssh_connect_kwargs())

    cmds = [
        "cat /data2/FreeToken/scripts/start_server.sh",
        "cat /data2/FreeToken/scripts/run_bench_speed.py"
    ]

    for cmd in cmds:
        print(f"=== {cmd} ===")
        stdin, stdout, stderr = ssh.exec_command(cmd)
        print(stdout.read().decode())

    ssh.close()

if __name__ == '__main__':
    main()
