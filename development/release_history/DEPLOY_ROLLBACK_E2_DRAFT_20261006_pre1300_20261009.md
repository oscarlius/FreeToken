# E2-base.1 部署与回滚手册草稿

10:29当前状态：R066b/b128已独立终审+D04 kept，实际1服务/4调用，无重试，两对均含own、无other/U+FFFD/非法control，热8256与独立冷0/0有实际缓存/并发证据。R063/b129已续启原授权4服务/48调用的D12默认关闭门（8f6a912 E3分支，不是合入481发布候选）。发布门待R063终态；D不补跑，D20只读同end查找问题已确认。未建分支、部署、推送；下述旧状态按时间保留为历史。

以下早期状态按时间保留，仅作历史；当前判断以前述状态及[R066封存报告](../plan/01_测试与调研/results/T20-E2-R066_20261009.md)为准。

当前授权（2026-10-09 08:44）：R065 原 not_met 保留，用户纠正其冷/热比较判据；按 [R066 授权](../plan/R066_DISCRIMINATE_V2_AUTHORIZATION_20261009.md) 验证 B 普通冷请求、D 同结构冷参照、C 并发及串号，共3服务/6调用。全部满足后立即跑R063，随后按08:30第5条闭合并提交方案。warm2处置已完成；以下旧阻塞状态为历史，当前R066启动复核中，未建分支、部署或推送。

最新阻塞：R065服务A同进程长请求冷/热全文不等，条款a不满足。B/C、R063未启动，发布门不能闭合；以下启动和release/e2方案保持草稿，未执行分支、部署或推送。

08:30补充状态：[新指令](../plan/SUPPLEMENT_20261009_0830.md)已批准R065在481候选上做3服务/7调用判别。warm2[只读处置](WARM2_READONLY_DISPOSITION_20261009.md)已完成并移出正确性发布门；R065通过后按新D16口径闭合并提交发布方案。以下07:34停止状态为历史。当前未建分支、部署或推送，三者仍分别审批。

本文件只供审查，部署、分支创建和回滚命令均未执行。生产部署、创建 release/e2、任何远端推送须用户逐项批准。[2026-10-09 01:00 指令](../plan/ROOT_EXECUTION_DIRECTIVE_20261009.md)定义发布门为T17 + R041 + T20（含 D16 补项）+ OOM 恢复，E3优化不阻塞发布；其冲突条款由[01:30夜间授权](../plan/NIGHT_PREAUTH_20261009.md)覆盖。

当前状态（2026-10-09 07:34）：T17、R041已通过；新OOM候选481d3a7的R064默认门4/48已kept，R061f恢复1/3已独立24项终审通过并D04 measured。R061c保留not_met，R061d/e保留failed_harness。D16的R040i就绪轮询失败已封存，R040j在原6/8范围中完成6调用，长请求全文不等，07:27停止并已D04封存not_met；R063及后续GPU等待用户裁定。R040h仍为待定，warm2缺少真实命中证据，继续跳过。发布门尚待D16不等价问题及warm缺口的裁定，未建release/e2、部署或推送。最新机器可读准备状态见 [10-09候选草稿](../plan/data_releases/E2_RELEASE_CANDIDATE_DRAFT_20261009.json)。

## 已核实的源码身份

