# R056 §12 工装源码与 CPU 交付

泳道 02 只新增 `r056_long_context_prepare.py`、`r056_performance_memory_observer.py`、定向 tests 与本文，协调日志只追加。根独占远端冻结、Linux CPU、真实文件 dry、R 启动前复核与 GPU 启动。未改 R046b/R049、产品代码或任何冻结源；未启动服务、请求模型端口、取锁、分 batch 或创建正式 RID。

## 测量契约

固定 `E2-R056`、发布树 `0aa23431e5b800797543bdecbf35a01045131d7d`、候选 `/data2/FreeToken/wt/e2base1-ordinary-rewind`。正常科学参数复用 D07；仅 KV/seq 改为 98,304，性能保持 0.88，无 D0、route trace 或 pause。继承环境中的 FT 开关全部清掉。

三次串行 fresh 服务，共 11 条请求：

| 服务 | 请求 | prompt / max_tokens | 冷证据 |
|---|---|---|---|
| production | cold32 ×4；cold64 ×2；short ×3 | 32,064 /128；65,424 /128；23 /128 | cold32/64 用原 probe 的不同 cold_id，实际 usage 必须 cached_tokens=0 |
| cold87_0 | seed_real 首完整请求一次 | 87,100 /2,048 | fresh owned 服务，保留 cached_tokens 原样 |
| cold87_1 | 完全相同的首完整请求一次 | 87,100 /2,048 | 第二个 fresh owned 服务，保留 cached_tokens 原样 |

87K 不加 unique 前缀、不截断 seed、不改 TASK/tools/thinking；两次 payload 字节摘要一致。原 SSE usage 若没有 cached_tokens，结果记录 `cached_tokens=null` 与 `cached_tokens_reported=false`，由不同 fresh owned 服务 birth 证明冷启动，不制造 0。若实际报告 cached_tokens 非 0 则拒绝。首枪 cold32_0 单列，32K 中位数只算其余三次。

已核原 T20 `ft_perf_decomp.py` short 构造用 **max_tokens=128**、temperature=0、thinking=false；历史实际 completion=120 是 stop 提前结束，不能把该值改作新请求预算。32K 原 builder target=32,052，实际 chat prompt=32,064；64K target=65,412，实际=65,424。正常九条复用原 T20 content-only 首 token/解码统计；87K 正式 ttft_any 与解码速度用 raw SSE 的 reasoning/content/tool-argument delta 到达时点，可从 stream.jsonl 复算；原 agent yield 后的 ttft_any 保留为 `original_agent_ttft_any_s` 观察值，明确标注与 T20 content-only 不同。

R 签前发现 v1 的两项 P1 已在本地 v2 窄修：前九条 wire SHA 按实际 PERF 的 `json.dumps(payload)` 默认 ensure_ascii=True，87K 按原 agent ensure_ascii=False，均保留原字典插入顺序；不从 sort_keys 的归档重读来计算 wire。87K 正式 ttft_any 改用 raw 第一条有效 delta 的 relative_seconds（round3），不把写盘后 consumer 的 clock 混入。科学 payload/采样、RID、窗口、比例保持不变；服务器冻结 v1 不改，新 source/dry/review 路径及三类准入 schema 用 v2。

只读历史小 summary SHA `04abeb2657b7b0da693ad6d43ca03da6f2098fff122ad06c244512d4c2b147ce`，实际 R040 args SHA `6816c859626948e89d0e7a089fb0d08ae7d4c2c534bc9fb3fa917cd464ac171b`。已核旧 KV/seq 是 **73,728**，因此新数字只作 98,304 对 73,728 的跨窗观察，不作 same-window 收益或 7% 判据。小 summary 未保留旧首枪，新 comparison 明确 nullreason，不重读旧 raw。

## 输入与观察器

绑定独立 R 的实际 0aa handler/frontend CPU 报告：`/data2/FreeToken/runs/dev_R056/r056_seed_real_cpu_input_v1.json`，SHA `770071f74ede52ae0e6ba6de012785847bd6ca118637e43e3667f50ccb2d54bc`。其执行 receipt SHA `099fc2243459a28630e53384d94d9ff4690e658cc683cc0d4b70e2bb49c780dd`，二者 0444。入口核报告 schema、候选、真实 87,100、原 max2048、thinking/tools、源与 tokenizer/config SHA，再复用原 agent build_payload，并核 canonical/wire payload SHA。87,100+2,048=89,148，窗口剩余 9,156；这仅证明第一条请求容量，不代表后续会话、启动或显存已通过。

