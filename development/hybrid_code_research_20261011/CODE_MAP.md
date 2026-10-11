# CODE_MAP — FreeToken 481d3a7 与 Strata v0.1.41 的"CPU 计算未命中专家"调用链对照

- 调研日期：2026-10-11。只读调研，未改动任何代码树。
- FreeToken 侧：服务器 `/data2/FreeToken/wt/release-e2`，提交 `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9`（发布版 481d3a7）。路径前缀 `python/freetoken/`。
- Strata 侧：服务器 `/data2/Strata/wt/r002-v0141`，提交 `fb58e0dbc8399662c0e47c76578c6e878b14f6cf`（tag v0.1.41）。路径前缀 `src/`、`docs/`。S1 实测配置见 `_src_snapshot/strata_s1/{argv.json,config.json}`（`--pcie-frac 0`、`--adapt-swaps 0`、`numactl --interleave=all taskset -c 4-47`）。
- 模型：Qwen3.8-Flash-Next（48 层、512 专家、top_k=10、hidden 2560、expert inter 640；config.json 读码确认）。
- 证据底稿：`_evidence/EVIDENCE_FREETOKEN.md`、`_evidence/EVIDENCE_STRATA.md`（同目录）。本图所有行号均读码确认。

## 1. FreeToken（hybrid decode，一个 MoE 层，flag-sync 默认路径）

```
路由打分          layers/moe.py:241-246  fused_topk（外部路由模型走 :210-234 routed_forward）
层入口分发        layers/moe.py:276-306  _decode_routed → decode_target=="hybrid" → _decode_hybrid
                  （--moe-cpu-layers 整层纯 CPU 在 :294-304 先行截走）
命中/取数决策     moe/offload_cache.py:1213-1232  ensure_experts_hybrid
（GPU 单 program   → moe/offload_kernels.py:43-60,97-125  → _ensure_experts_hybrid_kernel :291-410
  Triton kernel）    · 命中判定 slot_for_id[layer][e] >= 0            :341-343
                     · 取数封顶 max_fetch / fetch_frac_q16（Q16 定点现算）:345-355
                     · 取哪些 miss：BY_RECENCY（LRU+小 id tie）:364-368,406-410
                     · topk_ids 原地改写为槽位号或 -1（-1=溢出 miss→CPU）:400-404
CPU 路由集合      layers/moe.py:346-352  raw=clone、on_gpu=ids>=0、cpu_ids=where(on_gpu,-1,raw)
CPU 派发（先于    layers/moe.py:353  executor.decode_submit（注释 :338-340：先踢 CPU 任务再 GPU 取数）
 GPU 工作入队）   → moe/cpu_executor.py:543-587
                     · D2H x/ids/w → pinned（non_blocking）           :570-572
                     · 提交 = stream memop cuStreamWriteValue64×2     :577-583
                       （C++ 侧 cpu_moe_ext.cpp:646-657；退回 host-func :584-586 → C++ :1970-1978）
协调线程          cpu_moe_ext.cpp:2019-2060  busy-poll ready 旗标（50ms 热窗后空闲退避 :2019-2085）
                  → submit() :1892-1962
                     · 单线程预处理：nvfp4 激活 deinterleave + per-16 int8 量化 :1911-1941
                     · mutex + cur_gen++ + task_cv.notify_all()       :1955-1961
工作线程          worker_loop :1869-1890（task_cv.wait :1874-1876）
CPU 计算          run_task_body :1843-1867
                     · pass1：gate/up，tile=(token,route k,32 中间行)   do_pass1 :1582-1637
                     · 屏障 1（sense-reversal 纯自旋）                  :1568-1580
                     · prep：g 行 deinterleave+int8（worker 分摊）      prep_g_row :1799-1813
                     · 屏障 2（自旋）
                     · pass2：down，tile=(token,32 隐藏行)              do_pass2 :1639-1678
                     · 完工：末位 worker sync_cv.notify_all             :1882-1888
GPU 取数          layers/moe.py:363 → moe/offload_cache.py:1369-1411 copy_missing
                  （fused 单 launch 多 bank：kernel fast_index_copy :1385-1399）
GPU 专家 GEMM     layers/moe.py:370-379 → _expert_gemm :450-471
                  → moe/fused_nvfp4.py:161-202 → kernel/triton/nvfp4_fused_moe.py:90-142
                  （CPU 路由的权重置 0、slot clamp :366-367，保证每路由只算一次）
CPU 同步+H2D      layers/moe.py:382 decode_sync → moe/cpu_executor.py:589-605
                     · GPU 前端 cuStreamWaitValue64(done>=1)（不占 SM） :594-599 → C++ :659-664
                     · 退回 host-func                                   :600-602 → C++ :1975-1978,:2106-2109
                     · H2D y（non_blocking）                            :604
合并写回          layers/moe.py:383  return gpu_routed + cpu_routed（GPU 上 bf16 逐元素加）
执行器建立        engine/engine.py:752-753 → _init_cpu_moe_executor :789-823
                  → cache.set_cpu_executor（moe/offload_cache.py:851-861）
取数上限设置      engine/engine.py:758-787 _resolve_hybrid_fetch
                  ← moe/bench_profile.py:156-191 load_hybrid_fetch_fraction（ft bench bw profile）
```

CUDA Graph 关系：decode 整步一张图（`engine/graph.py:184-205,214-220`），hybrid 不打断图；每层图内含 3×D2H + memop 提交 + GPU fetch/GEMM + memop WAIT + 1×H2D + 加法节点；旗标槽每 (layer,bs) 一个（`moe/cpu_executor.py:55,273-286`）。

