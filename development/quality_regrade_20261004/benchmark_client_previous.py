#!/usr/bin/env python3
"""
Comprehensive Inference Framework Benchmark & Quality Client
Standardized for Gemini execution against FreeToken & ExLlamaV3.
Addresses:
1. Complete separation of reasoning_content vs content.
2. Exact token counting via AutoTokenizer.
3. Realistic TTFT (first token) and TTFT_content (first content token).
4. Full validation for all 60 test questions (no generic default passes).
5. Increased max_tokens budget (768) so reasoning models are not length-truncated.
"""

import os
import sys
import time
import json
import requests
import tempfile
import subprocess
import concurrent.futures

API_BASE = os.environ.get("FT_API_BASE", "http://127.0.0.1:8095/v1")
MODEL_NAME = os.environ.get("FT_MODEL_NAME", "Qwen3.8-Flash-Next-NVFP4")
RUN_DIR = os.environ.get("FT_RUN_DIR", "/data2/_shared/runs/run_20260930_gemini")

os.makedirs(RUN_DIR, exist_ok=True)

# Try loading tokenizer for exact token counting
TOKENIZER = None
try:
    from transformers import AutoTokenizer
    for tp in ["/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay", "/data2/model/Qwen3.8-Flash-Next-NVFP4"]:
        if os.path.exists(tp):
            TOKENIZER = AutoTokenizer.from_pretrained(tp, trust_remote_code=True)
            break
except Exception:
    TOKENIZER = None

def log_msg(msg):
    t_str = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{t_str}] {msg}", flush=True)

def wait_for_server(timeout=300):
    log_msg(f"Waiting for server at {API_BASE}/models to become healthy...")
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = requests.get(f"{API_BASE}/models", timeout=3)
            if r.status_code == 200:
                # Ping chat completions to ensure loading is complete (not 503)
                r_chat = requests.post(
                    f"{API_BASE}/chat/completions",
                    json={"model": MODEL_NAME, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1},
                    timeout=5
                )
                if r_chat.status_code == 200:
                    log_msg("Server is healthy and ready to serve chat requests.")
                    return True
        except Exception:
            pass
        time.sleep(3)
    log_msg("Timed out waiting for server.")
    return False