原 agent 实际 SHA `332a1870378d5bffa4891180280060e70f6135b6acff21b48603a5fc98ad44d9`；seed 原 SHA `8fe6b36da6c19eabb4a259535a9835f20e41921d4d7023ec7aaa0063c8b50bf3`。canonical payload SHA `247d28a3ebffd70c0be8ed915cce8e04f8f12dd1959fd260bb436e2d3f04bd97`，原客户端 wire SHA `3fd73a1e295e28a4afaf5b50e255504e6d8a26bbe0bd60b85cd981a4ea96cc8d`。

新 observer 在 `__main__` 和真实 spawn 重放的 `__mp_main__` 中、worker target 导入之前安装 Engine/Scheduler/IO hook，子进程保留父 service_birth。实际 Engine 初始化完成后记录主 KV slab 的 shape/num_pages/numel×element_size、free/total/allocated/reserved/cumulative peaks；**kv_storage_bytes 仅为主 slab，不包含 aux index 或 GDN，也不称总 KV allocation**。production 只采加载后；两个 87K 服务另采真实 UserMsg 请求前、finished DetokenizeMsg 发送前，绑定同一 UID、模型 worker birth 与 owned service birth。startup 保留原初始化 free 日志及新 R056_MODEL_LOADED 日志。

测量失败立即停止串行链，保留已完成请求、小增量 receipt 与 raw；所有性能 OOM/起服务后失败需根停下裁定，没有 0.80 性能 fallback。沿用现有 owned cleanup；第一次 startup cleanup 失败保留 owned_process/lock，不再重试来覆盖失败。

## 最小闭包及 CPU

实际运行同目录仅需四个源：

```text
r056_long_context_prepare.py              db4be62294fee0a7e7842254bd351f3fc653ebac8d4f34e8f18606e6683d3262
r056_performance_memory_observer.py       bd5240706c9f8977546af2f2c4ee3d761470be2d127abbcf602abc2eeee30a21
d07_g3g4_prepare.py                       c4a28aaa602536b3c1f5b94a77f9e18cd48443867f3c0cc8a029ab0531bbddd0
d07_r046a_file_prepare_v1.py              aca23df85e4e692ae037bc2609dbd3969472d3adce83d9105361f6fe44207040
```

定向 CPU 加三个文件，保持 tests 子目录：

```text
tests/test_r056_long_context_prepare.py   f00da137435b99f1ad5bd8a2be922ffdabc039baf9e178690248aed1fb96026b
tests/test_r055b_owned_launch.py          22bb17151776a0941ee75c15f33be28879f49180ac4c34c669435b053e89fd45
d16_cpu_sitecustomize.py                 887fe6dd9943f6359b09ee37d41089033f9d6e1e654c43f51e3a64158423637d
```

旧 test helper 只导入 fake-product/message，不执行旧测试全集，不需要 r055b_owned_launch 或 r055a_dryrun_base。运行的外部源直接复用 canonical probe、perf、发布树原 agent、只读输入报告、历史小 summary/args、canonical D04 writer，全部列入 `source_paths()` dry/review 绑定。seed 数据 SHA 与实际 frontend/tokenizer 源另由 packet/report 核验。已有 server owned 依赖 `/data2/FreeToken/runs/dev_D16/t20_startup_cpu_5d485bd933e4/source_tools/t17_owned_launch_protocol.py` SHA `7e1c05a79b856b6a99c3f8d9422afd7013b9ef0215c78e17427d205f78384dcf`，atomic `/data2/FreeToken/runs/plan_batches/e2_launch.py` SHA `a3924a63f7ea451972992857e78a2ba7b18c1cd9477e25ddfebb038614359acf`。不需要 D07 cold_eq helper，因为此入口不调用其冷等价接口。

