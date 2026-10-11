# D3 线性注意力多锚检查点：实施与验收（2026-10-03）

状态：**第一步（锚点集合匹配 + 预填锚封顶）已实现并测出数据；主体未完成。**
回放门「编辑后轮次首 token ≤ 4 s」只在**整段重发**场景通过（2.69 s），在**中途编辑**场景失败（8.14 s，零复用）。根因已用树导出与捐赠跟踪定位到一行代码，见 §4。

分支 `dev/d0-instrumentation`，远端 `/data2/FreeToken`，端口 8095。生产参数未动（`--memory-ratio 0.88`、`--ple-backend pinned`、`--moe-prefill-hit-d2d`、窗口三件套 49152），启动命令 `/data2/FreeToken/scripts/start_d3.sh` = 生产参数 + `--prefill-layer-major --enable-special-token-ckpt`。

## 1. 已实现的改动

| commit | 内容 |
|---|---|
| `e92fdf5` | 锚点集合匹配：`d3_extra_anchor_ids = {</think>, <\|im_end|>} \ {opener}`，逐 id 校验单 token；解码命中改集合判定 |
| `cd450be` | 预填锚封顶：`_add_one_req` 扫描 prompt token ids，命中锚点集合时把 `chunk_size` 截到该锚的页对齐边界 |
| `17345b3` | `PrefillAdder.anchor_ids` 字段（修 TypeError） |
| `52abf50` | `FT_D3_ANCHOR_MODE=first\|last` 切块粒度开关（默认 last） |
| `3b6fde3` / `194fa22` | `FT_D3_TREE_DUMP=1`：调度器空闲时导出 radix 树每个节点的 `end:mamba_slot:refs:len` |
| `74a824a` | `FT_D3_TRACE=1`：每次捐赠打印 `cached_len / L / extend_len` 与捐赠后的树 |

## 2. 回放结果（3 轮，生产默认 last 粒度）

轨迹：7 轮对话（每轮约 2160 token），第 5 轮内容分叉。

| 轮次 | 含义 | prompt tokens | 首 token | 前缀命中 |
|---|---|---|---|---|
| R2_cold | 冷，全新 | 13181 | **7.93 s** | 0 |
| R1_warm | 第 5 轮换成长文本，与 R2 公共前缀 8756 | 15332 | **8.14 s** | **0** |
| R2_warm_anchors | 换回 R2（整段重发） | 13181 | **2.69 s** | 13120 |

对照 D1 层优先的冷 32K 结果（13.1 s）与基线 21.52 s：锚封顶没有拖慢冷启动，13181 token 的 7.93 s 属于 D1 层优先的正常水平。

`first` 粒度（每个轮次边界都切一段，8 段）实测更差，**已否决**：R2_cold 23.0 s、R1_warm 21.4 s、R2_warm 2.73 s。冷启动慢 2.9 倍而 R1 依旧零命中。

## 3. 为什么 first 粒度救不了中途编辑

切得更碎本该让每个轮次边界都拿到快照。捐赠跟踪（`FT_D3_TRACE=1`）显示每个请求**只发生一次**捐赠，且发生在预填→解码过渡步：

```
[D3-DONATE] cached_len=13182 L=13120 ext=1 ping=(11, 10) next=0
[D3-DONATE]   committed@0 exist=False tree=0:None:0:0 | 13120:10:1:13120
```

`ext=1`、`cached_len=13182`（= 完整 prompt + 1）说明这条打印来自解码步，8 个预填分段一次都没进捐赠分支。空闲时的树导出同样只看到**一个**节点：

```
0:None:0:0 | 13120:10:0:13120
```

即：整棵树上只有结束捐赠的 13120 一个 GDN 快照。R1 在 8756 处分叉，而唯一快照在 13120 —— 比断点还靠后，`match_prefix`（只会回退到**最深**的带快照节点）只能返回 0。

## 4. 根因（推翻本文档上一版的判断）

上一版写「非 finish 提交 + 捐赠已存在，D3 主体 = 锚封顶」。**这是错的。** 树导出与捐赠跟踪都否定了它。

`scheduler/scheduler.py:_process_last_data` 循环开头：

```python
for i, req in enumerate(batch.reqs):
    if isinstance(req, ChunkedReq):
        # Don't cache intermediate chunks; the full prompt is cached once when the
        # final chunk is processed. Caching here snapshots a handle the next chunk
        # already copied (overlap), so cache_req double-frees the prior chunk.
        ...
    elif batch.is_prefill and req.table_idx != -1:
        self.cache_manager.cache_req(req, finished=False)   # 中间块永远走不到这里
```

