# D16 真实服务接线进展

本次新增入口 `d16_exact_service_startup.py` 保留共用 T17 精确输入接口与四个观察钩子，并在 spawn 子进程中安装原生 scheduler capture。`t17_d14_gpu.Run.service` 可显式选择双槽或四槽，默认双槽不变；服务命令和环境原件包含 D16 配置。`d16_service_workloads.collect` 支持独立 batch/alone 臂及一次测量，为独立进程对照提供入口。

## CPU 证据

`python development/d16_exact_startup_cpu_stage.py` 创建新的只读冻结包，不改正在运行的批次。最新阶段：

- `/data2/FreeToken/runs/dev_D16/exact_startup_cpu_6d85376470d2/cpu_validation.json`
- SHA256 `c98024727896ad446186262041e20735f28e4a36f18856e0ec85f5dfbda6d9db`
- 专属 `e2base1` 树 `b9c9248f910e8e2f0560087683e761d436fe8522`；9 PASS、0 skip。
- 实际 CPU spawn 子进程完成精确 ID 消息编解码与 tokenizer，UID=41、ID=[1469,17,198,248068]，四个保留观察钩子及 D16 worker 均已安装。
- 对原生 Scheduler/Engine 实例调用实际 capture installer，读取正确的逐 UID/generation 输入清单与显式容量预算；仅传输回调和 sampler 是 CPU sink，不加载模型或建立 ZMQ。
- 两个新增 HTTP 回归分别验证 batch/alone 单臂在新建服务器上只提交一组请求，并保留响应原件。HTTP 并发不构成物理批槽证据。

泳道 R 已独立复核最新阶段：16/16 文件重算一致、只读且无符号链接、本地源码和测试字节匹配，判 CPU 启动/安装范围 PASS。它未验证完整 Scheduler 构造、UserMsg 接入、采样/交付/最终封存或模型行为。

早期阶段 `1f184f6a32f0`（输入落盘目录缺失）和 `f5f28d747f33`（CPU fixture 未绑定原生初始化中的发送回调）失败工件保留。`f52fc65d31e2` 仅证实 worker 替换及精确输入，未验证 capture 配置，不作为安装器通过证据。

## 原始批槽读取器

泳道 A 子 Agent 提交 `09f97ce9b514a0b55dfab5c0bc3e378dadc577df` 已同步专属 `e2d16-readers`。冻结阶段 `/data2/FreeToken/runs/dev_D16/batch_observer_09f97ce9b514_cpu_36118a1b2a75`：101 PASS、0 skip，报告 SHA256 `2cdb1173308f1e71793598242929fb6be2d21ea938b45ab998c7d88b0edeb578`。原始证据读取器绑定实际批槽事件、UID、输入、采样张量、输出和进程身份，并拒绝路径越界及祖先符号链接。该提交尚未合入 D17。

泳道 R 已独立复核该阶段：32/32 文件重算一致，26 个冻结来源逐项匹配 Git blob，专属树干净、实际导入/CUDA 关闭及 101 PASS/0 skip 均确认。批内与单独运行产生差异时的首分叉、top-2 logit 差和合法重排包络仍需补齐；该问题正在后续版本修正，不能据当前测试数量认定 D16 完整交付。

## 待完成

后续进展见 [R035 工装事故和恢复记录](R035_CPU_FIXTURE_INCIDENT_20261005.md)：最新网络隔离、独立采集接线及失败清理 CPU 包为 26 PASS/0 skip，生产 source review 尚未交付，不授 D16 GPU 启动。新版批槽读取器 `37d46a078dd458bbe663d8d12dc36bdee6fef600` 已将稳定 batch-vs-alone 的差异输出为首分叉/top-2 原始诊断，102 PASS/0 skip；同形状重复漂移仍拒绝。它还没有合入 D17。

完成共用生命周期内的独立模型进程编排与原始证据读取器接线；补齐批形状变化的合法重排包络；真实 GPU 双槽/四槽重复及单独对照；缓存、停靠和时间交错场景。当前 CPU 证据不授予模型、T17、R041、T20 接受或 D17 标签。

