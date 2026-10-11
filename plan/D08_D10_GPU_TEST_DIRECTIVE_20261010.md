# D08 hybrid 两路 + D10 η 微基准：GPU 测试指令（归档版）

- 来源：主会话 2026-10-10 约 23:50 在对话中下发的指令。当时没有落盘，本文件是事后补的归档；内容与对话版一致，补充的冻结引用、启动参数和核对项在下文标注「〔归档补充〕」。
- 批准：用户 2026-10-10 晚原话"D08、D10可以一起测试"；压力测试已在对话中告知用户。
- 状态：未执行。执行前必须完成第五节核对清单。推送未批准，ollama 保持停用。
- 相关文件：`CLOSURE_JUDGMENT_20261010.md`（判定依据）；`D10_REANALYSIS_20261010.md` 第八节；闭环冻结件 `development/d10_reanalysis_20261010/closed_loop_20261010/INPUT_FREEZE.json`。

## 〇、顺序与预算（一个 GPU 窗口，总计 ≤35 分钟，超时就停下并回报）

0. **CPU 阶段（GPU 窗口之前）：**
   - 第二节 η 脚本的开发，限时 1 小时；
   - D05/D09 CPU 回放（另一份指令），可与上一项并行；
   - 两项都完成后才开 GPU 窗口。GPU 测速期间，测试服务器上不跑 CPU 计算。
1. **单路 offload 参照：** 在已恢复的 481 服务里发 1 条请求，用 X 的 lane0 提示，约 1 分钟。
2. **停 481**，然后依次跑：
   - 第二节 D10 η 微基准（进程内加载 1 次引擎）；
   - 第一节 D08 hybrid（1 个服务，单路 1 次调用，两路 2 次调用）；
   - 恢复 481，做 SDK 冒烟，观察窗口从恢复时重新计时。
3. 每一步写一行日志；全部完成后立即回报，不等 09:00。

**压力告知（用户已知悉）：**
- hybrid 运行期间约 21 个 CPU 核满载，约 3 分钟；
- η 微基准期间 PCIe 满载，约 1 分钟；
- 481 中断约 30 分钟；
- 并发 ≤2。

## 一、D08 hybrid 两路

### 1. 负载〔归档补充：冻结引用〕

- 输入：`closed_loop_20261010/inputs_X.jsonl`，SHA256 `f63b3623bbb0ab10b0001d68a20138fb15a0ce8893f3a2d4c0202825a22a1162`。两条不同内容的长文提示，输入 1,179 / 1,231 token。
- 生成参数：temperature=0，max_tokens=256，ignore_eos=false。两路都必须以 finish_reason=length 结束，否则该臂无效（不能当负结果用）。
- 顺序：先发 1 条单路（lane0 提示），再同时发 2 条。

### 2. 速度口径〔归档补充〕

必须与闭环完全一致：`INPUT_FREEZE.json` 的 `"metric": "AIPerf inverse inter_token_latency, same Y CLI settings"`，AIPerf CLI 参数与闭环 X 组相同。不允许换口径。

### 3. 配置〔归档补充：精确 argv 要求〕

- **基线 argv：** 已恢复的 481 服务（481d3a7）的完整 argv。
- **只允许两处改动：**
  - `--moe-strategy offload` 改为 `--moe-strategy hybrid`；
  - 加前缀 `numactl --interleave=all taskset -c 1,3-23,25,27-47`，即 R048b S 臂的绑核方式，21 个执行器线程。
- **R048b S 臂原始命令**（`/data2/_shared/runs/ft_rounds/E2-R048b/batch111/S/performance/SERVE_CMD.txt`），只作参照：
  `numactl --interleave=all taskset -c 1,3-23,25,27-47 … serve --model-path …/Qwen3.8-Flash-Next-NVFP4-overlay --memory-ratio 0.88 --moe-cache-auto --moe-prefill-hit-d2d --ple-backend pinned --moe-strategy hybrid --quant-backend moe.nvfp4=triton --max-running-requests 2 --cuda-graph-max-bs 2 --kv-reserve-tokens 98304 --max-seq-len-override 98304 --max-prefill-length 4096 --enable-cache-report --enable-special-token-ckpt --tool-call-parser qwen3_coder --reasoning-parser qwen3 --mamba-host-slots 0`
  （R048b 用的是候选 76af758 加 observer 包装。）