## 2. Strata v0.1.41（S1：--spec 2 verify 窗口，一个 MoE 层，--pcie-frac 0）

```
路由+门铃         src/core/layer.cpp:357-391  moe_route：router top-k → x/ids/w 拷进 mapped
                  → doorbell_ring（kernel：src/kernels/cuda/elementwise.cu:209-226,428-432；
                  序号取自 host 副本使图重放幂等，注释 layer.cpp:385-390）
host 收铃         src/core/verify.cpp:1971-1999  自旋 volatile h_seq_（20s 看门狗）
池回调            src/core/verify.cpp:2008-2010 → src/program/generate.cpp:955-976 drive_pool_multi
归属决策          src/core/expert_source.cpp:3105 expert_pool_dispatch_multi
（host 侧）          · 窗口 n_tok*k 条按路由序去重，上限 128 条          :3155-3164,:3101-3102
                     · 查驻留表 host_res：slot≥0 → GPU                  :3177-3182
                       （peer GPU kind 2 :3183-3184；Foresight 交换槽 :3187-3188）
                     · miss 按路由序编号；最后 (nmiss*pcie_num)>>8 个走 PCIe DMA
                       （kind 1，:3166-3167,:3191-3199）；S1 pcie-frac 0 → 全归 CPU（kind -1 :3175）
                     · usage 累加（供 adapt 置换；S1 adapt-swaps 0 静止）:3136-3138
GPU 计划先行发布  src/core/expert_source.cpp:3139-3140 注释；fence+P.publish(flagA)+P.fetch(flagB) :3235-3239
按专家分组        src/core/expert_source.cpp:3324-3345 ExpertJobMulti（distinct 专家聚合 nt 个 token）
                  → pool->run_split_multi_native :3349-3351
线程池两相位      src/kernels/cpu/pool.cpp:759-788 run_split_multi_native
                     · run_phase(5=全部专家的 gate/up 行)
                     · host 串行做 SwiGLU 后激活量化                     :772-775
                     · run_phase(6=全部专家的 down 行)
                     · phase 内行空间按任务静态等分（可跨专家边界）       :627-660
                     · 任务数 ≈ 3×(worker+host)                          :716-718
run_phase 协议    pool.cpp:688-698：wait_parked → begin_batch（epoch_++，publish :476-487）
                  → host 也 drain 抢任务（:693，host 循环 :823-833）→ wait_done → wait_parked
worker            pool.cpp:496-523：epoch_ 上 _mm_pause 自旋；超 spin_before_sleep_
                  （env STRATA_POOL_SPIN_US :439-440；默认常量 kSpinBeforeSleep 在 pool.hpp，
                  快照缺该头文件，默认值未找到）后 mutex+CV 睡眠
内核              drain :608-686 → mode 5/6 :627-660
                  → native_gu_rows/native_down_rows（src/kernels/cpu/native_expert.cpp:125-206）
                  → row_dot（src/kernels/cpu/iq_avx512.cpp:155-186：9-bit 码表查表+符号掩码
                    +_mm512_maddubs/madd_epi16 整数点积，每 256 值块一次 fp32 FMA）
                  结果写 mapped y_miss
host 写完成旗     src/core/verify.cpp:2039（fence/sfence 后 *flag=want；无计划兜底 :2018-2027）
GPU 图内合并      src/core/verify.cpp：wait_flag_ge 自旋核（src/kernels/cuda/verify_kernels.cu:970,1151-1198）
                     · 等 flagA（计划已发布）:1449 → VRAM 命中组 native_expert_grouped :1453
                     · 等 flagB（PCIe DMA 落地；S1 空）:1456
                     · 等 m_flag_（CPU 行就绪）:1473
                     · copy_rows_from_mapped 读回 CPU 行 :1477-1481
                     · moe_hit_add 命中+未命中合并 :1483
                     · native_moe_combine_multi 整窗一次 combine :1495-1498
```

CUDA Graph 关系：整个 verify 窗口捕获为一张图（`src/core/verify.cpp:1676-1769`；token 级整图 `src/core/session.cpp:836-908`）；CPU 路径在图外，经 mapped 旗标与图内自旋核握手。

## 3. 结构差异一览（详表见 Q1_Q10_COMPARISON.md）

| 环节 | FreeToken | Strata |
|---|---|---|
| 归属决策 | GPU 上单 program Triton kernel，图安全（offload_kernels.py:291-410） | host 侧 C++（expert_source.cpp:3105），决策后计划发布给 GPU |
| 池唤醒 | worker 睡条件变量，每层 1 次 CV 唤醒（cpu_moe_ext.cpp:1874-1876） | worker 自旋 epoch，超时转 CV（pool.cpp:496-523） |
| 相位屏障 | 2 次 sense-reversal 自旋屏障（:1568-1580） | 无屏障库；行空间静态等分 + 计数器（:627-698） |
| host/协调线程 | 提交前单线程做激活预处理，再睡 sync_cv（:1911-1968） | host 亲自抢任务算（pool.cpp:693,823-833） |
| 任务切分 | (token,route,32 行) tile，B≥2 同专家重复流（:1582-1678,:1100-1101） | 按 distinct 专家分组，行空间跨专家等分，权重只流一遍 |
| GPU 等待 | cuStreamWaitValue64，不占 SM（cpu_moe_ext.cpp:659-664） | 图内 wait_flag_ge 自旋核（verify_kernels.cu:970,1151-1198） |
| 合并 | H2D 后 GPU bf16 逐元素加（layers/moe.py:383） | 图内 copy_rows_from_mapped + moe_hit_add（verify.cpp:1477-1483） |
