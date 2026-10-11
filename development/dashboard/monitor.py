#!/usr/bin/env python3
"""运行监控侧车（8099）：只读，不改引擎、不占显存、不写 runs 目录。

主数据源是引擎自己的只读控制面（桌面端也在轮询同一批接口）：
  - /health            生命周期：loading / ok / error
  - /v1/stats          吞吐、KV/mamba 池、显存、活跃与累计请求
  - /v1/requests       请求环形日志（带 ?since= 游标：时长、TTFT、token 数都现成）
  - /v1/cache/status   维护态（loading / serving / 重建中）
引擎无数据时（停了、或旧构建缺接口）对应字段即为 null，不再读任何日志文件；
D0/排队数等引擎没有的口径恒为空。

nvidia-smi（容器只需 utility 级 GPU 能力）与 /data2/_shared/gpu.lock 是独立旁证。

失败关闭：任何一路取不到就置 null 并记进 unknown[]，页面显示「未知」，绝不填 0 ——
把「没采到」显示成 0 会误导正在做轮次的人。注意区分两件事：/v1/stats 的吞吐是 5 秒滑窗，
空闲时本来就是 0（那是真值）；接口没取到才是「未知」。
"""

import collections
import glob
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

RUNS_DIR = os.environ.get("RUNS_DIR", "/data2/_shared/runs")
FT_ROUNDS_DIR = os.environ.get("FT_ROUNDS_DIR", os.path.join(RUNS_DIR, "ft_rounds"))
GPU_LOCK = os.environ.get("GPU_LOCK_FILE", "/data2/_shared/gpu.lock")
ENGINE_URL = os.environ.get("ENGINE_URL", "http://172.16.108.9:8095")
MAX_SAMPLES = 1800  # A线历史曲线：2s 一采，保留约 1 小时
MAX_REQUESTS = 300
REQUEST_PAGE = 256          # /v1/requests 单次上限（引擎侧再夹到 512）
LOG_STALE_S = 120            # 日志多久没新行就当闲置
STATS_STALE_S = 30           # 端口数据多久没刷新就不配当「现值」

_LOG_RE_REMOVED = True  # 日志正则已删除（engine-only）

_lock = threading.Lock()
_state = {
    # 端口主源
    "engine": None, "engine_error": None,        # /health
    "stats": None, "stats_error": None,          # /v1/stats
    "cache": None, "cache_error": None,          # /v1/cache/status
    "stats_samples": collections.deque(maxlen=MAX_SAMPLES),
    "requests": collections.deque(maxlen=MAX_REQUESTS),   # /v1/requests 游标增量
    "req_error": None,
    "req_cursor": 0,
    "req_instance": None,
    "stats_at": 0.0,
    "requests_at": 0.0,
    "parse_errors": collections.deque(maxlen=20),
    "cpu_prev": None,
    "disk_prev": None,
    "started_at": time.time(),
}


def _now():
    return time.time()


# 引擎日志/静态资源之外的通用小工具 --------------------------------------------------

def _is_refused(err):
    """连接被拒/超时/DNS 失败：整台引擎都不在，不必再逐个数着接口报错。
    认的是异常类型名（各语言/各系统的报错文案不一样，Windows 连中文都有）。"""
    if not err:
        return False
    m = err.lower()
    return any(k in m for k in ("connectionrefused", "connection refused", "timed out", "timeout",
                                "unreachable", "getaddrinfo", "connectionreset", "nohost"))


def _get_json(path, params=None, timeout=3):
    """GET 引擎的一个只读接口。返回 (data, error)，两者只有一个非空。"""
    url = ENGINE_URL.rstrip("/") + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore")), None
    except urllib.error.HTTPError as e:
        return None, "HTTP %s" % e.code
    except (urllib.error.URLError, OSError) as e:
        reason = getattr(e, "reason", e)
        return None, "%s: %s" % (type(reason).__name__, reason)
    except ValueError as e:
        return None, "返回不是 JSON: %s" % e


def median(vals):
    v = sorted(x for x in vals if isinstance(x, (int, float)) and not isinstance(x, bool))
    if not v:
        return None
    i = len(v) // 2
    return round(v[i] if len(v) % 2 else (v[i - 1] + v[i]) / 2.0, 2)




