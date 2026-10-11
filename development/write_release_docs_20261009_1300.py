"""Update current release documents only; preserve prior snapshots, start nothing."""
import hashlib
import json
from pathlib import Path

FT = Path(__file__).resolve().parents[1]
DEV = FT / 'development'
OPS = '/data2/FreeToken/runs/dev_release/release_e2_ops_v3_20261009/source/development/release_e2_ops_v1'

PROPOSAL = r'''# E2 发布方案（13:00 指令落实，部署与推送未批准）

候选发布门已闭合；`release/e2` 与 `/data2/FreeToken/wt/release-e2` 已于 2026-10-09 13:03:20 创建，指向 `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9`。创建前复验 ref/目录不存在，创建后 tracked-clean，旧回滚树未变。[创建回执](RELEASE_E2_BRANCH_CREATION_20261009_v1.json)绑定这一事实。**部署、推送均未批准，未启动生产服务；生产配置的冷跑基准尚未产生。** 本方案提交用户审阅，批准后才能执行下列启动/回滚/冒烟操作。

依据：[13:00 指令](../plan/RELEASE_DIRECTIVE_20261009_1300.md)。完整起停与分时步骤见[统一操作手册](DEPLOY_ROLLBACK_E2_DRAFT_20261006.md)，[发布说明](RELEASE_NOTES_E2_DRAFT_20261006.md)只陈述已验范围。旧方案、回滚手册和说明已原字节归档至 `release_history/*_pre1300_20261009.md`，不再把历史待批状态混入当前操作段。

| 项目 | 本次准备与证据 |
| --- | --- |
| 身份 | release/e2=481d3a7；保留 rollback `/data2/FreeToken/src/FreeToken`=184c965。工装 effb996、E3 8f6a912、D20 修复均不自动合入。 |
| 托管 | `setsid -f` 启动专用 supervisor；代码强制独立 session/group，处理 TERM/INT/HUP。服务也有独立进程组，使用冻结 D07 生命周期清理。 |
| 日志与 PID | 每次新建 `/data2/FreeToken/runs/production/<审批号>/`；`serve.log`、`owner.json`、`stopped.json`；supervisor 输出 `<审批号>.supervisor.log`；活动 PID/出生/PGID/session 文件 `/data2/FreeToken/run/production.active.json`。 |
| Restart/停止 | 外层 `Restart=no`；内部已验 OOM worker 恢复保持开启。TERM 120 秒，KILL 30 秒，操作命令总等候 170 秒；失败保留锁和证据，不启动回滚。 |
| 环境 | `os.environ.copy()` 后剔除所有 `FT_*`、`PYTHONPATH`、`CUDA_VISIBLE_DEVICES`，重设 FT venv、对应源码路径、GPU0、MASTER_PORT8096、unbuffered/禁写pyc；保留必要 CUDA/动态库及宿主环境。发布和回滚使用同一函数，不使用空环境。 |
| 发布配置 | 内网 `172.16.108.9:8095`，TCPStore8096；taskset1,3-47，offload NVFP4 Triton，PLE pinned，98304/.88，running/graph2，层优先4096，special-token checkpoint，mamba host slots0。 |
| GPU 分时 | supervisor 原子取得 `/data2/_shared/gpu.lock`，token含production owner/审批号/PID出生；E3共用锁存在即排队，禁8095/8096。生产常驻，测试须停服审批→停止→测试→恢复→冒烟，每次停服记录独立审批号。 |
| 鉴权选择 | 按二选一要求选择内网地址绑定，未添加 key 或修改 iptables；不绑定0.0.0.0。内网地址并不提供用户级鉴权。 |
| 冒烟 | 维护独占时段，官方 SDK+pytest沿用R066：health、512提示/128输出、8257提示/128输出；绑定活动记录、活PID、实际argv、日志，首轮日志无prefill；每次new/cached行数与token总量精确核对，cached缺失不填0。保存SSE、usage、正文SHA和冷日志窗口。 |
| 回滚 | 完整停止命令等待GPU计算进程/8095/8096/锁/PID记录全部释放，再启动184c965；普通8192、窗口49152，使用同样环境清理/内网绑定/托管。量化触发见手册。 |

CPU准备包已上传并在 FT venv 验证：**20 passed，1 skipped（真实冒烟未执行）**；本地同样通过。最终服务器档案为 `/data2/FreeToken/runs/dev_release/release_e2_ops_v3_20261009/`，源码清单、CPU输出与[回执](release_e2_ops_v1/evidence_v3/receipt.json)均存档。`release_control.py --plan` 在服务器生成 Linux 最终argv，再与封存R056 `production/SERVE_CMD.txt`做diff；[发布diff](release_e2_ops_v1/evidence_v3/release_vs_R056.diff)、[回滚diff](release_e2_ops_v1/evidence_v3/rollback_vs_R056.diff)本地同字节保留。R056原命令SHA为 `e1708f7242325ca252fdd0d40219351473a2b49712f7ff1a63b3d78af7b54acb`，已核对原MANIFEST。

发布相对R056保持窗口/比例/running/graph/分块/量化/调度参数；差异是源码从0aa树移至481发布树、移除R056观测wrapper及其变量、使用ft生产入口、内网host和8095端口、加入专用托管。归档v1是早期CPU草案（Windows本地生成argv带反斜杠，废弃）；v2为修正Linux argv的中间包；仅v3是当前操作包。历史包保留，不覆盖。

## 冒烟与失败即回滚

首次部署先限制业务方访问，待启动/健康维护状态为serving后执行两条冷请求。生产running/graph2的 `cold_baseline.json` 是首次现场基准，现阶段没有填写SHA或usage实测值；不得以R066历史graph4 SHA替代。恢复同一发布配置时逐项比较首次冷SHA和usage；回滚模式独立基准，不跨版本比较正文。任何HTTP/SDK/finish/usage/非法字符/缓存证据/身份或配置检查失败，都停止放量，按已批准手册回滚；原失败文件保留。它验证明确的两条接口契约，不代替业务任务合规。

## 已知限制与默认值

- T17逐位证据覆盖已测现算尾段≥65；≤64（含1）与同结构冷参照的GPU正确性仍待证。D20 CPU调度修复在独立开发树，未合入481，不改变发布范围。
- 并发或前缀命中时，temperature0正文不保证与独立冷请求相同。冷可复现、同结构热冷、并发无串号分别记录；R066c分类c的五条回复均有字面文法异常，不能声称普遍任务合规。
- 双会话已测最低剩余约378MiB（R058场景采样377.7MiB），由OOM恢复兜底；该数不是任意业务下的连续最低保证。R056 87K单请求约0.357GiB样本另列，不能混用。
- OOM故障注入只在chat路由做过一次（R061f），其余公开路由测试不能当成分别做过故障注入。R061f绑定481，现场发布树和候选树默认均为队列上限128、ready等待900秒；R061f结果显式timeout900，实际观测排队1。此为默认值一致，不是128并发压测。[默认值回读](release_e2_ops_v1/evidence_v3/oom_defaults_readback.json)。
- 98304窗口上限仍拒绝越界；R056完整87100提示已测。32K解码中位34.33tok/s，对历史73728窗口38.30下降约10.4%，只作跨窗口披露。
- 旧not_met/failed_harness及原FTD03/04/erratum保留。FTD-20261009-1和论文v5/v5.1交付不构成部署批准。

## D20 与 GPU 队列

D20以481为基线，独立开发树 `/data2/FreeToken/wt/d20_short_tail_v1`，提交 `ebe191794ffe193e167766ae0b0e1fe0e5f5b613` + CPU回归 `d50be0f8f84ab1105f788be8f1354773ad539b63`。donor按调度段索引绑定，消除同end将1-token尾段误识别为donor；FT venv CPU **24 passed**，未GPU。[八格矩阵](d20_short_tail_v1/D20_SHORT_TAIL_CPU_MATRIX.md)：前缀8192/8256 × 尾段1/30/63/64；每格warm两调用+两个独立同结构cold各一调用，提案 **24服务生命周期/32调用**，GPU另报，当前未批准。

R045获13:00批准，在部署前空闲窗口尝试冻结v18入口；CPU88通过、FILEdry零服务零调用、source/FD独立复核通过。实际入口在reserve之前要求R040g `measured`，现场canonical为保留的 `failed_harness`，因此前置阻断，**实际0服务/0调用、无批次/锁/GPU**。已按任意not_met即停报停止GPU，不改旧判、不改判据、不重试。该阻断属于R045的前置依赖，未重新打开481的已闭合发布门。Strata **22服务/345调用仍未批准**。

发布门绑定见[E2闭合记录](E2_RELEASE_GATE_CLOSURE_20261009_v2.json)、[候选链](OOM_RELEASE_CANDIDATE_CHAIN_20261009.md)、[R066c报告](../plan/01_测试与调研/results/T20-E2-R066c_20261009.md)。
'''