- 基础：`0aa23431e5b800797543bdecbf35a01045131d7d`。当前待验收发布候选为 `/data2/FreeToken/wt/e2oom-protocol-restart` 的 `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9`，2026-10-09 只读复核 clean。阶段祖先链为 `0aa23431 → 4c878f6 → d577e32 → 481d3a7`；首段包含 9 个提交，4c 的直接父为 608251f，后两段为直接 Git parent。4c 的 R060c kept / R061c not_met 保留；d577 修复 OpenAI chat/completions 准入，481 补全 messages/responses。新候选已通过五个路由测试模块 124 项，以及真实公开路由 SDK 八项重启回归，实际GPU默认门R064 kept与恢复门R061f measured已分别通过。完整父链与各步门证据见 [候选父链](OOM_RELEASE_CANDIDATE_CHAIN_20261009.md)。
- D16 工装修复树 `effb996` 的直接父提交为 `0aa23431`；它和 OOM 候选是不同开发分支。不得把工装分支或 E3 优化 HEAD 自动合并入发布候选。
- 回滚检出：`/data2/FreeToken/src/FreeToken`，HEAD `184c965964b5f79deaecf1b1e3e0eda3187c829d`，2026-10-09 只读复核 tracked clean。保留原检出，不原地覆盖。
- 环境：`/data2/FreeToken/venv`；权重：`/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay`。

## 批准后的分支方案

以下是待批准方案，不执行任何 fetch/push，也不切换旧生产检出：

```bash
RELEASE_COMMIT=481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9
git -C /data2/FreeToken/src/FreeToken branch release/e2 "$RELEASE_COMMIT"
git -C /data2/FreeToken/src/FreeToken worktree add /data2/FreeToken/wt/release-e2 release/e2
```

执行前复验分支和目录尚不存在；存在不能覆盖。最终提交必须绑定对应新OOM候选的T16 kept与完整故障注入验收、全部业务结果和独立封存，以及用户对发布和本项操作的明确批准；旧608251默认门不能代替修复后新提交的门。性能取R056，T20补项及60题口径独立记录。启动前只查前置MANIFEST/round.json SHA、只读位与D04 history，不重读原始文件。R040保持failed_harness，不因局部PASS改判。

## 启动配置与交接

T20 实际参数为 `taskset -c 1,3-47`、GPU0、offload、NVFP4 Triton、PLE pinned、比例0.88、请求上限2、graph上限2、窗口73728、层优先4096和 special-token checkpoint。发布配置改窗口98304；其余参数沿用，工作树指向通过 OOM 恢复门的最终 release-e2。OOM 恢复默认开启、故障注入关闭，重启期间队列上限/超时及错误协议须按最终验收记录配置。生产不带 FT_DEV/FT_T17/FT_D16/FT_D3 捕获或 route trace。当前未部署。

R056实际98304/.88配置下，主KV slab约2.25GiB、初始化剩余约2.50GiB；两次完整87,100提示均完成，请求后显存样本约0.357GiB。该值为边界采样，不能当作连续最低余量。32K解码中位34.33 tok/s，较历史73728窗口的38.30下降约10.4%，作为发布配置变化披露，不据此改判T20或自动发布。

完整 seed_real 首请求87,100 token，不能截短。超过98,304仍拒绝（已知差距：Strata131,072）；seed_45k实际约1.2万token，名称不改。窗口是配置变化，T17、R041不重跑；R056与旧T20的比较明确标注73,728→98,304，正确性证据继续沿用。

启动前再核实实际服务管理器、生产端口、日志路径及旧服务PID/出生标识；当前文档没有臆造 systemd unit 或停止命令。仅在队列允许的空闲窗口且无其他 GPU 锁时启动。不得连接8095或任何被现有任务监听的端口来做部署探测。

待批准的直接前台启动命令：采用历史生产入口8095，TCPStore8096。2026-10-09 09:35仅用ss只读核查两端口均无监听，未作HTTP探测；执行前须再次核实。没有现成FreeToken systemd unit证据，故本方案为直接前台启动，终端日志及PID/出生标识随批准后的执行记录保存。