def call_chat_stream(messages, max_tokens=768, temperature=0.0):
    url = f"{API_BASE}/chat/completions"
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
        "stream_options": {"include_usage": True}
    }
    
    t0 = time.time()
    t_first_token = None
    t_first_content = None
    thinking_chunks = []
    content_chunks = []
    finish_reason = None
    in_tokens = 0
    out_tokens_usage = 0
    
    try:
        with requests.post(url, json=payload, stream=True, timeout=120) as r:
            if r.status_code != 200:
                return "", "", 0, 0, time.time() - t0, 0, 0, 0, "error", f"HTTP {r.status_code}: {r.text[:200]}"
            
            for line in r.iter_lines():
                if not line:
                    continue
                line_str = line.decode("utf-8")
                if line_str.startswith("data: "):
                    data_str = line_str[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                    except Exception:
                        continue
                    
                    usage = data.get("usage")
                    if usage:
                        in_tokens = usage.get("prompt_tokens", in_tokens)
                        out_tokens_usage = usage.get("completion_tokens", out_tokens_usage)
                        
                    choices = data.get("choices", [])
                    if choices:
                        choice = choices[0]
                        if choice.get("finish_reason"):
                            finish_reason = choice["finish_reason"]
                        delta = choice.get("delta", {})
                        think = delta.get("reasoning_content", "")
                        text = delta.get("content", "")
                        if think:
                            if t_first_token is None:
                                t_first_token = time.time()
                            thinking_chunks.append(think)
                        if text:
                            if t_first_token is None:
                                t_first_token = time.time()
                            if t_first_content is None:
                                t_first_content = time.time()
                            content_chunks.append(text)
                            
        t_end = time.time()
        total_latency = t_end - t0
        full_content = "".join(content_chunks).strip()
        full_thinking = "".join(thinking_chunks).strip()
        
        ttft_first_token = (t_first_token - t0) if t_first_token else total_latency
        ttft_content = (t_first_content - t0) if t_first_content else total_latency
        
        if TOKENIZER is not None:
            think_tok = len(TOKENIZER.encode(full_thinking)) if full_thinking else 0
            content_tok = len(TOKENIZER.encode(full_content)) if full_content else 0
        else:
            # Fallback estimation
            think_tok = len(thinking_chunks)
            content_tok = len(content_chunks)
            
        total_tok = out_tokens_usage if out_tokens_usage > 0 else (think_tok + content_tok)
        
        return full_content, full_thinking, ttft_content, ttft_first_token, total_latency, in_tokens, content_tok, think_tok, finish_reason or "stop", None
    except Exception as e:
        return "", "", 0, 0, time.time() - t0, 0, 0, 0, "error", str(e)

def grade_response(q, content, thinking="", finish_reason="stop"):
    cat = q["category"]
    res = content.strip()
    
    if not res:
        if finish_reason == "length":
            return False, "Failed: Truncated in thinking phase before answer could start"
        return False, f"Failed: Empty content (finish_reason={finish_reason})"
        
    if cat == "chinese_extraction":
        exp = q["expected"]
        score = 0
        total = len(exp)
        for k, v in exp.items():
            if isinstance(v, list):
                if any(sub_v in res for sub_v in v):
                    score += 1
            elif isinstance(v, str):
                check_v = v.replace("元", "").replace(" ", "").split("/")[0]
                if check_v in res.replace(" ", ""):
                    score += 1
        passed = (score >= total * 0.75)
        return passed, f"Extraction matched {score}/{total} entities"
        
    elif cat == "structured_tool":
        json_str = res
        if "```json" in res:
            parts = res.split("```json")
            json_str = parts[-1].split("```")[0].strip()
        elif "```" in res:
            parts = res.split("```")
            json_str = parts[-1].split("```")[0].strip()
        else:
            s_idx = res.find("{")
            e_idx = res.rfind("}")
            if s_idx != -1 and e_idx != -1 and e_idx > s_idx:
                json_str = res[s_idx:e_idx+1].strip()
                
        try:
            parsed = json.loads(json_str)
            keys = q.get("schema_keys", [])
            missing = [k for k in keys if k not in parsed]
            if not missing:
                return True, "Valid JSON matching required schema"
            else:
                return False, f"JSON missing required keys: {missing}"
        except Exception as e:
            return False, f"Failed to parse JSON: {e}"
            
    elif cat == "code_autotest":
        code_str = res
        if "```python" in res:
            parts = res.split("```python")
            code_str = parts[-1].split("```")[0].strip()
        elif "```" in res:
            parts = res.split("```")
            code_str = parts[-1].split("```")[0].strip()
            
        full_code = f"{code_str}\n\n{q['test_code']}\n"
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tf:
            tf.write(full_code)
            tpath = tf.name
            
        try:
            proc = subprocess.run(["python3", tpath], capture_output=True, text=True, timeout=5)
            passed = (proc.returncode == 0)
            reason = "Auto test assertions passed" if passed else f"Assertion/syntax error: {proc.stderr[:160]}"
        except subprocess.TimeoutExpired:
            passed = False
            reason = "Test execution timed out (5s)"
        except Exception as e:
            passed = False
            reason = f"Execution error: {e}"
        finally:
            if os.path.exists(tpath):
                os.remove(tpath)
        return passed, reason
        
    elif cat == "long_multiturn":
        target = q.get("target_needle")
        if target:
            passed = (target.lower() in res.lower())
            return passed, f"Needle '{target}' found: {passed}"
            
        neg = q.get("negative_constraints")
        if neg:
            violated = [n for n in neg if n in res]
            passed = (len(violated) == 0)
            return passed, f"Negative constraints violated: {violated}"
            
        expected_order = q.get("expected_order")
        if expected_order:
            indices = [res.find(item) for item in expected_order]
            if any(idx == -1 for idx in indices):
                missing = [expected_order[i] for i, idx in enumerate(indices) if idx == -1]
                return False, f"Order check failed, missing items: {missing}"
            is_sorted = all(indices[i] <= indices[i+1] for i in range(len(indices)-1))
            return is_sorted, f"Descending order check: {is_sorted}"
            
        target_context = q.get("target_context")
        if target_context:
            candidates = [c.strip() for c in target_context.split("/")]
            matched = [c for c in candidates if c in res]
            return len(matched) > 0, f"Target context matched: {matched}"
            
        exact_format = q.get("exact_format")
        if exact_format:
            passed = exact_format in res
            return passed, f"Format requirement '{exact_format}' present: {passed}"
            
        max_words = q.get("max_words_per_point")
        if max_words:
            lines = [l.strip() for l in res.split("\n") if l.strip() and l.strip()[0].isdigit()]
            if not lines:
                return False, "Failed to format as numbered list"
            long_lines = [l for l in lines if len(l) > max_words + 5]
            passed = (len(long_lines) == 0)
            return passed, f"Max words per point check (violations: {len(long_lines)})"

    return False, "Unrecognized test type or unvalidated question"

def run_phase3_quality(model_id, prompt_file):
    log_msg(f"=== Starting Phase 3: 60-Question Quality Suite for {model_id} ===")
    with open(prompt_file, "r", encoding="utf-8") as f:
        prompts = json.load(f)
        
    quality_out = os.path.join(RUN_DIR, f"quality_results_{model_id}.jsonl")
    f_out = open(quality_out, "w", encoding="utf-8")
    
    passed_cnt = 0
    total_cnt = len(prompts)
    category_stats = {}
    
    for idx, q in enumerate(prompts):
        cat = q["category"]
        if cat not in category_stats:
            category_stats[cat] = {"passed": 0, "total": 0}
        category_stats[cat]["total"] += 1
        
        msg = [{"role": "user", "content": q["prompt"]}]
        # Generous token budget to allow deep reasoning + complete answer
        max_tok = 768
        content, thinking, ttft_content, ttft_thought, lat, in_tok, out_tok, think_tok, finish, err = call_chat_stream(msg, max_tokens=max_tok)
        
        if err:
            passed = False
            detail = f"Call error: {err}"
        else:
            passed, detail = grade_response(q, content, thinking=thinking, finish_reason=finish)
            
        if passed:
            passed_cnt += 1
            category_stats[cat]["passed"] += 1
            
        record = {
            "model_id": model_id,
            "question_id": q["id"],
            "category": cat,
            "passed": passed,
            "detail": detail,
            "in_tokens": in_tok,
            "content_tokens": out_tok,
            "thinking_tokens": think_tok,
            "ttft_thought_s": round(ttft_thought, 3),
            "ttft_content_s": round(ttft_content, 3) if ttft_content else None,
            "latency_s": round(lat, 3),
            "finish_reason": finish,
            "response": content,
            "thinking": thinking
        }
        f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
        f_out.flush()
        
        status_sym = "PASS" if passed else "FAIL"
        log_msg(f"[{idx+1}/{total_cnt}] {q['id']} ({cat}): [{status_sym}] | {detail} | Toks: {think_tok} think / {out_tok} content | Lat: {lat:.2f}s")
        
    f_out.close()
    acc = passed_cnt / total_cnt
    log_msg(f"Quality test finished! Passed: {passed_cnt}/{total_cnt} ({acc*100:.1f}%)")
    for cat, s in category_stats.items():
        log_msg(f" - {cat}: {s['passed']}/{s['total']} ({s['passed']/s['total']*100:.1f}%)")
        
    return {
        "passed_cnt": passed_cnt,
        "total_cnt": total_cnt,
        "accuracy": acc,
        "category_stats": category_stats
    }

def run_benchmark_cell(model_id, prompt_text, target_len_desc, concurrency, num_requests=6, max_out=384):
    log_msg(f"Running benchmark cell: target={target_len_desc}, concurrency={concurrency}, num_reqs={num_requests}...")
    
    # Warmup
    log_msg("Sending 1 warmup request...")
    call_chat_stream([{"role": "user", "content": prompt_text}], max_tokens=64)
        
    records = []
    def worker(req_id):
        prompt_var = f"{prompt_text}\n[Req: {req_id} - {time.time()}]"
        content, thinking, ttft_c, ttft_t, lat, in_tok, out_tok, think_tok, finish, err = call_chat_stream(
            [{"role": "user", "content": prompt_var}], max_tokens=max_out
        )
        total_out = out_tok + think_tok
        dec_tok_s = (total_out) / (lat - ttft_t) if (lat > ttft_t and total_out > 0) else (total_out / lat if lat > 0 else 0)
        return {
            "req_id": req_id,
            "in_tokens": in_tok,
            "content_tokens": out_tok,
            "thinking_tokens": think_tok,
            "total_tokens": total_out,
            "ttft_thought_s": round(ttft_t, 3),
            "ttft_content_s": round(ttft_c, 3) if ttft_c else None,
            "latency_s": round(lat, 3),
            "decode_tok_s": round(dec_tok_s, 2),
            "error": err
        }
        
    t_start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(worker, i) for i in range(num_requests)]
        for f in concurrent.futures.as_completed(futures):
            records.append(f.result())
    t_total = time.time() - t_start
    
    valid = [r for r in records if r["error"] is None]
    ttfts = [r["ttft_thought_s"] for r in valid]
    lats = [r["latency_s"] for r in valid]
    dec_speeds = [r["decode_tok_s"] for r in valid]
    total_out_tok = sum(r["total_tokens"] for r in valid)
    
    median_ttft = sorted(ttfts)[len(ttfts)//2] if ttfts else 0
    median_lat = sorted(lats)[len(lats)//2] if lats else 0
    median_dec = sorted(dec_speeds)[len(dec_speeds)//2] if dec_speeds else 0
    throughput = total_out_tok / t_total if t_total > 0 else 0
    
    log_msg(f"Cell result: Median TTFT={median_ttft:.2f}s, Median Decode={median_dec:.2f} tok/s, Total Throughput={throughput:.2f} tok/s, Completed={len(valid)}/{num_requests}")
    return {
        "target": target_len_desc,
        "concurrency": concurrency,
        "num_requests": num_requests,
        "completed": len(valid),
        "median_ttft_s": round(median_ttft, 3),
        "median_latency_s": round(median_lat, 3),
        "median_decode_tok_s": round(median_dec, 2),
        "total_throughput_tok_s": round(throughput, 2),
        "records": records
    }

if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "phase3"
    mid = sys.argv[2] if len(sys.argv) > 2 else MODEL_NAME
    
    if action == "wait":
        if not wait_for_server():
            sys.exit(1)
    elif action == "phase3":
        pf = sys.argv[3] if len(sys.argv) > 3 else "/data2/_shared/test_prompts_60.json"
        res = run_phase3_quality(mid, pf)
        print(json.dumps(res, indent=2, ensure_ascii=False))
    elif action == "phase4_perf":
        p2k = "在分布式大语言模型推理系统中，" + "专家权重的预取机制和缓存置换算法（如 LRU 与 Radix Tree）对整体推理吞吐起着至关重要的决定性作用。" * 30
        c1 = run_benchmark_cell(mid, p2k, "2K_concurr_1", concurrency=1, num_requests=6)
        c2 = run_benchmark_cell(mid, p2k, "2K_concurr_2", concurrency=2, num_requests=6)
        
        out_bench = os.path.join(RUN_DIR, f"perf_{mid}.json")
        with open(out_bench, "w", encoding="utf-8") as f:
            json.dump({"cell_2k_c1": c1, "cell_2k_c2": c2}, f, indent=2, ensure_ascii=False)
        log_msg(f"Performance benchmark saved to {out_bench}")
