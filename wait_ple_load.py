import paramiko
import time
from scripts.ssh_credentials import ssh_connect_kwargs

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(**ssh_connect_kwargs())

    print("=== Monitoring FreeToken Weight Loading Progress ===")
    for i in range(60):
        time.sleep(5)
        stdin, stdout, stderr = ssh.exec_command("tail -n 15 /data2/FreeToken/qwen38_nvfp4.log")
        out = stdout.read().decode()
        print(f"--- [{(i+1)*5}s] ---")
        print(out)
        
        # Check if loading is finished
        if "WARMUP" in out or "Ready" in out or "Warmup" in out or "CUDA graph" in out or "100%" in out:
            # Check curl
            stdin, stdout, stderr = ssh.exec_command("""
curl -s -X POST http://127.0.0.1:8095/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "Qwen3.8-Flash-Next-NVFP4", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5}' || true
""")
            resp = stdout.read().decode()
            if "choices" in resp:
                print("\n>>> INFERENCE TEST SUCCEEDED! ENGINE IS FULLY ONLINE! <<<")
                print("Response:", resp)
                break

    ssh.close()

if __name__ == '__main__':
    main()
