# E2 发布方案（待 R066c 分类终审，2026-10-09）


> **11:52 当前状态**：R066c/b131已在独立启动签核与root实际admission后开跑，3服务/5调用冻结范围，服务X加载中；终审待定。R063a kept仅E3。发布门等待R066c分类c与D04，FTD/v5尚未生成，分支部署推送未执行。



> **11:45 当前口径**：用户已澄清逐字字符串判定与逐提示0/a/b/c分类；R066b四原始回复冻结前自检为异常/异常/干净/干净，与要求一致。R066c本地76、Linux101项CPU验证及实际FILEdry通过，候选481/3服务5调用，待独立启动复核后开跑。R063a kept只归E3，不绑定481门。C3按尾段≥65已证、≤64正确性待证。FTD/v5待R066c分类c终审；分支部署推送未执行。



> **11:34 当前状态**：R063a/b130 已独立终审+D04 kept，4服务/48调用与13/13完整尾段通过，78原件哈希不改，只归E3 D12；GPU释放。发布候选481门等待R066c共享前缀判别分类c，R066c CPU本地22/Linux47通过、原提示字节核对通过，尚未GPU开跑；分类“异常”含义待澄清。FTD/v5尚未生成，分支/部署/推送未执行。


> **当前状态（2026-10-09 11:20 用户修正）**：R063a/b130 继续完成终审封存，仅归 E3 D12（8f6a912），与发布候选481d3a7的门解除绑定。新增批准 R066c 共享前缀判别3服务/5调用，R063a释放GPU后执行；发布门等待R066c分类c与独立终审。D20缺口扩大为现算尾段≤64（含1）；T17仅覆盖尾段≥65。分支、部署、推送分别审批；Strata22/345未批准。以下早期状态按时间视为历史。


11:07当前状态：R063/b129已独立终审+D04 failed_harness，77原件不改；错误仅为合法PID后缀被新增断言误拒。第一次常设重试R063a/b130于11:06正式启动，原4服务/48调用；候选/配置/提示/判据不变，原cold_id显式冻结。v2 CPU本地/Linux34/34、实际FILEdry/独立startup和root四消费者通过。R066b c kept保持；发布门等待R063a独立终态/D04，FTD/论文v5尚未生成，未建分支、部署、推送。

10:57当前状态：R063/b129四臂结束后的比较报工装错误：新增默认关闭断言误拒合法PID后缀。独立actual参数与文本/full-tail复算确认failed_harness；原轮待D04封存，不记kept。新R063a仅复用原pinned strict_args修复断言，候选/配置/输入/判据不变，CPU本地与Linux33/33、实际FILEdry通过，待独立启动签核；按常设最多2次重试授权接续。R066b c kept保持，发布门仍未闭合；FTD/论文v5未生成，分支/部署/推送未执行。

**状态：R066b c 已独立/D04 kept；R063/b129 四臂默认关闭门执行中，发布门尚未闭合。本文是待审方案，未建分支、部署或推送。** 后续以新终态更新本页，并附新FTD与论文v5；不把本草稿当作批准。

## 候选与回滚点

发布候选：`481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9`，来源`/data2/FreeToken/wt/e2oom-protocol-restart`。基线`0aa23431`之后至OOM恢复`4c878f6`共9个提交（含4c）；4c直接父为608251f，不能写成0aa→4c单个补丁。后续直接父链为`4c878f6 → d577e32 → 481d3a7`，分别补齐公开API准入/恢复协议及相关路由；完整关系见[候选父链与验收](OOM_RELEASE_CANDIDATE_CHAIN_20261009.md)。不将工装effb996或E3的8f6a912自动合入。

回滚点：保留的`/data2/FreeToken/src/FreeToken`，HEAD `184c965964b5f79deaecf1b1e3e0eda3187c829d`。该版含K1已知缺陷，回滚只使用历史普通8192分块、49152窗口，不套用新层优先配置。两棵树均保留，不原地覆盖。

