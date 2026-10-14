import paramiko
from scripts.ssh_credentials import ssh_connect_kwargs

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(**ssh_connect_kwargs())

    cmd = "tail -n 25 /data2/FreeToken/qwen38_nvfp4.log"
    stdin, stdout, stderr = ssh.exec_command(cmd)
    print(stdout.read().decode())

    # test curl
    stdin, stdout, stderr = ssh.exec_command("""
curl -s -X POST http://127.0.0.1:8095/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "Qwen3.8-Flash-Next-NVFP4", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5}' || true
""")
    print("Curl response:", stdout.read().decode())

    ssh.close()

if __name__ == '__main__':
    main()