# 端口主源 ---------------------------------------------------------------------------

def _instance_id(health, stats):
    for doc in (stats, health):
        if isinstance(doc, dict) and doc.get("instance_id"):
            return str(doc["instance_id"])
    return None


def _stats_sample(st, now):
    """/v1/stats 的一份采样。缺字段一律 None，不补 0 —— 0 在这份接口里是「窗口内真没出字」。"""
    tp = st.get("throughput") if isinstance(st.get("throughput"), dict) else {}
    kv = st.get("kv") if isinstance(st.get("kv"), dict) else {}
    mm = st.get("mamba") if isinstance(st.get("mamba"), dict) else {}
    req = st.get("requests") if isinstance(st.get("requests"), dict) else {}
    total = kv.get("total_pages")
    used = kv.get("used_pages")
    s = {"at": now, "src": "stats",
         "gen_tps": tp.get("decode_tps"), "input_tps": tp.get("prefill_tps"),
         "running": req.get("active"), "queued": None, "context_token": None,
         "kv_usage": (round(used / total, 4) if total and used is not None else None),
         "mamba_used": mm.get("used_slots"), "mamba_total": mm.get("total_slots"),
         "vram_bytes": st.get("vram_bytes"),
         "active": req.get("active"), "completed": req.get("completed"),
         "p95_ms": req.get("p95_ms"), "ttft_mean_ms": req.get("ttft_mean_ms"),
         "prompt_tokens_total": req.get("prompt_tokens_total"),
         "completion_tokens_total": req.get("completion_tokens_total")}
    return {k: v for k, v in s.items() if v is not None}


def engine_poll():
    """轮询四个只读接口。健康检查连不上就整组跳过（别再对同一台机器发 3 次垃圾请求）。"""
    health, herr = _get_json("/health")
    now = _now()
    refused = _is_refused(herr)
    if refused:
        with _lock:
            _state["engine"] = None
            _state["engine_error"] = herr
            _state["stats"] = None
            _state["stats_error"] = "引擎不可达，未轮询"
            _state["cache"] = None
            _state["cache_error"] = "引擎不可达，未轮询"
            _state["req_error"] = "引擎不可达，未轮询"
        return
    stats, serr = _get_json("/v1/stats")
    cache, cerr = _get_json("/v1/cache/status")
    with _lock:
        instance = _instance_id(health, stats)
        last = _state["req_instance"]
        if instance is not None and last is not None and instance != last:
            # 换服务进程 = 游标从头开始；不清零会一直 since=很大 而永远拿不到新请求
            _state["req_cursor"] = 0
            _state["requests"].clear()
        _state["req_instance"] = instance

    rdoc = None
    rerr = None
    # 四个接口各自独立：这个构建可能有 /v1/stats 却没有 /v1/requests，不能连带跳过
    rdoc, rerr = _get_json("/v1/requests", {"since": _state["req_cursor"], "limit": REQUEST_PAGE})

    with _lock:
        _state["engine"] = health
        _state["engine_error"] = herr
        _state["stats"] = stats
        _state["stats_error"] = serr
        _state["cache"] = cache
        _state["cache_error"] = cerr
        _state["req_error"] = rerr
        _state["stats_at"] = now
        if serr is None and isinstance(stats, dict):
            _state["stats_samples"].append(_stats_sample(stats, now))
        if rerr is None and isinstance(rdoc, dict):
            items = rdoc.get("entries")
            nxt = rdoc.get("next_cursor")
            if isinstance(items, list) and isinstance(nxt, int) and not isinstance(nxt, bool):
                if nxt < _state["req_cursor"]:      # 游标倒退 = 服务重启过，别拿旧进程的位置继续要
                    _state["requests"].clear()
                _state["req_cursor"] = nxt
                for e in items:
                    if not isinstance(e, dict):
                        continue
                    _state["requests"].append({
                        "at": now, "stamp": e.get("ts"), "method": e.get("method"), "path": e.get("path"),
                        "status": e.get("status"), "duration_ms": e.get("duration_ms"),
                        "ttft_ms": e.get("ttft_ms"), "prompt_tokens": e.get("prompt_tokens"),
                        "completion_tokens": e.get("completion_tokens"), "error": e.get("error"),
                        "src": "ring"})
                _state["requests_at"] = now


