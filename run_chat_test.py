import requests
import time
import json

def main():
    url = "http://172.16.108.9:8095/v1/chat/completions"
    payload = {
        "model": "Qwen3.8-Flash-Next-NVFP4",
        "messages": [
            {"role": "system", "content": "You are a helpful coding assistant."},
            {"role": "user", "content": "请用Python写一个快速排序算法，并简要说明其时间复杂度。"}
        ],
        "temperature": 0.6,
        "max_tokens": 512,
        "stream": True
    }
    
    print("=== Sending Request to Qwen3.8-Flash-Next-NVFP4 on 8095 ===")
    t0 = time.time()
    t_first = None
    tokens = 0
    full_text = []
    full_thinking = []
    
    with requests.post(url, json=payload, stream=True, timeout=60) as r:
        for line in r.iter_lines():
            if not line:
                continue
            line_str = line.decode('utf-8')
            if not line_str.startswith("data: "):
                continue
            data_str = line_str[6:].strip()
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                delta = chunk["choices"][0]["delta"]
                think = delta.get("reasoning_content", "")
                content = delta.get("content", "")
                if think:
                    if t_first is None:
                        t_first = time.time()
                    tokens += 1
                    full_thinking.append(think)
                    print(think, end="", flush=True)
                if content:
                    if t_first is None:
                        t_first = time.time()
                    tokens += 1
                    full_text.append(content)
                    print(content, end="", flush=True)
            except Exception as e:
                pass
                
    t1 = time.time()
    print("\n\n" + "="*50)
    ttft = (t_first - t0) if t_first else 0
    decode_time = (t1 - t_first) if t_first else 0
    tps = tokens / decode_time if decode_time > 0 else 0
    print(f"TTFT (首字延迟)       : {ttft:.3f} s")
    print(f"生成的 Token 数       : {tokens} tokens")
    print(f"解码耗时 (Decode Time): {decode_time:.3f} s")
    print(f"生成速率 (Tokens/s)   : {tps:.2f} tokens/s")
    print("="*50)

if __name__ == '__main__':
    main()