2026-10-06 07:10:38：现有 d16_exact_service_startup.py 增加显式 FT_D16_PARK_RESTORE=1 停靠钩子。仅在原生开发暂停已经排空 last_data、准备 accepted 回复的安全点执行；默认关闭，不改产品工作树或已有冻结包。使用已有空闲 host bank（不足即失败，不驱逐前缀快照），按原生 to_host/clear_slots/from_host 对活跃请求做四类状态搬运；在 engine stream 上同步，保留 before/host/cleared/restored 原始张量，检查 bitwise，并只释放测试分配的 host slots。请求 table/linear slot/host tracks 不变；这仍不是释放设备槽再调度或最终续写接受证明。

源码 SHA256 424f8e76d8d8e0211d11069979c09d4db909533d5cbc9746a49ddf0d8fe61e5c；既有测试文件 SHA256 c94ef15a8bd59f0584b659dfc8064cf2a208b6fad5afde1570cb60ef708c5492。服务器 FT venv 通过标准输入运行这两份实际源码，沿用既有 CPU socket guard、CUDA隐藏：六项 CPU 检查 PASS（默认关闭、暂停开关前置、仅 accepted 前执行、失败不回复成功、四状态成功搬运、PLE ngram 损坏检出）。未启动服务，未连接端口，未新建冻结包/fixture 工具。真实 host bank 配置、GPU 搬运和停靠对不恢复的续写 token/全文逐位对照仍待接线并在完整 T20 实际执行。
2026-10-06 07:11:46：实际共用 t17_d14_gpu.Run.service 新增可选 mamba_host_slots，默认0；命令与解析参数严格绑定同一请求值，拒绝bool/负值。T20停靠臂可用非零主存bank，同时控制臂须使用相同配置。现有测试检查双/四请求容量×host bank0/5四组合的实际argv、归档配置与回调。Windows socket guard/CUDA隐藏检查10 PASS、2 SKIP（无torch；两个四状态检查已在服务器通过）。源码 SHA256 8dc27803897834f1bf2c4d1df06265b3407c508622a0d1efe47687f05bc2e659；测试 SHA256 1035f603a44ccc62d3ff044219e340be4e8f12dcb90647154dbf9a55affbee05。R038已测试冻结源1dd61d保持原字节，本地T20改动不混入该轮。尚未接实际停靠请求触发与不恢复控制臂，不能作为完整T20启动交付。
2026-10-06 07:15:31：现有 d16_native_process_collection.py 接入实际 parking query 和四独立进程编排：同容量4、host bank5、相同pause开关与1秒间隔，两次不恢复控制、两次恢复臂。触发前读取真实 sampler 原子manifest及SHA绑定的receipt，确认UID0至少第8个采样且尚未结束；暂停accepted回执必须绑定原生roundtrip request_id/UID。轮末检查实际scheduler进程birth/group、native delivery complete和128个实际交付token；四臂全文/token不同即失败，同配置重复一致才输出pending独立复核。第一臂参数比对范围按停靠组隔离并在退出时恢复外层，防止此前host bank0参数污染本组。

源码SHA256 231f00ef77fe31d65ffe557b1a142df01316a8457086fc9090716770f680eaea；测试SHA256 77a227ea8781358c5b08ee98af195954f2b40db5644f13f0b769020f3ce55cc8。既有CPU隔离测试24 PASS/7 SKIP（Windows Linux进程身份与无torch跳过，此前服务器四状态检查通过）。新增5项检查覆盖两种真实触发流程、过早结束拒绝、四臂配置/独立身份/参数恢复、输出差异拒绝。这里只完成已有工具的接线，尚无真实GPU停靠结论；cache/interleave与完整T20外层仍待完成。未新增future读取器/冻结包，未改变R038已封存源。
2026-10-06 07:20:56：既有D16启动入口增加 FT_D16_CACHE_INIT=cold/warm（默认无操作）。两臂均先原生cache.reset，预热臂在首请求之前对每个非CPU、非unpinned层通过原生ensure_experts/copy_missing预置expert0；无任何预热请求，不触发KV/前缀命中。要求实际id_of_slot驻留计数与预置层数一致，存initial_residency.pt及初始化记录；重置测量统计，退出前保留原生prefill hit/total及decode miss计数。包装原生engine.forward_batch返回不变，在第一decode之前与第127次decode之后保留四类状态.pt及精确dtype/shape/bytes SHA，后续冷/热对照须核对原件。

