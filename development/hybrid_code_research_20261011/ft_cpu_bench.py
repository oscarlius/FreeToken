# hybrid 代码调研 FreeToken 侧 CPU 微基准（2026-10-11）
# 只调用已构建的 _cpu_moe 扩展（发布版 481d3a7），合成 NVFP4 bank，纯 CPU，不碰 CUDA。
# 用法：CUDA_VISIBLE_DEVICES="" /data2/FreeToken/venv/bin/python ft_cpu_bench.py
import gc
import json
import os
import statistics
import sys
import time

os.environ["CUDA_VISIBLE_DEVICES"] = ""
sys.path.insert(0, "/data2/FreeToken/wt/release-e2/python")

import torch  # noqa: E402  (must precede the pybind extension load)

try:
    from freetoken.kernel import _cpu_moe  # noqa: E402
    LOAD_PATH = "package"
except Exception:  # bypass freetoken/__init__ if the package import chain is heavy
    import glob
    import importlib.util

    so = sorted(glob.glob("/data2/FreeToken/wt/release-e2/python/freetoken/kernel/_cpu_moe*.so"))[0]
    spec = importlib.util.spec_from_file_location("_cpu_moe", so)
    _cpu_moe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_cpu_moe)
    LOAD_PATH = so

H, I, E, TOP_K, L = 2560, 640, 512, 10, 1  # Qwen3.8-Flash-Next expert geometry, one layer

g = torch.Generator().manual_seed(1234)


def u8(*shape):
    return torch.randint(0, 256, shape, dtype=torch.uint8, generator=g)


banks = {
    "gate_up_packed": u8(E, 2 * I, H // 2),
    # 0x38 = e4m3 1.0 (normal range; avoids denormal-decode CPU slowdown, cf. benchbw.py:331-333)
    "gate_up_scale": torch.full((E, 2 * I, H // 16), 0x38, dtype=torch.uint8),
    "gate_up_global": torch.full((E, 2 * I), 1.0, dtype=torch.float16),
    "down_packed": u8(E, H, I // 2),
    "down_scale": torch.full((E, H, I // 16), 0x38, dtype=torch.uint8),
    "down_global": torch.full((E, H), 1.0, dtype=torch.float16),
}
_keep = list(banks.values())


def table(t):
    tt = torch.tensor([t.data_ptr()], dtype=torch.int64)  # per-layer pointer table (L=1)
    _keep.append(tt)
    return tt.data_ptr()


def physical_reps():
    reps, seen = [], set()
    for c in sorted(os.sched_getaffinity(0)):
        try:
            with open(f"/sys/devices/system/cpu/cpu{c}/topology/thread_siblings_list") as f:
                key = f.read().strip()
        except OSError:
            reps.append(c)
            continue
        if key not in seen:
            seen.add(key)
            reps.append(c)
    return reps


def siblings_of(c):
    with open(f"/sys/devices/system/cpu/cpu{c}/topology/thread_siblings_list") as f:
        s = f.read().strip()
    out = set()
    for part in s.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.update(range(int(a), int(b) + 1))
        else:
            out.add(int(part))
    return sorted(out)


reps = physical_reps()
core_plans = {}
core_plans[1] = [reps[20] if len(reps) > 20 else reps[-1]]
core_plans[12] = reps[6:18] if len(reps) >= 18 else reps[:12]
if len(reps) >= 24:
    core_plans[24] = reps[4:24] + [siblings_of(r)[-1] for r in reps[4:8]]
else:
    core_plans[24] = reps

x = (torch.randn(1, H, generator=g) * 0.1).to(torch.bfloat16)
w = torch.rand(1, TOP_K, generator=g, dtype=torch.float32)
y = torch.zeros(1, H, dtype=torch.bfloat16)
ids = torch.full((1, TOP_K), -1, dtype=torch.int32)

out = {
    "load_path": LOAD_PATH,
    "geometry": {"H": H, "I": I, "E": E, "top_k": TOP_K, "layers": L},
    "physical_reps": reps,
    "nice": os.nice(0),
    "configs": [],
}

for nt in (1, 12, 24):
    cores = core_plans[nt][:nt]
    ext = _cpu_moe.CpuMoeExecutor(
        num_threads=len(cores), num_layers=L, num_experts=E, top_k=TOP_K,
        hidden_size=H, inter_size=I, max_tokens=1,
        activation_id=0, apply_router_weight_on_input=0, weight_format=1,  # silu, nvfp4
        gate_up_ptr=table(banks["gate_up_packed"]), down_ptr=table(banks["down_packed"]),
        gate_up_scale_ptr=table(banks["gate_up_scale"]), gate_up_global_ptr=table(banks["gate_up_global"]),
        down_scale_ptr=table(banks["down_scale"]), down_global_ptr=table(banks["down_global"]),
        gate_up_bias_ptr=0, down_bias_ptr=0,
        swiglu_alpha=1.702, swiglu_limit=float("inf"),
        core_ids=cores,
    )
    isa = ext.isa_name()
    task = ext.create_task(0, 1, x.data_ptr(), ids.data_ptr(), w.data_ptr(), y.data_ptr())
    kbase = torch.arange(TOP_K, dtype=torch.int32)
    step = 0

    def set_k(k):
        global step
        if k > 0:
            ids[0, :k] = ((step * k) + kbase[:k]) % E  # rotating disjoint expert windows
            ids[0, k:] = -1
        else:
            ids.fill_(-1)
        step += 1

    for i in range(8):  # warmup
        set_k(TOP_K)
        ext.run_task(task)

    for k, iters in ((0, 128), (1, 24), (3, 24), (10, 24)):
        run_medians, gmin, gall = [], float("inf"), float("-inf")
        for _r in range(5):
            samples = []
            for _i in range(iters):
                set_k(k)
                t0 = time.perf_counter_ns()
                ext.run_task(task)
                dt = (time.perf_counter_ns() - t0) / 1e6
                samples.append(dt)
            run_medians.append(statistics.median(samples))
            gmin = min(gmin, min(samples))
            gall = max(gall, max(samples))
        out["configs"].append({
            "threads": len(cores), "core_ids": cores, "isa": isa, "k_experts": k,
            "iters_per_run": iters, "run_medians_ms": [round(v, 6) for v in run_medians],
            "median_of_medians_ms": round(statistics.median(run_medians), 6),
            "min_step_ms": round(gmin, 6), "max_step_ms": round(gall, 6),
        })
        print(f"threads={len(cores):2d} k={k:2d} medians={[round(v,4) for v in run_medians]} "
              f"min={gmin:.4f} max={gall:.4f}", flush=True)
    del ext
    gc.collect()
    time.sleep(1.0)  # let the pool's workers join before the next config

print(json.dumps(out, indent=1))