引擎**显式跳过**中间预填块的缓存提交。作者给的理由是 overlap 调度下下一块已经拷走了 handle，此处再提交会重复释放页。因此 `cache_manager._cache_req_hybrid` 的非 finish 分支虽然写着「Prefill chunk commit: donate the frozen snapshot」，在分块预填下**从不执行**——它只在整条提示预填完、进入解码过渡的那一个 batch 上跑一次，捐一次。

这也解释了 `#mamba-slot` 全程 3/12：捐赠后立刻补一个替换槽（树取走一个、我方补一个），净变化为 0；只有结束捐赠不补，才升到 4/12。**不能用这个计数判断捐赠是否发生**，树导出才是可靠信号。

所以 D3 的核心工程项是这一行本身：让锚块能做中间提交，且不触发注释里说的 double-free。

## 5. 剩下的工作（按序）

1. **锚块中间提交**（阻塞其余全部）。可选路径与代价：
   - (a) 锚块关掉 prefill overlap，drain 后安全提交。改动最小，但牺牲搬运/计算重叠，预填变慢。
   - (b) 锚块提交时只 insert 不 free、不改 `req.cache_handle`，让树节点与请求**共享**页所有权；需要在页释放路径上识别「树也引用」，属 `_free_req_slots` / `_free` 的所有权语义改动。
   - (c) 提交后重指 handle、但把下一块的 overlap 延后到 drain 之后。折中，需改 overlap 调度时序。
   这条要独立评审，作者的注释说明 double-free 不是想象出来的。
2. **每请求多快照槽**：`linear_state_pool` 每槽 115 MB，12 槽 = 1.38 GB，当前 `ping-pong` 只有 2 个槽、一轮只捐一个。多锚需要按锚 alloc 独立槽 + LRU 挂树节点回收。
3. **恢复选择**：`HybridRadixCache.match_prefix` 已经会「回退到最深的带快照节点」，锚够密时这一步自动成立；但需要一个「断点前最近存活锚」的显式指标（重算 token 数、锚命中率）来接 D0 埋点通道。
4. **验收脚本升级**：`/data2/FreeToken/scripts/d3_trace.py` 目前 3 轮、只发 prompt。方案要求 ≥10 轮真实 OpenCode 轨迹（含工具调用与思考），并且要有一个**真中途编辑**的用例（现在 R1 是唯一的中途编辑用例，它没过）。

## 6. 风险

- 中间块进 radix 改变缓存语义（内存、驱逐、与 prompt-end pin 的交互）。
- 锚封顶会缩小 chunk → 与 D1 层优先的「整池只搬一次」冲突。实测 last 粒度只切 2 段，冷启动无明显损失；一旦为多锚切细就会退化（first 粒度 23 s）。**D1+D3 的组合规则应是：首轮全量准入，只有重算后缀才按锚切段。**
- 页对齐与 ×CHUNK track 的 state_len 约束（PLE conv 历史 ≤ CHUNK_SIZE=64）。注意 `boundary = cached_len + ((extend_len-1)//64)*64` 总是落在块末前 64 token 处，不是块末本身；节点长度与快照状态是自洽的，恢复正确，但锚点标注要按这个偏移理解。
- 层优先路径的 `_build_layer_major_chunks` 给所有子块复用**同一个 `Req` 对象**，`r.extend_len` 在每个子块上都是整段长度。大提示（子块数 >1）时 `_build_track_metadata` 会按整段长度反复写快照并翻转 ping-pong，可能取到两个子块之前的陈旧槽。13K 提示只有一个子块，没暴露；32K 有 8 个子块，**做 D3 之前必须先验这一条**。

## 7. 与其它开发项的关系

- D1 的 ≤9 s 差距已定性为 MoE 分组 GEMM 内核瓶颈，另立内核优化任务，本次未动。
- D2 按规则停做。D4/D5 未动。
- D3 第一步的两个改动（`e92fdf5` 锚集合扩展、`cd450be` 预填锚封顶）**挂在 `config.special_token_ckpt` 上，不是 `FT_D3_*` 环境变量**；生产启动命令 `runs/cold32k_20261002/SERVE_CMD.txt` 带 `--enable-special-token-ckpt`，所以用生产参数启动就会执行这两条路径。本文上一版写的「所有新增代码默认关闭、生产启动命令未变」**不成立，已撤回**：`FT_D3_*` 三个诊断开关确实默认关，锚集合扩展与锚封顶默认生效。「生产未动」目前只是声明，需与 main 做 A/B 才能证实。
- 反向缺陷：`scheduler.py:150` 无条件读 `self.d3_extra_anchor_ids`，而该属性只在 `if config.special_token_ckpt and (is_hybrid or is_swa)` 分支内赋值（`config.py:20` 默认 False）。不带 `--enable-special-token-ckpt` 启动会在 `Scheduler.__init__` 抛 `AttributeError`，服务起不来。