源码SHA256 3aa4704db314472c1cb1a9c41dbd7f0cc1f9eabb8f3309ee0acda77471643783，测试SHA256 e730931b9d695acb266cc6df1c1cb7ffe0b55d86dec0de567a8749f72b0db071。本地guard检查25 PASS/9 SKIP；服务器FT venv guard+CUDA隐藏直接执行实际源码及既有CPU测试，两种初始化/四状态原件捕获检查PASS（GPU native缓存使用CPU mock；不能代替GPU数值验证）。上一版本服务器9项parking/cache检查也通过。未新增冻结包/读取器，未改R038冻结源。cache四进程编排、原始数值复核、interleave及完整T20外层仍待完成。
2026-10-06 07:24:01：现有 collect_cache_processes 复用停靠组四进程编排，两次cold、两次warm，同容量4/host bank0；每个进程仅一条全冷exact-ID目标请求。实际退出后要求native delivery complete、独立scheduler birth、128个token/全文稳定，并核对cache初始化execution/驻留数/priming_requests=0、cold prefill_hit_rows=0/warm>0、四角色raw.pt存在与生产者SHA元数据逐位对照一致。结果仍为 bitwise_pending_independent_review；原始.pt的独立重算由真实轮次结束后的R复核完成，不以元数据相同替代正式接受。

源码SHA256 75e4f11a11a714a308dd96aaaaafa649f3ef11df8d1b210889da6123e04e50d8；测试SHA256 89225818cd830a006e13d0f4227d0b0e7735f9b8ae7ecfc02e119443d300a60e。既有guard CPU回归29 PASS/9 Windows平台或无torchSKIP。覆盖四cache臂的配置/进程/结果、不匹配输出、四状态变化、无实际预热命中拒绝，及停靠原路径回归。未新增读取器/冻结包/fixture工具；现有R038源不变。实际T20源还须包含已有native_workloads依赖（0aa产品工具目录目前不含该文件），并在一次实际GPU启动前复核中绑定；T20整轮不可提前宣称可启动。interleave和整轮外层继续开发。
2026-10-06 07:30:47：既有 collect_native_processes 增加 interleave=True（限两路：短输入<4096、长输入>4096）。两次batch臂先启动UID0短请求，等待SHA绑定的原生generation>=7采样记录，再提交UID1长请求；复用原四次独立solo对照、actual service/native process identity和原始evidence map。轮末必须存在prefill batch物理包含UID0/1，且UID0 extend_len=1、UID1 extend_len>1；两次混合阶段的phase、actual/padded size、input tensor shape、各请求cached/device/extend长度必须完全相同，否则拒绝进入同形状比较。没有把HTTP并发当作物理交错接受。

在既有D16启动入口扩展实际observer元数据，保留live_input_ids_sha256（会随解码增长）和input_ids_sha256（绑定原始admission registry），并捕获上述实际geometry。原observer只记录不断增长的Req.input_ids SHA，native reader却以原始prompt SHA查同批；不修会漏掉全部decode batch证据。这次仅改本地已有测试入口，产品0aa及服务器R038封存源未变。

collector SHA256 202aba9a4d362d8ca2148065a4003d04a2e475edae6df3a1f5a6d7290536f2f0；startup SHA256 9cd0c09328f16f6191ca1f101747379cbf4e632fbcfa2ff6b05faf25a5d8964a。既有CPU socket guard/CUDA隐藏34 PASS/9 SKIP：新增真实顺序触发检查、3项输入几何拒绝、原始/增长SHA及实际长度记录检查；旧parking/cache流程回归通过。真实GPU下两次交错形状稳定性与batch-vs-alone首分叉/top2包络仍须实测；现有native_workloads读取器用于已有原件。完整T20 outer及实际启动前依赖绑定仍待完成。没有新增future reader/fixture工具/冻结包。