10:36只读核验：候选commit对象可从源repo读取，rollback tracked-clean；`refs/heads/release/e2`和`/data2/FreeToken/wt/release-e2`均不存在；8095/8096均无监听，未作HTTP探测。执行时需再核验这些会变化的事实。

## 待单独批准的分支创建

[用户指令](../plan/R066B_CANARY_V2_AUTHORIZATION_20261009.md)明确“建分支、部署、推送仍分别审批”。以下命令仅供审查，未执行：

```bash
RELEASE_COMMIT=481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9
git -C /data2/FreeToken/src/FreeToken branch release/e2 "$RELEASE_COMMIT"
git -C /data2/FreeToken/src/FreeToken worktree add /data2/FreeToken/wt/release-e2 release/e2
```

创建前复验ref与目录不存在，不覆盖已有目标。独立工作树保留旧rollback树；本项批准不包含部署或推送。

## 待单独批准的启动命令

目标主机172.16.108.9；API8095、TCPStore8096；同一FT venv与共享权重overlay。没有已确认的systemd unit，本方案是前台启动。配置沿用R056已测发布配置：GPU0、taskset1,3-47、offload NVFP4 Triton、PLE pinned、窗口98304、比例0.88、running/graph2、层优先4096；无D0、FT_DEV/FT_D16/FT_T17/route捕获变量。私有R066b验收的running/graph4并非此生产配置。

以下显式空环境保留既有d07 clean_environment所用PATH及关键运行键，避免继承开发捕获变量；命令没有启动过：

```bash
env -i \
  PATH=/data2/FreeToken/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games:/snap/bin \
  PYTHONPATH=/data2/FreeToken/wt/release-e2/python VIRTUAL_ENV=/data2/FreeToken/venv \
  CUDA_VISIBLE_DEVICES=0 MASTER_PORT=8096 PYTHONUNBUFFERED=1 \
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

执行前复验候选、发布门封存hash/只读位、GPU锁、端口与服务owner；保存实际argv、commit、导入路径、日志、PID/出生和所属组。OOM恢复默认开启，故障注入关闭。健康检查与真实业务正确性分别记录；仅用已绑定本服务的PID/出生/组停止，保留失败证据。回滚的完整历史参数和执行边界见[部署/回滚手册](DEPLOY_ROLLBACK_E2_DRAFT_20261006.md)。

## 已知限制与数据口径

- 并发时temperature0正文可能与单独冷请求不同；前缀缓存命中时也可能与不命中时不同。D16发布口径为单请求冷跑跨进程一致、T17同结构热/冷逐位范围、指定并发canary无串扰、finish/usage有效，不能宣称普遍全文不变。
- **现算尾段 ≤ 64 token 的热路径（含 1 token）未与同结构冷参照逐位比对；T17 覆盖尾段 ≥ 65。线性注意力按 64 分块，尾段 ≤ 64 时不写续算检查点，是另一条代码分支。**。D不补跑；[D20只读结论](D20_D14_8256_GUARD_READONLY_20261009.md)确认同end查找静态问题，未修引擎。
- 98304/.88完整首请求87100token已在R056完成；32K解码中位34.33tok/s，对旧73728配置38.30下降约10.4%，属跨窗口披露，不是同配置性能比较。R056余量是采样值，不能当连续最低值；超过98304仍拒绝。
- T20原R040机器failed_harness和R040j/R065/R066a原not_met保持；新用户口径只沿用明示已测范围，不重写旧判。warm2零hit不证明缓存坏，正确性门移除，稳定命中/收益转E3。
- Strata R001 canonical pending_review，已启用MTP，71.9tok/s不能作无投机基线；R002的22服务/345调用尚未批准。E3优化分支与D12开启验证不随本次发布激活。

推送仍单独等待批准；本次未执行fetch/push，也未创建release/e2。