def stats_activity(samples):
    """最近几个 stats 采样里有没有在出字/在读 prompt。"""
    recent = samples[-3:]
    gen = any((s.get("gen_tps") or 0) > 0 for s in recent)
    pre = any((s.get("input_tps") or 0) > 0 for s in recent)
    act = max((s.get("active") or 0) for s in recent) if recent else 0
    return gen, pre, act


def derive_pools(stats, cache, ctx_used, cache_error=None):
    """上下文填充与池容量：把 /v1/stats 与 /v1/cache/status 已有的数拼成能看的口径。

    空的时候必须说清是哪一种空——「引擎没连上」「引擎在加载权重」「就绪但字段缺」
    对做轮次的人是三件不同的事，糊成一句「等就绪」就是误导。
    加载期 geometry 全是 0，那是「还没分配」，不是「0 个专家 / 0 token 池」，一律置 None。"""
    cache = cache if isinstance(cache, dict) else {}
    stats = stats if isinstance(stats, dict) else {}
    geo = cache.get("geometry") if isinstance(cache.get("geometry"), dict) else {}
    kv = stats.get("kv") if isinstance(stats.get("kv"), dict) else {}
    model = stats.get("model") if isinstance(stats.get("model"), dict) else {}
    state = cache.get("state")
    ked = kv if isinstance(kv, dict) else {}
    _ku, _kps = ked.get("used_pages"), ked.get("page_size")
    if ctx_used is None and isinstance(_ku, (int, float)) and isinstance(_kps, (int, float)) and _ku > 0:
        ctx_used = _ku * _kps  # engine-only：上下文已用 = /v1/stats kv.used_pages × page_size
    out = {"cache_state": state, "ctx_total": model.get("ctx"), "ctx_used": ctx_used,
           "ctx_pct": None, "kv_pool_tokens": None, "kv_used_tokens": None, "kv_pct": None,
           "moe_cached": None, "moe_total": None, "moe_gib": None, "moe_policy": None,
           "budget_gib": None, "mamba_total": None, "note": None}
    if out["ctx_total"] and isinstance(ctx_used, (int, float)):
        out["ctx_pct"] = round(min(100.0, ctx_used / out["ctx_total"] * 100.0), 1)
    if not cache:
        out["note"] = "没拿到 /v1/cache/status（%s），池几何不画" % (cache_error or "未取到")
        return out
    if state != "serving":
        out["note"] = "引擎维护态 %s：池还没分配" % (state or "未报")
        return out
    pages, ps = geo.get("num_pages"), geo.get("page_size")
    if pages and ps:
        out["kv_pool_tokens"] = int(pages) * int(ps)
    used, total = kv.get("used_pages"), kv.get("total_pages")
    if used is not None and total:
        out["kv_used_tokens"] = int(used) * int(kv.get("page_size") or 1)
        out["kv_pct"] = round(used / total * 100.0, 1)
        if not out["kv_pool_tokens"]:
            out["kv_pool_tokens"] = int(total) * int(kv.get("page_size") or 1)
    cached = geo.get("moe_cache_size")
    unit = (geo.get("unit_bytes") or {}).get("moe_per_expert")
    out["moe_total"] = geo.get("num_experts")
    out["moe_cached"] = cached
    out["moe_policy"] = geo.get("moe_cache_policy")
    if cached and unit:
        out["moe_gib"] = round(cached * unit / 1073741824.0, 2)
    budget = geo.get("cache_budget_bytes")
    out["budget_gib"] = round(budget / 1073741824.0, 2) if budget else None
    out["mamba_total"] = geo.get("num_mamba_slots")
    return out


