# D10 CUDA 原型审查包

候选提交基线为 `481d3a7`，原型在独立工作树实现，默认关闭，未触碰
`prediction_manifest.json` 或 `PREDICTION_SEAL.json`。

`freetoken.moe.staggered_decode.StaggeredDecodePrototype` 是实际 PyTorch CUDA
stream/event 原型：它创建独立 copy/compute streams，并在每层提交
`copy(A) -> compute(A) + copy(B) -> compute(B)`。每个 compute 仅等待自己的
copy-ready event，因而 B 的 H2D work 可与 A 的 kernel 同时执行。返回的 compute
completion event 是上层回收资源前必须等待的 fence；热路径没有 synchronize。

两条 lane 都必须提供互不相交的专家 cache slots 和解码 state slots。任何 cache
或状态别名、空资源、重复 request identity 都立即拒绝。现有统一 `OffloadMoeCache`
的 LRU 计划（`evict_slots/src_indices/num_indices`）仍是一份共享可变状态，因此此
原型刻意没有接入服务调度器：在分配器为每条 lane 提供专属计划张量、并完成两请求
调度/采样/KV 提交的整步契约前，接入会错误地把原型伪装成可测吞吐路径。

原型也拒绝 CUDA graph capture。当前 `GraphRunner` 捕获整个 `model.forward()`，与
跨请求的 eager 两流事件依赖不兼容；D10 后续若要测量，必须先定义单独的静态双 lane
图契约，而不是重放两个既有完整图。

`scripts/bench_d10_staggered_copy_compute.py` 是受控的 R045 两请求入口：它读取
两个冻结记录，调用上述真实 CUDA copy/compute/event 路径，并只报告路径完成；它不加载
模型、不起 HTTP 服务、不产生吞吐声明。它用于先验证设备端事件依赖与非重叠 staging
槽，不能代替服务级 D10 或 AIPerf。

CPU 审查命令（不触发 CUDA）：

```powershell
python -m pytest tests/moe/test_staggered_decode.py -q
```

得到 ROOT `ALLOW_COMPILE` 后的远端最小导入/编译准备命令（预计 1--3 分钟；不启动
服务、不做 GPU 测量）：

```bash
cd /data2/FreeToken/wt/d10-staggered-v1
source /data2/FreeToken/venv/bin/activate
python -m compileall -q python/freetoken/moe/staggered_decode.py
python -c 'from freetoken.moe.staggered_decode import StaggeredDecodePrototype; print("D10 import OK")'
```

获 ROOT 的 GPU 测量锁后，实际 CUDA 可行性（非 AIPerf）入口为：

```bash
PYTHONPATH=python python scripts/bench_d10_staggered_copy_compute.py \
  --input-file /data2/FreeToken/d10_staggered_20261009/inputs.jsonl
```

这不是 D10 正式 GPU 验收。R045 原 128 / `ignore_eos=false` 两个冻结提示和新增 256 /
`ignore_eos=true` 输入保持由既有 runner 管理，GPU 阶段仍须等 D09、T16、逐层 T05
证据及 ROOT 的测量顺序。
