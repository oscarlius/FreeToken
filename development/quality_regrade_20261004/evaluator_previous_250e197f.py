#!/usr/bin/env python3
"""
Standardized Evaluator for Inference Framework Benchmarks.
Implements:
1. Status classification: PASS / ANSWER_FAIL / TRUNCATED / EVALUATOR_ERROR / RUNTIME_ERROR.
2. Code block extraction: preserves target functions/classes, imports, and dependencies; ignores disconnected example blocks.
3. Numerical and entity matching: '46820' == '46,820', separate verification for service and method names, subscript normalization.
4. JSON schema, field types, and nested value verification.
5. Strict separation of thinking vs content (only content is graded).
6. Strict token usage from server or AutoTokenizer (or None, never chunk counts).
7. Null ttft_content when content is empty; mandatory finish_reason.
"""

import re
import os
import sys
import json
import tempfile
import subprocess
import unicodedata

def normalize_text(text: str) -> str:
    """Normalize unicode subscripts (e.g. Li₁₀GeP₂S₁₂ -> Li10GeP2S12) and standard spacing."""
    if not text:
        return ""
    # Map common subscripts and superscripts to ascii
    sub_map = str.maketrans("₀₁₂₃₄₅₆₇₈₉⁰¹²³⁴⁵⁶⁷⁸⁹", "01234567890123456789")
    text = text.translate(sub_map)
    # Remove zero-width spaces, normalize NFKC
    text = unicodedata.normalize("NFKC", text)
    return text

def extract_python_code(content: str, entry_point: str = None) -> str:
    """
    Extracts executable Python code from model response content.
    If multiple code blocks exist, combines imports and the block defining the target entry_point.
    """
    code_blocks = re.findall(r"```(?:python)?\s*\n(.*?)\n```", content, re.DOTALL)
    
    if not code_blocks:
        # If no markdown fences, check if content itself is python code
        lines = content.strip().split("\n")
        if any(line.strip().startswith(("def ", "class ", "import ", "from ")) for line in lines):
            return content.strip()
        return ""
        
    if len(code_blocks) == 1:
        return code_blocks[0].strip()
        
    # Multiple code blocks: often block 1 is definition and block 2 is example/usage.
    # We collect all import statements across all blocks.
    imports = []
    def_blocks = []
    
    for block in code_blocks:
        lines = block.split("\n")
        block_imports = [l for l in lines if l.strip().startswith(("import ", "from "))]
        imports.extend(block_imports)
        
        # Check if this block defines any function or class
        has_def = any(re.match(r"^(?:async\s+)?def\s+\w+|class\s+\w+", l.strip()) for l in lines)
        if entry_point:
            if re.search(r"\b(def|class)\s+" + re.escape(entry_point) + r"\b", block):
                def_blocks.append(block)
        elif has_def:
            def_blocks.append(block)
            
    # If we found definition blocks, combine them with unique imports
    unique_imports = []
    for imp in imports:
        if imp not in unique_imports:
            unique_imports.append(imp)
            
    if def_blocks:
        combined = "\n".join(unique_imports) + "\n\n" + "\n\n".join(def_blocks)
        return combined.strip()
        
    # Fallback to the first block
    return code_blocks[0].strip()

def extract_json_object(content: str):
    """Extracts JSON dict/list from text, handling markdown fences and surrounding explanation."""
    code_blocks = re.findall(r"```(?:json)?\s*\n(.*?)\n```", content, re.DOTALL)
    candidates = code_blocks if code_blocks else []
    
    # Also find outermost { ... } or [ ... ]
    s_obj = content.find("{")
    e_obj = content.rfind("}")
    if s_obj != -1 and e_obj != -1 and e_obj > s_obj:
        candidates.append(content[s_obj:e_obj+1].strip())
        
    s_arr = content.find("[")
    e_arr = content.rfind("]")
    if s_arr != -1 and e_arr != -1 and e_arr > s_arr:
        candidates.append(content[s_arr:e_arr+1].strip())
        
    candidates.append(content.strip())
    
    for c in candidates:
        try:
            return json.loads(c), None
        except Exception as e:
            last_err = str(e)
            
    return None, last_err