v2 本地 guard + CUDA_VISIBLE_DEVICES 空 + PYTHONDONTWRITEBYTECODE=1：**18 passed，0 skipped，两个 source AST PASS**。包括真实 multiprocessing spawn 回归、实际 fileprep/dry 全 producer 路径、三服务十一请求顺序、readonly 源可写复制、同字节 87K/原采样、usage/cache 拒绝、失败停链与一次 cleanup、旧回执拒绝、跨窗首枪及 8095 网络拒绝。新增非 ASCII 请求通过实际 PERF.post_stream / agent.post_events 的 Request.data 捕获证明 wire 摘要，另用实际 agent.consume_stream 的消费 clock 晚于 raw 时点 1 秒的反例验证正式 TTFT/解码 raw 复算。测试直接用 canonical 既有 client；本地 agent 源与 release 仅行尾不同，LF-normalized SHA 为固定 332a187…，不改变运行时 exact SHA 检查。

Windows spawn 测试只为 `/proc` identity 提供 OS fixture；spawn、父/子进程与 hook 安装都实际执行。根已完成 v1 Linux15PASS/真实 FILEDRY，但 R 因两项 P1 未签；该证据不能代替 v2 Linux/新 FILEDRY。根 v2 Linux 重跑将使用真实 `/proc`；当前本地结果不能代替 GPU 证据。

## 根冻结后执行

根将上面七文件放入选定的只读 source_tools，保持四源同目录和 tests 子目录。设置 `R056_ENTRY` 为最终冻结入口的绝对路径，后续 dry/run 必须一直使用该 entry、同一用户/UID 和 `/data2/FreeToken` cwd。不用新 reader/framework/package。

Linux CPU 命令：

```bash
cd /data2/FreeToken
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import ast,os,runpy
from pathlib import Path
import pytest
entry=Path(os.environ['R056_ENTRY']);stage=entry.parent
os.environ['CUDA_VISIBLE_DEVICES']=''
runpy.run_path(str(stage/'d16_cpu_sitecustomize.py'))
for name in ('r056_long_context_prepare.py','r056_performance_memory_observer.py'):
    ast.parse((stage/name).read_text())
raise SystemExit(pytest.main(['-q',str(stage/'tests/test_r056_long_context_prepare.py')]))
PY
```

真实 file dry（根专属；调用正式准备函数全部路径，禁模型/锁/batch/RID）：

```bash
cd /data2/FreeToken
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import os,runpy,sys
from pathlib import Path
entry=Path(os.environ['R056_ENTRY']);os.environ['CUDA_VISIBLE_DEVICES']=''
runpy.run_path(str(entry.parent/'d16_cpu_sitecustomize.py'))
sys.argv=[str(entry),'--dry-run'];runpy.run_path(str(entry),run_name='__main__')
PY
```

dry sibling 固定 `/data2/_shared/runs/ft_rounds/.dryrun_R056_v2_E2-R056`，新 receipt schema `ft_r056_file_dry/v2`。复制只读源码至 runtime_sources 后显式 chmod0600，原源不变。各服务、十一条 request/inputs/stream/result、增量 receipt、raw manifest、comparison、preflight、failed/cleanup 与 metadata/pre_d04 路径全部实际写出 CPU probe，不签测量。

R 复核通过后在 `/data2/FreeToken/runs/dev_R056/reviews/E2-R056-v2/` 写只读 `review.json`（schema `ft_r056_startup_review/v2`，rid/candidate、verdict PASS、source_execution_ready true、sources 精确等于 dry receipt、dry_receipt_path/SHA）与 `pin.json`（schema `ft_r056_review_pin/v2`、rid、review_sha256）。入口再核同 entry/path/user/UID/cwd/source，旧版本回执拒绝。

正式根入口（CPU 与 dry/R 都通过才执行）：

```bash
cd /data2/FreeToken
/data2/FreeToken/venv/bin/python "$R056_ENTRY" --run
```

controller 直接复用已 pin 的 e2_launch reserve/publish-child 协议，不手动指定新 RID/batch。正式 raw 在 `/data2/_shared/runs/ft_rounds/E2-R056`，先输出 pending_review 的 result/pre_d04。根/R 按 completed_*.json 增量核各阶段，再复用 canonical `/data2/FreeToken/scripts/round_json_append.py`（SHA `67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff`）做最终 D04/只读封存；本入口不预造 canonical round/MANIFEST 或接受结论。
