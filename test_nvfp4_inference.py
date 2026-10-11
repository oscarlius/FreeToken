import json
import time
import urllib.request

def test_inference():
    print("=== Testing Streaming Inference on Qwen3.8-Flash-Next-NVFP4 (Port 8095) ===")
    url = "http://172.16.108.9:8095/v1/chat/completions"
    
    payload = {
        "model": "Qwen3.8-Flash-Next-NVFP4",
        "messages": [
            {"role": "system", "content": "You are a helpful AI assistant."},
            {"role": "user", "content": "请用Python写一个快速排序算法，并简要解释其时间复杂度。"}
        ],
        "temperature": 0.6,
        "max_tokens": 512,
        "stream": True
    }
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    
    t_start = time.time()
    t_first_token = None
    generated_tokens = 0
    full_content = ""
    full_reasoning = ""
    
    print("\n--- Stream Output Start ---")
    with urllib.request.urlopen(req, timeout=60) as resp:
        for line in resp:
            line_str = line.decode('utf-8').strip()
            if not line_str.startswith("data:"):
                continue
            data_str = line_str[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                reasoning = delta.get("reasoning_content", "")
                content = delta.get("content", "")
                
                if reasoning:
                    if t_first_token is None:
                        t_first_token = time.time()
                    generated_tokens += 1
                    full_reasoning += reasoning
                    print(reasoning, end="", flush=True)
                if content:
                    if t_first_token is None:
                        t_first_token = time.time()
                    generated_tokens += 1
                    full_content += content
                    print(content, end="", flush=True)
            except Exception as e:
                pass
                
    t_end = time.time()
    print("\n--- Stream Output End ---\n")
    
    ttft = (t_first_token - t_start) if t_first_token else 0
    decode_duration = (t_end - t_first_token) if t_first_token else 0
    tps = generated_tokens / decode_duration if decode_duration > 0 else 0
    
    print("=" * 60)
    print(f"TTFT (首字延迟)       : {ttft:.3f} s")
    print(f"生成的 Token 总数     : {generated_tokens} tokens")
    print(f"解码耗时 (Decode Time): {decode_duration:.3f} s")
    print(f"生成速率 (Throughput) : {tps:.2f} tokens/s")
    print("=" * 60)

if __name__ == '__main__':
    test_inference()