def derive_state():
    """状态判定顺序：引擎自己在加载 → 维护态不是 serving → 端口有活动 → 否则 unknown。
    端口新鲜度超时（stats_at 太久以前）就不再声称它是现值。"""
    with _lock:
        health = _state["engine"]
        stats = _state["stats"]
        cache = _state["cache"]
        stats_at = _state["stats_at"]
        port_recent = list(_state["stats_samples"])
        last = None  # 日志旁路已删除（engine-only）
        have_log = False  # 日志旁路已删除（engine-only）
        growth = None
    idle_s = round(_now() - growth) if growth else None

    if isinstance(health, dict) and health.get("status") == "loading":
        prog = health.get("progress") or {}
        done, total = prog.get("done_bytes"), prog.get("total_bytes")
        pct = ("%.1f%%" % (done / total * 100)) if isinstance(done, (int, float)) and isinstance(total, (int, float)) and total else "?"
        return "loading", idle_s, growth, "阶段 %s，已搬 %s / %s GB（%s）" % (
            health.get("phase") or "?", round((done or 0) / 1073741824, 2),
            round((total or 0) / 1073741824, 2), pct)

    if isinstance(cache, dict) and _now() - stats_at <= STATS_STALE_S:
        cst = cache.get("state")
        if cst and cst != "serving":
            return ("loading" if cst == "loading" else "busy"), idle_s, growth, "维护态 %s" % cst

    if isinstance(stats, dict) and _now() - stats_at <= STATS_STALE_S:
        gen, pre, active = stats_activity(port_recent)
        if gen:
            return "generating", idle_s, growth, None
        if pre:
            return "reading", idle_s, growth, None
        if active > 0:
            return "reading", idle_s, growth, "有 %s 条请求在跑，但窗口内没有 token 增量" % active
        return "idle", idle_s, growth, None

    # 引擎-only：端口无新鲜值即 unknown，不再看日志。
    return "unknown", idle_s, growth, "端口没有新鲜值（/v1/stats 超时或字段缺）"