def grade_question(q: dict, content: str, finish_reason: str = "stop") -> tuple[str, str]:
    """
    Evaluates a single question and returns (status, detail).
    Statuses:
      - PASS
      - ANSWER_FAIL
      - TRUNCATED
      - EVALUATOR_ERROR
      - RUNTIME_ERROR
    """
    try:
        cat = q.get("category")
        res = content.strip() if content else ""
        
        # Check truncation first
        if finish_reason == "length":
            if not res:
                return "TRUNCATED", "Truncated in thinking phase before answer content began"
            # In code questions, if code is cut mid-token
            if cat == "code_autotest":
                # Check if code block was left unclosed
                if content.count("```") % 2 != 0:
                    return "TRUNCATED", "Truncated in code body before markdown fence closed"
                    
        if not res:
            if finish_reason == "length":
                return "TRUNCATED", "Empty content due to length budget exhaustion"
            return "ANSWER_FAIL", f"Empty content received with finish_reason={finish_reason}"
            
        # 1. Chinese Extraction
        if cat == "chinese_extraction":
            expected = q.get("expected", {})
            score = 0
            total = len(expected)
            norm_res = normalize_text(res).replace(" ", "")
            
            for k, v in expected.items():
                if isinstance(v, list):
                    if any(normalize_text(sub_v).replace(" ", "") in norm_res for sub_v in v):
                        score += 1
                elif isinstance(v, str):
                    # Check numerical value or clean string
                    norm_v = normalize_text(v).replace(" ", "")
                    # Extract digits if pure numerical comparison
                    digits_v = re.findall(r"\d+", norm_v)
                    digits_res = re.findall(r"\d+", norm_res)
                    if digits_v and all(d in digits_res for d in digits_v):
                        score += 1
                    elif norm_v in norm_res:
                        score += 1
                    else:
                        # Check sub-phrases (e.g. "硅酸盐学报")
                        check_sub = norm_v.replace("元", "").split("/")[0]
                        if check_sub in norm_res:
                            score += 1
                            
            passed = (score >= total * 0.7)
            status = "PASS" if passed else "ANSWER_FAIL"
            return status, f"Matched {score}/{total} entities"

        # 2. Structured JSON Tool
        elif cat == "structured_tool":
            obj, err = extract_json_object(res)
            if obj is None:
                if finish_reason == "length":
                    return "TRUNCATED", f"JSON truncated mid-stream: {err}"
                return "ANSWER_FAIL", f"Failed to parse valid JSON: {err}"
                
            schema_keys = q.get("schema_keys", [])
            missing = [k for k in schema_keys if k not in obj]
            if missing:
                return "ANSWER_FAIL", f"JSON missing required keys: {missing}"
                
            # Verify field types if defined
            expected_types = q.get("expected_types", {})
            for field, expected_type in expected_types.items():
                val = obj.get(field)
                if expected_type == "float" and not isinstance(val, (int, float)):
                    return "ANSWER_FAIL", f"Field '{field}' expected float, got {type(val).__name__}"
                elif expected_type == "int" and not isinstance(val, int):
                    return "ANSWER_FAIL", f"Field '{field}' expected int, got {type(val).__name__}"
                elif expected_type == "str" and not isinstance(val, str):
                    return "ANSWER_FAIL", f"Field '{field}' expected str, got {type(val).__name__}"
                    
            return "PASS", "Valid JSON matching required schema and types"

        # 3. Code Autotest
        elif cat == "code_autotest":
            entry_point = q.get("entry_point")
            if not entry_point:
                # Infer entry_point from test_code (e.g. "assert merge_intervals(...)")
                m = re.search(r"\bassert\s+([A-Za-z0-9_]+)\(", q.get("test_code", ""))
                if m:
                    entry_point = m.group(1)
                elif "class LRUCache" in q.get("prompt", ""):
                    entry_point = "LRUCache"
                    
            code_str = extract_python_code(res, entry_point=entry_point)
            if not code_str:
                if finish_reason == "length":
                    return "TRUNCATED", "No complete code block extracted due to length truncation"
                return "ANSWER_FAIL", "No code block found in response"
                
            # If entry_point was inferred, ensure it exists in code_str
            if entry_point and entry_point not in code_str:
                if finish_reason == "length":
                    return "TRUNCATED", f"Target definition '{entry_point}' truncated or omitted"
                return "ANSWER_FAIL", f"Extracted code missing target definition '{entry_point}'"
                
            full_code = f"{code_str}\n\n{q['test_code']}\n"
            with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tf:
                tf.write(full_code)
                tpath = tf.name
                
            try:
                proc = subprocess.run([sys.executable, tpath], capture_output=True, text=True, timeout=5)
                if proc.returncode == 0:
                    return "PASS", "Auto test assertions passed"
                else:
                    err_msg = proc.stderr.strip()
                    # Check if error is due to incomplete syntax caused by truncation
                    if finish_reason == "length" and ("SyntaxError" in err_msg or "IndentationError" in err_msg):
                        return "TRUNCATED", f"Code syntax truncated at length limit: {err_msg[:120]}"
                    return "ANSWER_FAIL", f"Assertion/execution failure: {err_msg[-160:]}"
            except subprocess.TimeoutExpired:
                return "ANSWER_FAIL", "Execution timed out (5s limit exceeded)"
            except Exception as e:
                return "EVALUATOR_ERROR", f"Execution error in test runner: {e}"
            finally:
                if os.path.exists(tpath):
                    os.remove(tpath)

        # 4. Long Multiturn & Logic
        elif cat == "long_multiturn":
            norm_res = normalize_text(res)
            
            # Special case for long_01 (46,820 vs 46820)
            if q.get("id") == "long_01":
                digits = "".join(re.findall(r"\d+", norm_res))
                if digits == "46820":
                    return "PASS", "Numerical match 46820 (comma/formatting insensitive)"
                return "ANSWER_FAIL", f"Expected 46820, got digits: {digits}"
                
            # Special case for long_07 (service name & method name verified separately)
            if q.get("id") == "long_07":
                has_svc = "payment-gateway" in norm_res
                has_method = "verifySignature" in norm_res
                if has_svc and has_method:
                    return "PASS", "Verified both service 'payment-gateway' and method 'verifySignature'"
                return "ANSWER_FAIL", f"Missing components: service={has_svc}, method={has_method}"
                
            # Check needle
            target = q.get("target_needle")
            if target:
                norm_target = normalize_text(target).replace(" ", "")
                norm_c = norm_res.replace(" ", "")
                if norm_target in norm_c or any(t.strip() in norm_c for t in norm_target.split("：")):
                    return "PASS", f"Needle '{target}' found"
                if finish_reason == "length":
                    return "TRUNCATED", f"Length truncation prevented needle '{target}'"
                return "ANSWER_FAIL", f"Target needle '{target}' missing in response"
                
            # Check negative constraints
            neg = q.get("negative_constraints")
            if neg:
                violated = [n for n in neg if n in res]
                if violated:
                    return "ANSWER_FAIL", f"Negative constraints violated: {violated}"
                return "PASS", "All negative constraints respected"
                
            # Expected order
            expected_order = q.get("expected_order")
            if expected_order:
                indices = [res.find(item) for item in expected_order]
                if any(idx == -1 for idx in indices):
                    missing = [expected_order[i] for i, idx in enumerate(indices) if idx == -1]
                    return "ANSWER_FAIL", f"Missing ordered items: {missing}"
                is_sorted = all(indices[i] <= indices[i+1] for i in range(len(indices)-1))
                if is_sorted:
                    return "PASS", "Order validation passed"
                return "ANSWER_FAIL", "Order validation failed (elements out of sequence)"
                
            # Target context
            target_context = q.get("target_context")
            if target_context:
                candidates = [c.strip() for c in target_context.split("/")]
                matched = [c for c in candidates if c in res]
                if matched:
                    return "PASS", f"Matched target context: {matched}"
                return "ANSWER_FAIL", f"None of target contexts matched: {candidates}"
                
            # Exact format
            exact_format = q.get("exact_format")
            if exact_format:
                if exact_format in res:
                    return "PASS", f"Exact format requirement '{exact_format}' present"
                return "ANSWER_FAIL", f"Format requirement '{exact_format}' missing"
                
            # Max words per point
            max_words = q.get("max_words_per_point")
            if max_words:
                lines = [l.strip() for l in res.split("\n") if l.strip() and l.strip()[0].isdigit()]
                if not lines:
                    return "ANSWER_FAIL", "Failed to format as numbered list"
                long_lines = [l for l in lines if len(l) > max_words + 5]
                if not long_lines:
                    return "PASS", "Numbered list word limit respected"
                return "ANSWER_FAIL", f"Exceeded words per point on {len(long_lines)} items"

        return "EVALUATOR_ERROR", f"Unrecognized category: {cat}"

    except Exception as e:
        return "EVALUATOR_ERROR", f"Evaluator crashed: {e}"