MANUAL = r'''# E2 部署与回滚手册（13:00 指令后的当前方案）

**分支已创建；生产部署和推送未批准、未执行。** 本文件中的启动、停止和真实冒烟命令都是审批后的操作步骤。代码已完成CPU准备与服务器归档，尚无生产PID或首次冷跑SHA。候选481、回滚184c965、最终argv/R056差异和证据见[发布提案](RELEASE_PROPOSAL_E2_20261009.md)。

## 托管与环境

最终操作源码在 `@OPS@`，源码及依赖清单为其上三级档案中的 `evidence/source_manifest.json`。运行前核对该清单。`release_control.py --plan --mode release|rollback`只打印argv，不启动任何东西。

采用 `setsid -f` 创建独立supervisor，无外层自动重启（Restart=no）。supervisor PID/出生/PGID/session及服务组写入 `/data2/FreeToken/run/production.active.json`，每次目录的 `owner.json`保留相同记录；服务日志 `serve.log`，外层日志 `<审批号>.supervisor.log`。处理TERM/INT/HUP并按owned group清理；TERM120秒、KILL30秒、控制命令总等待170秒。进程身份变更、锁替换、GPU/端口未释放时fail closed，保留诊断，不使用killall或抢删锁。

发布/回滚均调用 `release_config.environment()`：复制宿主环境，删除所有FT_*及旧PYTHONPATH/CUDA_VISIBLE_DEVICES，再设对应树python目录、FT venv、GPU0、MASTER_PORT8096、PATH、PYTHONUNBUFFERED、PYTHONDONTWRITEBYTECODE。保留LD_LIBRARY_PATH/CUDA等必要宿主键。启动前验证对应HEAD精确匹配，拒绝tracked变动及未追踪/ignored文件；如被无关文件阻断，先审查归属，不能强行绕过检查。

## 发布启动（批准后）

每次使用实际审批号替换占位符，生产目录与日志必须从未存在。先确认发布源码/门hash、内网IP、GPU闲、共享锁不存在、8095/8096无监听，并限制业务方访问直到冒烟完成。

```bash
OPS=@OPS@
DEPLOY_APPROVAL=REPLACE_WITH_ACTUAL_DEPLOYMENT_APPROVAL_ID
[[ "$DEPLOY_APPROVAL" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$ ]] || exit 2
mkdir -p /data2/FreeToken/runs/production /data2/FreeToken/run
( set -C
  setsid -f /data2/FreeToken/venv/bin/python "$OPS/release_control.py" \
    --start --mode release --approval-id "$DEPLOY_APPROVAL" \
    --run-dir "/data2/FreeToken/runs/production/$DEPLOY_APPROVAL" \
    </dev/null >"/data2/FreeToken/runs/production/$DEPLOY_APPROVAL.supervisor.log" 2>&1
)
```

`setsid`返回不等于服务就绪。回读active/owner的实际PID出生和argv；用 `/health`确认status=ok且maintenance=serving。冷启动允许最多1800秒，每10秒检查一次；超时停止放量并触发回滚。首个模型请求必须来自下面的冒烟测试，维护独占窗口内禁止其他业务请求；无法证明独占则不签冷基准。首次冷基准验证的是当前running/graph2配置。

```bash
export RELEASE_SMOKE_BASE=http://172.16.108.9:8095
export RELEASE_SMOKE_MODE=release
export RELEASE_SMOKE_OWNER=/data2/FreeToken/run/production.active.json
export RELEASE_SMOKE_SERVE_LOG="/data2/FreeToken/runs/production/$DEPLOY_APPROVAL/serve.log"
export RELEASE_SMOKE_RUN_DIR="/data2/FreeToken/runs/production/$DEPLOY_APPROVAL/smoke_first"
export RELEASE_SMOKE_EXCLUSIVE_APPROVAL="$DEPLOY_APPROVAL"
unset RELEASE_SMOKE_BASELINE
CUDA_VISIBLE_DEVICES= PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python \
  -m pytest -q "$OPS/test_smoke_live.py"
```

测试只调用现有服务，不启动模型；使用R066官方SDK输入512/8257、各128输出、temperature0，SDK禁重试，单请求timeout900秒。绑定active文件、活服务PID出生、准确host/argv/commit/log；要求此前无prefill、每条日志new/cached总量和分块行数匹配。API cached字段缺失按缺失记录，以backend日志证明冷；没有日志证据或有额外prefill则失败。保存health、原SSE/usage、正文SHA、日志字节窗口和 `cold_baseline.json`。这两条互相无公共token前缀；维护独占是必要条件，现有backend日志没有逐request ID，不声称其本身提供直接UID绑定。

首次cold SHA是现场记录，没有借用graph4旧值。后续恢复发布服务设 `RELEASE_SMOKE_BASELINE=<首次smoke_first/cold_baseline.json>`逐项比较相同模式/窗口/分块下SHA和usage。业务放量仅在完整冒烟通过后。

## 完整停止与回滚（批准后）

以下停服必须用真实停服/回滚审批号，不能拿任意自填字符串当批准。stop命令先绑定supervisor出生，再写 `stop_<审批号>.json`，触发owned清理，等待GPU计算进程、8095/8096、共享锁、active记录全部释放。

```bash
STOP_APPROVAL=REPLACE_WITH_ACTUAL_DOWNTIME_APPROVAL_ID
[[ "$STOP_APPROVAL" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$ ]] || exit 2
/data2/FreeToken/venv/bin/python "$OPS/release_control.py" \
  --stop --approval-id "$STOP_APPROVAL"
ss -H -ltn '( sport = :8095 or sport = :8096 )'
nvidia-smi --query-compute-apps=pid --format=csv,noheader,nounits
test ! -e /data2/_shared/gpu.lock
test ! -e /data2/FreeToken/run/production.active.json
```

stop退出必须为0，ss与compute输出为空，lock和active都不存在；GPU显存回落到启动idle门槛（各卡<1000MiB），才可进入回滚。任一失败保留锁与证据并报告，不能继续启动旧服务。新的审批号启动旧版；不切换、不覆盖新树：

```bash
ROLLBACK_APPROVAL=REPLACE_WITH_ACTUAL_ROLLBACK_APPROVAL_ID
[[ "$ROLLBACK_APPROVAL" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$ ]] || exit 2
( set -C
  setsid -f /data2/FreeToken/venv/bin/python "$OPS/release_control.py" \
    --start --mode rollback --approval-id "$ROLLBACK_APPROVAL" \
    --run-dir "/data2/FreeToken/runs/production/$ROLLBACK_APPROVAL" \
    </dev/null >"/data2/FreeToken/runs/production/$ROLLBACK_APPROVAL.supervisor.log" 2>&1
)
export RELEASE_SMOKE_MODE=rollback
export RELEASE_SMOKE_SERVE_LOG="/data2/FreeToken/runs/production/$ROLLBACK_APPROVAL/serve.log"
export RELEASE_SMOKE_RUN_DIR="/data2/FreeToken/runs/production/$ROLLBACK_APPROVAL/smoke_first"
export RELEASE_SMOKE_EXCLUSIVE_APPROVAL="$ROLLBACK_APPROVAL"
unset RELEASE_SMOKE_BASELINE
CUDA_VISIBLE_DEVICES= PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python \
  -m pytest -q "$OPS/test_smoke_live.py"
```

回滚同样先等health=serving并独占冒烟；`RELEASE_SMOKE_BASE`和`RELEASE_SMOKE_OWNER`沿用上节。回滚的SHA只形成其自己的基准，不与发布SHA跨版本比较。失败保留日志并停止，不自行切第三个候选。

**回滚窗口选49152。** 对应旧184c965的历史普通8192配置，`/data2/_shared/runs/ft_rounds/_e0/paper_headroom_20261003/serve_final_8192.log`的解析参数及[8192复核](../RESULTS_FT_PAPER_HEADROOM_20261003.md)、[历史32K记录](../RESULTS_FT_COLD32K_20261002.md)支持49152。32768只见于历史启动脚本，不是该已核实回滚配置；不沿用候选98304，不开层优先。旧版含K1，回滚降低的是新版本风险，不声称旧版无缺陷。旧E0归档不是当前D04规范下独立封存轮次。

| 量化触发 | 处理 |
| --- | --- |
| 初启1800秒仍未serving，或任一冒烟请求900秒未完成 | 不放量，保存日志并回滚。 |
| 任一冒烟HTTP/SDK/finish/usage/非法字符/缓存证据/身份配置失败；同配置恢复SHA或usage不符 | 一次即触发；保存失败产物，回滚。 |
| OOM后900秒未恢复serving，或重启进入terminal/dead状态一次 | 回滚。 |
| 10分钟内≥2次OOM/worker restart | 回滚；单次成功恢复保留记录，不单凭低显存样本回滚。 |
| serving期间连续3次health失败（间隔10秒），或5分钟内≥3次非预期5xx/worker错误 | 停止新流量，回滚。显式输入超窗/客户端取消不计服务故障。 |
| 已确认串号、非法控制字符或错误usage一次 | 停止新流量，保留原输出并回滚。一般业务答案质量另按业务验收，不声称脚本可自动判真。 |

这些是待批准的运维阈值，不是本次CPU检查测得的故障率。部署批准应包含上述失败分支的停止/回滚授权；当前没有这项授权，未执行任何命令。

## 生产常驻与按需测试

启动时production owner登记共享GPU锁，E3入口锁存在即排队、保留端口8095/8096全部禁用（R045 v18实测FILEdry端口另用）。每次测试流程为：记录本次停服审批号 → 上述stop并验证全部释放 → 独立测试批次取得同一锁 → 测试终态与owned清理 → 新恢复审批号用release模式启动 → 与首次graph2冷基准比较的独占冒烟 → 放量。审批号同时出现在停服JSON、owner、run目录及协调记录，不能靠后台kill绕过审批。生产部署批准到达时，E3在当前批次边界让出，不抢杀进行中服务。

## CPU验证与未执行项

本地与服务器最终包均20 passed、真实冒烟1 skipped；涵盖环境不污染、两个argv、PID出生拒绝、资源未释放拒绝、TERM/INT/HUP模拟清理、延迟回收等待、发布/回滚冒烟owner/地址/审批绑定。没有启动模型服务或做真实OOM/停服恢复演练；这部分只能在批准后留现场证据。服务器最终argv和R056 diff已经生成，不以CPU通过代替生产验收。
'''.replace('@OPS@', OPS)