def metrics():
    # 引擎-only 模式（用户要求）：不再读 serve.log，主源只剩引擎四个接口。
    engine_poll()
    gpu, gpu_err = gpu_snapshot()
    with _lock:
        st_samples = list(_state["stats_samples"])[-MAX_SAMPLES:]
        lg_samples = []  # 日志旁路已删除
        ring = list(_state["requests"])[-60:]
        log_req = []  # 日志旁路已删除
        d0 = []  # 日志旁路已删除（输出本就恒空）
        engine = _state["engine"]
        engine_error = _state["engine_error"]
        stats, stats_error = _state["stats"], _state["stats_error"]
        cache, cache_error = _state["cache"], _state["cache_error"]
        req_error = _state["req_error"]
        stats_at = _state["stats_at"]
        requests_at = _state["requests_at"]
        log_path = None  # 日志旁路已删除
        last_batch = None  # 日志旁路已删除
        growth = None  # 日志旁路已删除（本函数内无他用）
        parse_errors = list(_state["parse_errors"])[-8:]
    unknown = []

    state, idle_s, _, state_note = derive_state()
    engine_down = bool(engine_error) and _is_refused(engine_error)

    # 主源是端口；它不新鲜即 stale，不再读日志。
    stats_fresh = isinstance(stats, dict) and (_now() - stats_at) <= STATS_STALE_S
    samples = st_samples
    primary = "stats" if stats_fresh else None
    stale = not stats_fresh

    recent = samples[-20:]
    gen = [v for v in (s.get("gen_tps") for s in recent) if isinstance(v, (int, float))]
    inp = [v for v in (s.get("input_tps") for s in recent) if isinstance(v, (int, float))]
    window = (max(s["at"] for s in recent) - min(s["at"] for s in recent)) if len(recent) > 1 else 0

    def last_of(key, src=None):
        for s in reversed(src if src is not None else samples):
            if s.get(key) is not None:
                return s[key]
        return None

    # 引擎-only：queued/context_token 等日志批次行字段不再回填，缺即 None。
    aux = None
    sreq = (stats.get("requests") if isinstance(stats, dict) else None) or {}
    live = {
        "running_req": last_of("running"),
        "queued_req": (aux or {}).get("queued"),
        "kv_usage": last_of("kv_usage"),
        "context_token": (aux or {}).get("context_token") or last_of("context_token"),
        "mamba_used": last_of("mamba_used"),
        "mamba_total": last_of("mamba_total"),
        "vram_bytes": last_of("vram_bytes"),
        "gen_tps": last_of("gen_tps"),
        "gen_tps_mean": round(sum(gen) / len(gen), 2) if gen else None,
        "gen_tps_median": median(gen),
        "input_tps": last_of("input_tps"),
        "input_tps_median": median(inp),
        "input_tps_points": len(inp),
        "active": sreq.get("active"),
        "completed": sreq.get("completed"),
        "p95_ms": sreq.get("p95_ms"),
        "ttft_mean_ms": sreq.get("ttft_mean_ms"),
        "prompt_tokens_total": sreq.get("prompt_tokens_total"),
        "completion_tokens_total": sreq.get("completion_tokens_total"),
        "window_s": round(window, 1),
        "window_points": len(samples),
        "idle_s": idle_s,
        "stale": bool(stale),
        "fresh": bool(samples),
        "primary": primary,
    }

    if not samples and state != "loading":          # 加载期本来就没有吞吐，不算「取不到」
        unknown.append("throughput（引擎 /v1/stats 无新鲜采样）")
    if engine_down:
        unknown.append("engine（%s 未监听：/health 与 /v1/stats、/v1/requests、/v1/cache/status 全取不到）" % ENGINE_URL)
    else:
        for name, err in (("engine /health", engine_error), ("engine /v1/stats", stats_error),
                          ("engine /v1/requests", req_error), ("engine /v1/cache/status", cache_error)):
            if err:
                unknown.append("%s %s" % (name, err))
    if gpu_err:
        unknown.append("gpu")

    # 请求列表也要讲新鲜度：环接口挂了就退回访问日志，别拿一份不再刷新的旧环当现状。
    ring_age = round(_now() - requests_at) if requests_at else None
    ring_ok = bool(ring) and requests_at and (_now() - requests_at) <= STATS_STALE_S
    if ring_ok:
        requests, req_src = ring, "ring"
    else:
        requests, req_src = ring, ("ring" if ring else None)

    return {
        "ts": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S"),   # 容器是 UTC，页面按东八区显示
        "uptime_s": round(_now() - _state["started_at"]),
        "state": state,
        "state_note": state_note,
        "engine_down": engine_down,
        "live": live,
        "pools": derive_pools(stats, cache, None, cache_error),
        "series": {"t": [s["at"] for s in samples], "gen_tps": [s.get("gen_tps") for s in samples],
                   "input_tps": [s.get("input_tps") for s in samples],
                   "running": [s.get("running") for s in samples], "src": primary},
        "series_log": {"t": [], "gen_tps": [], "input_tps": []},
        "engine": engine if engine else {"error": engine_error},
        "stats": stats if stats else {"error": stats_error},
        "cache": cache if cache else {"error": cache_error},
        "endpoints": {"/health": "ok" if engine else engine_error, "/v1/stats": "ok" if stats else stats_error,
                      "/v1/requests": "ok" if req_error is None else req_error,
                      "/v1/cache/status": "ok" if cache else cache_error},
        "gpu": gpu if gpu else {"error": gpu_err},
        "host": host_snapshot(),
        "bench": {"lock": lock_snapshot()},
        "requests": requests,
        "requests_src": req_src,
        "requests_age_s": ring_age,
        "d0_chunks": [],
        "sources": {"primary": "engine /v1/stats" if primary == "stats" else
                              "没有可用主源（引擎无新鲜采样）",
                    "serve_log": None, "engine_url": ENGINE_URL, "runs_dir": RUNS_DIR},
        "unknown": [u for u in dict.fromkeys(unknown) if u],
        "parse_errors": parse_errors,
    }


# 独立旁证 ---------------------------------------------------------------------------

GPU_FIELDS_FULL = ["name", "utilization.gpu", "utilization.memory", "memory.used", "memory.total",
                   "temperature.gpu", "power.draw", "power.limit", "clocks.sm", "clocks.max.sm",
                   "fan.speed", "pcie.link.gen.current", "pcie.link.width.current"]
GPU_KEYS = ["name", "util_pct", "mem_util_pct", "mem_used_mib", "mem_total_mib", "temp_c", "power_w",
            "power_limit_w", "sm_clock_mhz", "clock_max_mhz", "fan_pct", "pcie_gen", "pcie_width"]
GPU_FIELDS_MIN = ["name", "utilization.gpu", "memory.used", "memory.total", "temperature.gpu", "clocks.sm"]
GPU_KEYS_MIN = ["name", "util_pct", "mem_used_mib", "mem_total_mib", "temp_c", "sm_clock_mhz"]
NA_TOKENS = ("n/a", "na", "[n/a]", "not supported", "[not supported]", "unknown", "")
_WHOLE_DISK = re.compile(r"sd[a-z]$|nvme\d+n\d+$|vd[a-z]$|md\d+$")