```bash
export PYTHONPATH=/data2/FreeToken/wt/release-e2/python
export VIRTUAL_ENV=/data2/FreeToken/venv
export CUDA_VISIBLE_DEVICES=0
export MASTER_PORT=8096
export PATH=/data2/FreeToken/venv/bin:$PATH
taskset -c 1,3-47 /data2/FreeToken/venv/bin/ft serve \
  --model-path /data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay \
  --served-model-name Qwen3.8-Flash-Next-NVFP4 --host 0.0.0.0 --port 8095 \
  --memory-ratio 0.88 --moe-cache-auto --moe-prefill-hit-d2d --ple-backend pinned \
  --moe-strategy offload --quant-backend moe.nvfp4=triton \
  --max-running-requests 2 --cuda-graph-max-bs 2 \
  --kv-reserve-tokens 98304 --max-seq-len-override 98304 --max-prefill-length 4096 \
  --enable-cache-report --tool-call-parser qwen3_coder --reasoning-parser qwen3 \
  --prefill-layer-major --enable-special-token-ckpt --mamba-host-slots 0
```

这不是新增验收轮次。记录实际导入路径、commit、完整argv与解析配置，再确认目标业务请求能正确完成；健康HTTP成功单独记录，不能代替业务正确性。

## 观察与回滚

已验收恢复逻辑应在 OOM 时保持 API，明确终止受影响请求、隔离旧 worker 并重启，重启期间有界等待。单次 OOM 与成功恢复记录在生产日志；重复 OOM、重启失败、错误生成/命中续算或持续服务错误需保存时间、API/worker epoch与日志，再按批准的回滚流程处理。停止只按本次发布记录的 PID/出生与进程组，不使用 killall，不删除别人的锁。

回滚点为保留的184c965检出。该版本含K1，使用普通8192分块，不能启用层优先。E0历史轮次没有独立的 `ft_rounds/E0-R002` 目录；规则第3节映射到 `_e0/paper_headroom_20261003/`，轮次登记在旧轮次库。已只读核实 `serve_final_8192.log` 的解析参数：窗口49152、分块8192、special-token checkpoint开启、offload与图上限2。不能称其为当前D04规范下的独立封存轮次。

批准后的回滚启动骨架如下，实际生产端口、管理器和日志仍须在执行记录中绑定；这段只写入文档，未执行：

```bash
export PYTHONPATH=/data2/FreeToken/src/FreeToken/python
export VIRTUAL_ENV=/data2/FreeToken/venv
export CUDA_VISIBLE_DEVICES=0
export MASTER_PORT=8096
export PYTHONUNBUFFERED=1
export PATH=/usr/local/cuda-13.0/bin:/data2/FreeToken/venv/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-13.0/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
numactl --cpunodebind=0,1 --interleave=all /data2/FreeToken/venv/bin/ft serve \
  --model-path /data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay \
  --served-model-name Qwen3.8-Flash-Next-NVFP4 --host 0.0.0.0 --port 8095 \
  --memory-ratio 0.88 --moe-cache-auto --moe-prefill-hit-d2d --ple-backend pinned \
  --moe-strategy offload --quant-backend moe.nvfp4=triton \
  --max-running-requests 2 --cuda-graph-max-bs 2 \
  --kv-reserve-tokens 49152 --max-seq-len-override 49152 --max-prefill-length 8192 \
  --enable-cache-report --enable-special-token-ckpt \
  --tool-call-parser qwen3_coder --reasoning-parser qwen3
```

配置来源为 [历史生产命令](../RESULTS_FT_COLD32K_20261002.md) 与 [8192复核记录](../RESULTS_FT_PAPER_HEADROOM_20261003.md)，并与上述归档日志的解析参数对齐。回滚保留已核实的49152窗口；不能把新候选98304窗口无审查地套在旧版上。实际停止/启动只针对批准时绑定的所属服务PID及出生标识，不套用历史日志中的旧PID。

恢复后用原生产入口验证业务请求并观察8099监控/日志。失败则保留诊断并报告，不自行改判或切换其它候选。

## SSH 凭据

`_shared/ssh_exec.py` 仅从 `FT_SSH_PASSWORD` 读取密码，缺少变量在连接前报错。通过安全会话注入，不在命令示例、日志、文件或提交中写值；也可使用已配置的 OpenSSH 身份。发布准备没有推送任何仓库。