NOTES = r'''# E2 发布说明（候选完成，生产激活未批准）

`release/e2`=481d3a7及独立工作树已按13:00批准创建；发布门闭合，部署/推送未批准且未执行。[发布方案](RELEASE_PROPOSAL_E2_20261009.md)、[统一部署回滚手册](DEPLOY_ROLLBACK_E2_DRAFT_20261006.md)和[CPU操作包](release_e2_ops_v1/evidence_v3/receipt.json)已补齐托管、环境、argv diff、内网绑定、GPU分时、量化回滚及R066冒烟方案；CPU20通过，真实冒烟尚未执行，生产graph2 SHA/usage待现场记录。

候选从0aa23431经4c878f6、d577e32到481d3a7，首段含9个提交，不能写成单一补丁。新候选包含OOM worker恢复和公开API恢复期间准入协议；完整父链、默认门/恢复门与路由范围见[候选链](OOM_RELEASE_CANDIDATE_CHAIN_20261009.md)。发布配置98304/.88、running/graph2、层优先4096、pinned PLE、NVFP4 Triton、GPU0；回滚保留184c965普通8192、49152。

| 已有证据 | 限定结论 |
| --- | --- |
| T17 | 逐位等价覆盖已测尾段≥65；≤64含1走不同分支，GPU正确性待证。 |
| D16/R066系列 | 单请求冷可复现、同结构热/冷与指定并发分别记录；不能宣称temperature0任意并发全文不变。R066c五条字面文法异常按用户口径分类c，不证明普遍任务合规。 |
| R056 | 98304配置完整87100提示已测，32K解码中位34.33tok/s，对旧73728的38.30约下降10.4%；跨窗口代价，非同配置回归结论。87K请求后约0.357GiB为采样。 |
| R058 | 双会话已测最低采样377.7MiB，约378MiB；依赖OOM恢复兜底，不保证所有业务余量。 |
| R061f | chat路由一次故障注入；已验受影响请求错误、排队恢复与新worker冷参照一致。其它路由没有分别故障注入。队列默认128、ready等待900秒与481一致；只实际观测1个排队请求。 |
| D20 | 独立开发树已修同end donor查找，CPU24通过；未合入481、未GPU。八格同结构矩阵提案24服务生命周期/32调用，仍待GPU批准。 |
| R045 | 13:00批准后冻结v18实际入口在reserve前因R040g canonical failed_harness（要求measured）阻断；0服务/0调用，无批次/锁/GPU，不改旧判或自主重试。 |

FTD-20261009-1已只读发布，论文v5/v5.1已完成各自审查；旧FTD、failed/not_met、v5原件不变。R063a仅E3 D12默认关闭证据，E3优化和D20不随本次发布激活。Strata22服务/345调用仍未批准。

停服/恢复/冒烟必须有本次审批号并占用同一共享锁；生产常驻，测试按需申请停服。正式激活后才会生成生产PID、冷SHA/usage及观察记录。本说明不把分支、CPU通过或健康HTTP当成业务验收。
'''