def _num(raw):
    """nvidia-smi 的数值字段；[N/A] / [Not Supported] 一律 None。
    「读不到功耗」和「功耗 0 W」是两件事，不能混。"""
    if raw.strip().lower() in NA_TOKENS:
        return None
    try:
        v = float(raw)
    except ValueError:
        return None
    return int(v) if v.is_integer() else v


def parse_nvidia_smi(line, keys):
    """一行 nvidia-smi CSV（noheader,nounits）→ dict；字段不齐就返回 None。"""
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < len(keys):
        return None
    out = {}
    for k, raw in zip(keys, parts):
        out[k] = raw if k == "name" else _num(raw)
    return out


def gpu_snapshot():
    """先按全字段查；驱动不认某个字段会让整条查询失败，那时退回最小集——
    宁可少几张卡，也不能因为功耗读不了把 GPU 利用率一起弄没。"""
    if not shutil.which("nvidia-smi"):
        return None, "容器里没有 nvidia-smi（起容器要带 --gpus 且 NVIDIA_DRIVER_CAPABILITIES=utility）"
    for fields, keys in ((GPU_FIELDS_FULL, GPU_KEYS), (GPU_FIELDS_MIN, GPU_KEYS_MIN)):
        cmd = ["nvidia-smi", "--query-gpu=" + ",".join(fields), "--format=csv,noheader,nounits"]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=6)
        except Exception as e:
            return None, "nvidia-smi 调用失败: %s" % e
        if out.returncode != 0:
            continue
        line = out.stdout.strip().splitlines()[0] if out.stdout.strip() else ""
        parsed = parse_nvidia_smi(line, keys)
        if parsed:
            return parsed, None
    return None, "nvidia-smi 两次查询都没拿到可解析的字段"


def parse_proc_stat(text):
    """/proc/stat 的第一行（聚合 cpu 行）→ (总 jiffies, 空闲 jiffies)。利用率要两次采样相减。

    只取第一行：后面跟着 cpu0…cpu95 每核行，整篇 split 会把「cpu0」当数字解析而失败。"""
    lines = text.splitlines() if text else []
    f = lines[0].split() if lines else []
    if not f or f[0] != "cpu" or len(f) < 5:
        return None
    try:
        nums = [int(x) for x in f[1:]]
    except ValueError:
        return None
    return sum(nums), nums[3] + (nums[4] if len(nums) > 4 else 0)      # 空闲 = idle + iowait


def pct_from_delta(prev, cur):
    """第一次采样没有前值 → None，不猜一个 0%。"""
    if not prev or not cur:
        return None
    dt = cur[0] - prev[0]
    di = cur[1] - prev[1]
    if dt <= 0:
        return None
    return round(max(0.0, min(100.0, (1.0 - di / dt) * 100.0)), 1)


def parse_diskstats(text):
    """整盘设备的累计读写扇区（扇区固定 512 B，与 /proc/diskstats 的定义一致）。
    只数整盘（sda / nvme0n1 / vda / md0）：算上分区会把同一份流量数两遍。"""
    rd = wr = 0
    seen = False
    for line in text.splitlines():
        f = line.split()
        if len(f) < 10 or not _WHOLE_DISK.search(f[2]):
            continue
        try:
            rd += int(f[5])
            wr += int(f[9])
        except ValueError:
            continue
        seen = True
    return (rd, wr) if seen else None


def mb_s_from_delta(prev, cur, dt_s):
    """磁盘读写 MB/s。计数器回绕（负差）或间隔太短 → None。"""
    if not prev or not cur or not dt_s or dt_s < 0.5:
        return None
    dr, dw = cur[0] - prev[0], cur[1] - prev[1]
    return {"read_mb_s": None if dr < 0 else round(dr * 512.0 / 1e6 / dt_s, 2),
            "write_mb_s": None if dw < 0 else round(dw * 512.0 / 1e6 / dt_s, 2)}


def read_text(path, limit=8192):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except OSError:
        return None


