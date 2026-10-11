#!/usr/bin/env python3
"""
Standalone FreeToken Load & Inference Test for GLM-5.3-Flash-NVFP4.
Tests single-card offload feasibility on 256GB RAM + 1x RTX 4090 (24GB).
Runs in /data2/FreeToken/venv.
"""

import os
import sys
import time
import json
import subprocess
import requests

MODEL_PATH = "/data2/model/GLM-5.3-Flash-NVFP4"
SERVED_NAME = "GLM-5.3-Flash-NVFP4"
PORT = 8095
SERVER_URL = f"http://127.0.0.1:{PORT}"
LOG_FILE = "/data2/FreeToken/glm5_standalone.log"
OUTPUT_JSON = "/data2/_shared/runs/run_20260930_gemini/glm5_standalone_test.json"

def log_msg(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def check_resources():
    mem_out = subprocess.check_output(["free", "-m"], text=True)
    lines = mem_out.strip().split("\n")
    mem_line = [p for p in lines[1].split() if p]
    total_mem = int(mem_line[1])
    avail_mem = int(mem_line[6])
    
    gpu_out = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=memory.total,memory.used,memory.free", "--format=csv,noheader,nounits"],
        text=True
    ).strip()
    gpu_total, gpu_used, gpu_free = [int(p.strip()) for p in gpu_out.split(",")]
    
    return {
        "host_total_mb": total_mem,
        "host_avail_mb": avail_mem,
        "gpu_total_mb": gpu_total,
        "gpu_used_mb": gpu_used,
        "gpu_free_mb": gpu_free
    }

def main():
    log_msg("=== Starting Independent GLM-5.3-Flash-NVFP4 Load Test ===")
    res_before = check_resources()
    log_msg(f"Initial Host Memory: {res_before['host_avail_mb']} MB available / {res_before['host_total_mb']} MB total")
    log_msg(f"Initial GPU VRAM: {res_before['gpu_free_mb']} MB free / {res_before['gpu_total_mb']} MB total")
    
    if res_before["host_avail_mb"] < 195000:
        log_msg(f"WARNING: Host available memory {res_before['host_avail_mb']} MB might be tight for 190.4GB GLM weights!")
        
    # Ensure port 8096 is clean
    subprocess.run(f"fuser -k -9 {PORT}/tcp 2>/dev/null || true", shell=True)
    time.sleep(2)
    
    cmd = [
        "numactl", "--cpunodebind=0,1", "--interleave=all",
        "/data2/FreeToken/venv/bin/ft", "serve",
        "--model-path", MODEL_PATH,
        "--served-model-name", SERVED_NAME,
        "--host", "0.0.0.0",
        "--port", str(PORT),
        "--cors-origins", "*",
        "--memory-ratio", "0.88",
        "--moe-cache-auto",
        "--moe-strategy", "offload",
        "--quant-backend", "moe.nvfp4=triton",
        "--max-running-requests", "1",
        "--cuda-graph-max-bs", "1",
        "--kv-reserve-tokens", "8192",
        "--tool-call-parser", "glm47",
        "--reasoning-parser", "glm"
    ]
    
    log_msg(f"Launching command: {' '.join(cmd)}")
    log_f = open(LOG_FILE, "w", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdout=log_f, stderr=subprocess.STDOUT)
    server_pid = proc.pid
    log_msg(f"GLM server launched with PID: {server_pid}")
    
    # Wait for server to load weights (typically ~4-5 minutes for 190GB)
    t0 = time.time()
    ready = False
    oom_killed = False
    error_snippet = ""
    
    for i in range(70): # up to 7 minutes
        time.sleep(6)
        elapsed = int(time.time() - t0)
        
        # Check if process died
        ret = proc.poll()
        if ret is not None:
            log_msg(f"Process terminated unexpectedly with exit code {ret} at {elapsed}s!")
            if ret == -9 or ret == 137:
                oom_killed = True
            break
            
        try:
            r = requests.get(f"{SERVER_URL}/v1/models", timeout=3)
            if r.status_code == 200:
                # Check chat endpoint
                r_chat = requests.post(
                    f"{SERVER_URL}/v1/chat/completions",
                    json={"model": SERVED_NAME, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1},
                    timeout=5
                )
                if r_chat.status_code == 200:
                    log_msg(f"GLM Server is FULLY READY and serving requests! (Elapsed: {elapsed}s)")
                    ready = True
                    break
                else:
                    log_msg(f"[{elapsed}s] /v1/models is 200, chat is {r_chat.status_code} (still preparing)...")
            else:
                log_msg(f"[{elapsed}s] /v1/models returned {r.status_code}...")
        except Exception:
            pass
            
    res_after = check_resources()
    log_f.close()
    
    # Read last 30 lines of log
    with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
        log_lines = f.readlines()
    last_log = "".join(log_lines[-40:])
    
    smoke_result = None
    if ready:
        log_msg("Sending smoke generation prompt to GLM-5.3-Flash...")
        prompt = "请简要解释什么是大语言模型的混合专家架构（MoE），以及它为什么能在推理时降低计算量？"
        t_req = time.time()
        try:
            resp = requests.post(
                f"{SERVER_URL}/v1/chat/completions",
                json={
                    "model": SERVED_NAME,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 256,
                    "temperature": 0.0
                },
                timeout=120
            )
            lat = time.time() - t_req
            if resp.status_code == 200:
                body = resp.json()
                msg = body["choices"][0]["message"]
                smoke_result = {
                    "success": True,
                    "latency_s": round(lat, 3),
                    "response": msg.get("content", ""),
                    "reasoning": msg.get("reasoning_content", "")
                }
                log_msg(f"Generation successful in {lat:.2f}s! Response length: {len(smoke_result['response'])}")
            else:
                smoke_result = {"success": False, "status_code": resp.status_code, "text": resp.text[:200]}
        except Exception as e:
            smoke_result = {"success": False, "error": str(e)}
            
    # Cleanup server
    log_msg("Terminating GLM server process...")
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()
    subprocess.run(f"fuser -k -9 {PORT}/tcp 2>/dev/null || true", shell=True)
    
    report = {
        "model": "GLM-5.3-Flash-NVFP4",
        "framework": "FreeToken",
        "weights_path": MODEL_PATH,
        "weights_size_gib": 190.40,
        "initial_resources": res_before,
        "loaded_resources": res_after,
        "ready": ready,
        "oom_killed": oom_killed,
        "time_to_ready_s": int(time.time() - t0) if ready else None,
        "smoke_generation": smoke_result,
        "last_log_snippet": last_log[-1500:]
    }
    
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    log_msg(f"Result saved to {OUTPUT_JSON}")
    print(json.dumps(report, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