def main():
    archive = DEV / 'release_history'
    archive.mkdir(exist_ok=True)
    docs = {'RELEASE_PROPOSAL_E2_20261009.md': PROPOSAL,
            'DEPLOY_ROLLBACK_E2_DRAFT_20261006.md': MANUAL,
            'RELEASE_NOTES_E2_DRAFT_20261006.md': NOTES}
    for name, content in docs.items():
        old = DEV / name
        preserved = archive / (old.stem + '_pre1300_20261009.md')
        if not preserved.exists():
            with preserved.open('xb') as handle:
                handle.write(old.read_bytes())
        old.write_text(content, encoding='utf-8')
    draft = FT / 'plan/data_releases/E2_RELEASE_CANDIDATE_DRAFT_20261009.json'
    value = json.loads(draft.read_text(encoding='utf-8'))
    value['activation'].update(release_branch_created=True, branch_approval=True,
        deployment_approval=False, push_approval=False, production_deployed=False, pushed_to_remote=False)
    value['branch_proposal'].update(branch_created_at='2026-10-09 13:03:20 CST',
        creation_receipt='development/RELEASE_E2_BRANCH_CREATION_20261009_v1.json')
    value['production_configuration'].update(production_port=8095, tcpstore_port=8096,
        host='172.16.108.9', service_manager='setsid supervisor; Restart=no',
        activation_bindings_status='CPU prepared; deployment/push not approved; live smoke not run')
    value['proposed_runtime_entry'].update(mode='setsid_supervisor_CPU_prepared_not_activated',
        branch_exists=True, worktree_exists=True, activation=False,
        CPU_archive='/data2/FreeToken/runs/dev_release/release_e2_ops_v3_20261009',
        cold_baseline_SHA=None, cold_baseline_usage=None)
    value['downstream']['all_GPU'] = 'R045 v18 pre-reservation dependency blocked: R040g canonical failed_harness, expected measured; actual zero services/calls; GPU stopped. Strata22/345 unapproved.'
    value['downstream']['D20'] = 'isolated CPU fix+24 tests; proposed 24 service lifecycles/32 calls unapproved; not merged into481'
    value['remaining'] = ['user review of CPU-prepared operational proposal', 'deployment approval', 'push approval',
                          'production graph2 cold smoke and live observation after approval']
    value['release_directive'] = 'plan/RELEASE_DIRECTIVE_20261009_1300.md'
    draft.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    readme = FT / 'README.md'
    text = readme.read_text(encoding='utf-8')
    text = text.replace('建分支、部署、推送分别待批且未执行。',
        'release/e2与工作树已按13:00批准创建；部署、推送未批准且未执行。')
    readme.write_text(text, encoding='utf-8')
    update = '''\n## 13:00 发布指令落实（当前状态）\n\nrelease/e2=481已创建，生产部署与推送未批准。setsid托管、统一环境、PID/日志、共享锁、内网绑定、量化回滚及R066 graph2冷冒烟已补齐；本地/服务器CPU20通过，真实冒烟未执行。[当前发布方案](development/RELEASE_PROPOSAL_E2_20261009.md)。D20独立CPU修复24通过，八格GPU矩阵提案24服务生命周期/32调用未批准。R045已尝试冻结v18入口，因R040g正式终态failed_harness而要求measured，在reserve前停止，实际0服务/0调用、无GPU；保持旧判、不重试。Strata22/345未批准。\n\n'''
    readme.write_text(readme.read_text(encoding='utf-8').replace(
        '## 当前交付（2026-10-09，最终复核完成）', update + '## 当前交付（2026-10-09，最终复核完成）', 1), encoding='utf-8')
    summary = FT / 'plan/MORNING_SUMMARY_20261009.md'
    summary.write_text(('''# 当前进展摘要（2026-10-09，13:00发布指令落实）\n\n| 类别 | 当前状态 |\n| --- | --- |\n| 分支 | release/e2和独立工作树已创建，HEAD481，回滚树未变。 |\n| 发布准备 | setsid/环境/argv-R056 diff/内网绑定/GPU锁/回滚/SDK冒烟已补齐，CPU20通过；部署、推送未批准，真实冒烟未运行。 |\n| D20 | 同end donor CPU修复24通过；八格同结构GPU矩阵24服务生命周期/32调用仅提案。 |\n| R045 | 获批后实际入口在reserve前被R040g正式failed_harness终态阻断（要求measured）；0服务/0调用，无批次/锁/GPU，不改原判。 |\n| 交付与范围 | 发布门保持闭合，FTD及v5/v5.1交付保留；Strata22/345未批准。 |\n\n[当前发布方案](../development/RELEASE_PROPOSAL_E2_20261009.md)与[操作手册](../development/DEPLOY_ROLLBACK_E2_DRAFT_20261006.md)提交审阅。R045前置阻断按任意not_met即停报处理，GPU不续跑。\n\n以下为历史快照，以本表为当前状态。\n\n''') + summary.read_text(encoding='utf-8'), encoding='utf-8')
    coord = FT / 'plan/COORDINATION_LOG.md'
    with coord.open('a', encoding='utf-8') as handle:
        handle.write('\n\n## 2026-10-09 13:00 指令落实\n\n分支已创建481，deploy/push未批准；CPU操作包v3本地/服务器20通过、live smoke跳过；最终Linux argv/R056 diff与128/900默认值已服务器存档。D20独立24 CPU通过、24服务/32调用GPU矩阵未批准。R045冻结v18在reserve前被R040g canonical failed_harness（期待measured）阻断，0服务/0调用，无批次/锁/GPU；按not_met停报，旧判保留。Strata22/345未批准。当前方案/操作手册/发布说明已重写，原文原字节归档release_history。\n')
    print(json.dumps({'documents': list(docs), 'CPU_only': True,
        'deployment': False, 'push': False, 'model_service_started': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
