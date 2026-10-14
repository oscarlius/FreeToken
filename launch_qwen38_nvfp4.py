import paramiko
import time
from scripts.ssh_credentials import ssh_connect_kwargs

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(**ssh_connect_kwargs())

    print("=== Step 1: Force killing old processes and checking VRAM ===")
    kill_cmd = """
fuser -k -9 8095/tcp 2>/dev/null || true
pkill -9 -f 'sglang' 2>/dev/null || true
pkill -9 -f 'ft serve' 2>/dev/null || true
pkill -9 -f 'scheduler' 2>/dev/null || true
sleep 3
"""
    ssh.exec_command(kill_cmd)
    time.sleep(4)

    stdin, stdout, stderr = ssh.exec_command("nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits")
    used_vram = stdout.read().decode().strip()
    print(f"Current VRAM used: {used_vram} MiB")

    print("\n=== Step 2: Creating and launching FreeToken server script ===")
    launch_script = """#!/bin/bash
export PATH=/usr/local/cuda-13.0/bin:/data2/FreeToken/venv/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-13.0/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
export VIRTUAL_ENV=/data2/FreeToken/venv
export PYTHONUNBUFFERED=1

numactl --cpunodebind=0,1 --interleave=all \
  /data2/FreeToken/venv/bin/ft serve \
  --model-path /data2/model/Qwen3.8-Flash-Next-NVFP4 \
  --served-model-name Qwen3.8-Flash-Next-NVFP4 \
  --host 0.0.0.0 \
  --port 8095 \
  --cors-origins '*' \
  --memory-ratio 0.88 \
  --moe-cache-auto \
  --moe-prefill-hit-d2d \
  --ple-backend pinned \
  --moe-strategy offload \
  --nvfp4-backend triton \
  --max-running-requests 4 \
  --cuda-graph-max-bs 4 \
  --kv-reserve-tokens 32768 \
  --max-seq-len-override 32768 \
  --max-prefill-length 4096 \
  --enable-special-token-ckpt \
  --tool-call-parser qwen3_coder \
  --reasoning-parser qwen3 > /data2/FreeToken/qwen38_nvfp4.log 2>&1 &
echo $!
"""
    ssh.exec_command("cat << 'EOF' > /data2/FreeToken/start_qwen38_nvfp4.sh\n" + launch_script + "\nEOF\nchmod +x /data2/FreeToken/start_qwen38_nvfp4.sh")
    
    stdin, stdout, stderr = ssh.exec_command("/data2/FreeToken/start_qwen38_nvfp4.sh")
    pid = stdout.read().decode().strip()
    print(f"Server launched in background with PID: {pid}")

    print("\n=== Step 3: Monitoring startup log ===")
    ready = False
    for i in range(45):
        time.sleep(3)
        stdin, stdout, stderr = ssh.exec_command("tail -n 20 /data2/FreeToken/qwen38_nvfp4.log")
        log_snippet = stdout.read().decode()
        print(f"\n--- [Wait {(i+1)*3}s] Log snapshot ---")
        print(log_snippet)
        
        # Check if health endpoint responds
        stdin, stdout, stderr = ssh.exec_command("curl -s http://127.0.0.1:8095/v1/models || true")
        res = stdout.read().decode()
        if "Qwen3.8" in res or "object" in res:
            print("\n>>> SERVICE IS FULLY READY ON PORT 8095! <<<")
            print("Response:", res)
            ready = True
            break
            
        # Check if process died
        stdin, stdout, stderr = ssh.exec_command(f"kill -0 {pid} 2>/dev/null && echo 'ALIVE' || echo 'DEAD'")
        status = stdout.read().decode().strip()
        if status == "DEAD":
            print("\n[ERROR] Server process died! Full log:")
            stdin, stdout, stderr = ssh.exec_command("cat /data2/FreeToken/qwen38_nvfp4.log")
            print(stdout.read().decode())
            break

    ssh.close()

if __name__ == '__main__':
    main()