def host_snapshot():
    out = {}
    getload = getattr(os, "getloadavg", None)         # Windows 没有这个调用：置 None，不崩采集
    try:
        out["loadavg"] = [round(x, 2) for x in getload()] if getload else None
    except OSError:
        out["loadavg"] = None
    try:
        info = {}
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                k, _, v = line.partition(":")
                info[k] = int(v.strip().split()[0])
        total = info.get("MemTotal", 0) / 1048576.0
        avail = info.get("MemAvailable", 0) / 1048576.0
        out["mem_total_gb"] = round(total, 1)
        out["mem_used_gb"] = round(total - avail, 1)
    except (OSError, ValueError):
        out["mem_total_gb"] = None
        out["mem_used_gb"] = None
    try:
        with open("/proc/pressure/io", encoding="utf-8") as fh:
            first = fh.readline().strip()      # "avg10=.. avg60=.. avg300=.. total=.."
            out["io_pressure_avg10"] = float(re.search(r"avg10=([\d.]+)", first).group(1))
        with open("/proc/pressure/cpu", encoding="utf-8") as fh:
            first = fh.readline().strip()
            out["cpu_pressure_avg10"] = float(re.search(r"avg10=([\d.]+)", first).group(1))
    except (OSError, ValueError, AttributeError):
        out.setdefault("io_pressure_avg10", None)
        out.setdefault("cpu_pressure_avg10", None)
    out["cores"] = os.cpu_count()

    # 利用率与速率都是差分量：第一次采样只能给 None，第二次起才有值。
    now = _now()
    cpu = parse_proc_stat(read_text("/proc/stat") or "")
    with _lock:
        prev_cpu = _state["cpu_prev"]
        _state["cpu_prev"] = cpu
    out["cpu_pct"] = pct_from_delta(prev_cpu, cpu)

    disk = parse_diskstats(read_text("/proc/diskstats") or "")
    with _lock:
        prev_disk, prev_at = _state["disk_prev"] or (None, None)
        _state["disk_prev"] = (disk, now)
    rates = mb_s_from_delta(prev_disk, disk, now - prev_at if prev_at else None) or {}
    out["read_mb_s"] = rates.get("read_mb_s")
    out["write_mb_s"] = rates.get("write_mb_s")
    return out


def safe_web_path(name, base):
    """静态文件路径必须在 WEB_DIR 里，越界返回 None（符号链接也按真实路径判）.

    先把反斜杠当分隔符看待：在 Linux 上它本来是合法文件名字符，
    于是 "..\\..\\etc\\passwd" 会被判成「没越界」——客户端可不管你在哪个系统。"""
    b = os.path.realpath(base)
    target = os.path.realpath(os.path.join(b, name.replace("\\", "/")))
    if target == b or target.startswith(b + os.sep):
        return target
    return None


def lock_snapshot():
    if not os.path.isfile(GPU_LOCK):
        return {"held": False}
    try:
        with open(GPU_LOCK, encoding="utf-8") as fh:
            data = json.load(fh)
        return {"held": True, "owner": data.get("owner"), "since": data.get("since"), "raw": data}
    except (OSError, ValueError) as e:
        return {"held": True, "owner": None, "error": "锁文件读不出: %s" % e}


def loop(interval=2.0):
    while True:
        try:
            engine_poll()  # engine-only：不再读任何日志，tail_log 已删除
        except Exception as e:
            with _lock:
                _state["parse_errors"].append("采集循环异常: %s" % e)
        time.sleep(interval)


def start_background():
    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    import uvicorn
    from fastapi import FastAPI
    from fastapi.responses import FileResponse, JSONResponse

    WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
    app = FastAPI(title="Run Monitor (read-only sidecar)", version="1.0")
    start_background()

    @app.get("/metrics")
    def _metrics():
        return JSONResponse(metrics())

    @app.get("/")
    def _index():
        return FileResponse(os.path.join(WEB_DIR, "monitor.html"))

    @app.get("/web/{name:path}")
    def _asset(name: str):
        target = safe_web_path(name, WEB_DIR)
        if target is None:
            return JSONResponse({"detail": "越界路径"}, status_code=400)
        if not os.path.isfile(target):
            return JSONResponse({"detail": "没有这个文件"}, status_code=404)
        return FileResponse(target)

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8099")), log_level="warning")