- **commit：** 优先用 481d3a7。如果 CPU 准入阶段发现 481d3a7 不接受 `--moe-strategy hybrid`，改用 76af758（D08 埋点保持默认关闭），并在结果里写明 commit 不同。
- **argv 差异：** 运行前把实际 argv 与 481 恢复服务的 argv 做逐项 diff 并封存，除上述两处外不允许有任何差异。

### 4. 记录

- 每路解码 tok/s（口径同上）；
- serve.log 中 `--moe-cache-auto` 解析出的 moe_cache_size（应为 2,700。偏差超过 5% 时列为混杂因素）；
- moe_hybrid_max_fetch 的实际取值与语义；
- 运行中的 CPU 利用率快照、执行器线程 `taskset -pc`、`numastat -p <pid>`（按 D08 环境复核的要求采集）。

### 5. 预登记判据

参照值：offload 两路 X 实测 **16.951013 / 17.014054**（闭环，481 生产服务）。

| 结果 | 判定 |
|---|---|
| H1：hybrid 两路每路都 ≥ 19.6（offload 的 1.15 倍） | hybrid 对两路有价值，回报用户，由用户决定下一阶段 |
| H0：每路都 ≤ 17.0 | D08 在两路上也关闭；连同单路负结果，D08 在当前执行器上整体关闭 |
| 介于两者之间 | 不确定，如实回报，不追加 GPU |
| 任一路 < 7.8 | 异常：先查绑核与争用，不出结论 |

- 单路 hybrid 与第〇节第 1 步单路 offload 的比值只作记录（R048b 在 32K 时为 0.87）。
- 推算（未验证）：如果失误专家由 CPU 和链路并行承担，两路每路约 20–24。前提是按 R048b 粗估的 CPU 有效速率约 18 GB/s，这个前提没有单独测过。

## 二、D10 重叠前提：η 微基准

目的：D10 的理想上界 23.9（闭环 m=38.24%，链路受限）假设搬运和计算完全重叠（η=1）。这一节直接测 η，不开发 D10。

1. **脚本：** 只在独立工作树里新增一个默认关闭的脚本，不改发布路径。进程内加载引擎（可用 offline_mode），用一个固定 token 重复解码，预热到全部命中，然后捕获 bs=1 解码图。
2. **测量**（CUDA event，各 50 次，取中位数）：
   - **T_comp：** 连续回放两次 bs=1 图，模拟两路计算。
   - **T_copy：** 用真实的 `fast_index_copy_multi_jit`，从 pinned host bank 拷 **367** 个专家（= X 两路每步失误量 2 × 0.3824 × 480）到空闲槽。〔归档补充〕约束：
     - 只写数据行，不改 slot_for_id / id_of_slot 映射表；
     - 目标槽与图回放用到的槽不能重叠（固定 token 下大约用到 480 槽，空闲 ≥2,200）。
   - **T_both：** 两者放在不同 stream 上同时发出；在共同起点和汇合点各记一个 event。
   - **η = (T_comp + T_copy − T_both) / min(T_comp, T_copy)**。另外报告并发时 T_comp 自身变慢了多少。
3. **对照模型：**
   - T_copy 预期约 41.9 ms：367 × 2,772,480 B = 1.0175 GB，B_P = 24.3 GB/s；
   - T_comp 预期约 26.2 ms：2 × t0，t0 = 13.1 ms，短上下文；
   - 任一偏差超过 ±20% 时，先报告偏差，不计算 η。
