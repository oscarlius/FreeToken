# D06 当前开发与验证记录

更新时间：2026-10-04，最新执行状态以看板 observed_at 为准。**状态：源码候选已交付待验证，尚未完成 D06 验收。**

本地树 `development/e2d06/`、分支 `exp/e2d06`；父树为含 D02 的 E2-base `23f2e2caa3395837c9474735ffc83321f3b9b5a1`。候选提交 `03692633df48456fb0baa78de7b64e5628a12ab1`；服务器独立候选树 `/data2/FreeToken/wt/e2d06` 已安装准确 Git blob，已开展独立T16默认路径门，业务部署和T05验收尚未完成。

## 已完成与当前证据

- 四个任务卡接口 two-decode/stall/pair-short/h1 保持不变。客户端的每 token 时间戳来自开发模式下真实 sampled-token ACK，拒绝重复、跳号、非整数计数和 ACK 前内容；首 token 取首次实际内容。
- HTTP 使用可关闭的真实 socket 实现总 deadline；失败取消同伴请求并有界 join。真实 localhost 心跳、慢响应头和同伴取消回归通过。API 自身也统一限制初始 enqueue 与回包等待，有界传递 cancel，保留外部取消语义。
- scheduler 先 drain 在途 GPU/cache 操作，再开始完整 idle；每个请求独立串行拥有暂停区间，取消 active 只停止其剩余区间，pending/expired 请求不得迟发暂停。idle 中普通消息延后处理。默认 ACK 仍使用原 UserReply wire，开发计数字段仅在 DevUserReply。
- 提示在标准 chat-template 下以 enable_thinking=False 渲染后编码，ctx 是精确前端 ID 长度；不同文本从模板后开始区分。目标 Qwen 的实际 TokenizeManager.tokenize CPU 校验在 4000/32000/32052 下均逐 ID 一致、精确达到长度，左右提示 SHA 不同，前缀重合均 4 token。
- H1 每条件等待 8 个实际 UID-bound decode 步，再触发事件；先测本 repetition 的真实 prefill 全部分块区间，再运行等时长 idle，最后 none。输出执行顺序和实际起止；事件内 H2D/miss 与事件后前 H 步计时分别保存，extra 取 prefill−idle，缺失不补 0。未覆盖完整 H 或解码提前结束非 0。
- 本地客户端 30 PASS。**准确提交在服务器隔离 CPU 环境：69 PASS，6.32 s**；实际 tokenizer 校验另行通过。默认 GPU门不能由这些 CPU 结果替代。
- 独立源码复核最后结论无剩余源码阻塞；原退回事项及 Python 3.10 两次失败已保留。只做了换行归一化进入 Git；准确提交的 16 文件 SHA 已与服务器核对。
- T05 卡已补 FT_DEV_PAUSE_ENDPOINT=1 及 FT_DEV_D0_TIMELINE_STEPS=20000；T16 仍不开开发开关。客户端限定本次 Qwen 标准模板路径，DSV4 无模板路径在发请求前明确拒绝。

## 可审计工件

| 工件 | 用途 / SHA256 |
|---|---|
| [d06_candidate_server.json](d06_candidate_server.json) | 准确提交、16源文件、服务器路径、69项、tokenizer证据；文件 SHA `295336d3a40639d4823b1145d792f0accffc5cd0da0388e68a03966d27ac44e5` |
| 服务器 `/data2/FreeToken/runs/dev_D06/candidate_0369263/targeted.log` | 准确提交69项及tokenizer校验；SHA `a87ecc2aa220e813fa776d2b23048846ba78c15eab72362914a1093998a12c1a` |
| [d06_candidate_commit.json](d06_candidate_commit.json) | 本地提交 / 父树 / 准确Git blob / bundle记录 |
| `development/d06_candidate_0369263.bundle` | 仅提交源码，SHA `384b350c8216c1150d879d02169b0c01417bd27ad4fbb705d65049ae1f0d86fe`；未上传权重 |
| [d06_cpu_f18fc557cb89.json](d06_cpu_f18fc557cb89.json) | 提交前69 PASS / tokenizer逐ID校验；Windows原字节快照 |
| [d06_server_cpu_e2e552b30920.json](d06_server_cpu_e2e552b30920.json) | 历史31 PASS/1 FAIL，Python3.10无Task.cancelling |
| [d06_cpu_721b2d9fce80.json](d06_cpu_721b2d9fce80.json) | 历史65 PASS/1 FAIL，Python3.10异步取消race被吞 |
| [d06_source_review.md](d06_source_review.md) | 独立源码复核范围、原阻塞闭合及验证边界 |
| [d06_client_notes.md](d06_client_notes.md) | 命令、输出字段与证据规则 |

## 下一步和保留限制

按串行 GPU 队列推进：T16 默认关闭门 → D06 G3（同提示32K工具合理性）/G4（实际idle无批次日志）→ T05 两个独立进程全套。R019/b47保留为失败轮次：完整13条父prefill被旧包装器错误按12条校验。新完整尾段包装器和启动器准确Linux45PASS、独立复核通过，R020/b48已经启动，正在串行测量四臂。R020结果还需独立原始复核和D04封存。卡状态不得改“完成”，开发自检不构成正式轮次或部署证明。

G3/G4专用工装已修复独立审查发现的两项缺口：领导进程提前退出时清理真实子进程组，以及服务完全停止后才判读最终日志。源码SHA `71bb47168915cf7bc8a70adf550cf465b8f3d942a649a26c1976233e21a585e2`，准确Linux10PASS（含真实leader退出/child存活清理）及self-test通过，日志SHA `bef875de956bde7cbbe62a6d350d406536dd95db387d0af48b76f319d90dbc33`。准确源目录 `/data2/FreeToken/runs/dev_D06/d06_selfcheck_71bb4716`；GPU G3/G4尚未启动。

默认暂停端点404、finite duration/timeout、TP>1显式unsupported已在CPU seams验证；GPU实际空闲时钟、缓存不变和默认逐位门仍需真实验证。H1 prefill跨度超过端点60秒上限、EOS过早或D02证据不足时明确失败，不补数、不放宽阈值。本地看板与OpenCode交接独立于D06，线上实时接入尚未开发。
