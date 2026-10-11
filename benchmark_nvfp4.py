import requests
import time
import json

def run_test(prompt, name="Test", max_tokens=300):
    url = "http://172.16.108.9:8095/v1/chat/completions"
    payload = {
        "model": "Qwen3.8-Flash-Next-NVFP4",
        "messages": [
            {"role": "system", "content": "You are a professional assistant."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.6,
        "max_tokens": max_tokens,
        "stream": True
    }
    
    print(f"\n{'='*20} Running: {name} {'='*20}")
    t0 = time.time()
    t_first = None
    tokens = 0
    full_text = []
    
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
                content = delta.get("content", "") or delta.get("reasoning_content", "")
                if content:
                    if t_first is None:
                        t_first = time.time()
                    tokens += 1
                    full_text.append(content)
                    print(content, end="", flush=True)
            except Exception:
                pass
                
    t1 = time.time()
    ttft = (t_first - t0) if t_first else 0
    decode_time = (t1 - t_first) if t_first else 0
    tps = tokens / decode_time if decode_time > 0 else 0
    
    print(f"\n\n--- Metrics for {name} ---")
    print(f"TTFT (首字延迟)       : {ttft:.3f} s")
    print(f"生成的 Token 数       : {tokens} tokens")
    print(f"解码耗时 (Decode Time): {decode_time:.3f} s")
    print(f"解码速率 (Tokens/s)   : {tps:.2f} tokens/s")
    
    return {"name": name, "ttft": ttft, "tokens": tokens, "decode_time": decode_time, "tps": tps}

def main():
    benchmarks = [
        ("请写一个Python实现带有过期时间的LRU Cache类，包含get、put方法。", "Benchmark 1: 复杂代码生成", 350),
        ("一个长方形的长增加20%，宽减少10%，它的面积增加了百分之几？请一步一步给出详细推理过程。", "Benchmark 2: 数学推理", 250),
        ("简述大语言模型中MoE架构与Dense架构的优缺点，以及为什么在消费级单卡上部署需要权重卸载。", "Benchmark 3: 架构理论解析", 300)
    ]
    
    results = []
    for prompt, name, max_tokens in benchmarks:
        r = run_test(prompt, name, max_tokens)
        results.append(r)
        time.sleep(1)
        
    print("\n" + "="*60)
    print("=== Qwen3.8-Flash-Next-NVFP4 基准评测总览 ===")
    print(f"{'测试项':<30} | {'TTFT(s)':<8} | {'Tokens':<8} | {'速率(tok/s)':<12}")
    print("-" * 66)
    for r in results:
        print(f"{r['name']:<30} | {r['ttft']:<8.3f} | {r['tokens']:<8} | {r['tps']:<12.2f}")
    avg_tps = sum(r['tps'] for r in results) / len(results)
    avg_ttft = sum(r['ttft'] for r in results) / len(results)
    print("-" * 66)
    print(f"平均首字延迟 (Avg TTFT): {avg_ttft:.3f} s")
    print(f"平均解码速率 (Avg Throughput): {avg_tps:.2f} tokens/s")
    print("="*60)

if __name__ == '__main__':
    main()