4. **预登记判据：**

   | η | 判定 |
   |---|---|
   | ≥ 0.8 | D10 现实上界约 ≥21/路（单路 17 的 1.25 倍），列为开发候选回报用户；开发需 10–20 人日，另行审批 |
   | < 0.5 | 现实上界 ≤ 18.2/路，收益不到 7%，D10 关闭 |
   | 介于两者之间 | 如实回报 |

5. **限时：** 1 小时内如果做不到"图回放 + 并发拷贝"，就跳过本节并说明原因。不能用 eager 循环代替：eager 会被 CPU 派发拖慢，测出的 η 无效。

## 三、范围外

- D05/D09 回放另有指令（主会话 23:54，见 D05/D09 卡顶部注记和协调日志 23:54 条）。
- 论文 v5.4 由主会话负责，Codex 不改论文。

## 四、纪律

只追加；每步写一行日志；结果经独审后回报；推送未批准。

## 五、GPU 执行前核对清单〔归档补充〕

1. X 输入文件的 SHA256 等于 `f63b3623…a1162`；生成参数与第一节第 1 点一致。
2. 速度口径（AIPerf ITL 及其 CLI 参数）与闭环 X 组逐项一致。
3. hybrid argv 与 481 恢复服务的 argv 逐项 diff，只有第一节第 3 点允许的两处差异；commit 已记录。
4. moe_cache_size 解析值已记录（预期 2,700）。
5. η 脚本已通过 CPU 自检：映射表不被写、目标槽与图回放的槽不重叠、两条 stream 汇合正确。
6. D05/D09 回放和 η 脚本开发都已结束，GPU 窗口期间测试服务器上没有 CPU 计算任务。
7. ollama 处于停用状态；记录 uptime 和 R 态线程数。


## 修订 v2（主会话，真实写入 2026-10-11T00:29:48+08:00）：第一节 D08 只加预登记预测和记录项，不加 GPU 配置点

依据：`development/strata_0142_review_20261011/r048b_hybrid_split_analysis.py` 及其输出（R048b S 臂诊断数据，只读）。起因：评审 Strata 0.1.42 时考虑过"按 Strata 公式再加一个分流比例配置点"，经数据复核否决。

1. **不加第二个分流配置点。** R048b 数据显示：
   - 我们 hybrid 的 CPU 边际成本是每个专家 0.084 ms，比 PCIe 的 0.114–0.18 ms 还低；
   - 真正的瓶颈是每层 0.207 ms 的固定开销，即使交给 CPU 的专家数为 0 也要约 0.13–0.19 ms；
   - 分流上限实测为每层最多 3 个专家走 PCIe（第 0 步 7/3；稳态 PCIe 份额：单路 0.205，两路 0.238）。

   所以把更多专家改走 PCIe，对单路基本没有好处。Strata 那套公式基于它自己执行器的成本结构，不适用于我们。
2. **预登记预测**（推算，不作判据）：
   - R048b 诊断模式下，两路步长只比单路长 13%（47.1 对 41.6 ms），原因是两路共享那份固定开销；
   - 按这个比例换算到性能模式，32K、m≈29% 时 hybrid 两路每路约 27–28 tok/s；
   - X 负载（1.2K 输入，m≈38%）失误更多，预测区间放宽为每路 19–27 tok/s；
   - 实测落在区间外时，报告偏差并分析，但不改判据。
3. **判据维持原 H1/H0。** 新增一条：如果结果 ≤17.0，结论必须写明"只关闭当前执行器（含每层固定开销）的两路收益"，不关闭"去掉固定开销后的 hybrid"。去掉固定开销的手段是 D08 卡原计划第 2 项"移植 Strata 线程池：空闲时休眠、不自旋"，这一项从未实施。
4. **新增记录项**（不改变测量本身）：
   - `moe_hybrid_max_fetch` 的实际语义、取值，以及对应代码行；
   - 性能模式下不开 trace 和 D0，以免扰动计时。如果计数只能靠 D0 或 trace 采集，就不采，只记录 argv 默认值。
5. **GPU 预算不变**（≤35 分钟），服务数与调用数也不变。
