# 第七节测量队列 CPU 交付

生产基线保持 `E2-base.1@0aa23431`。测量父树 `E2-base.1-p1@effb996` 已同步到内网独立工作树，D08/D15 分别 rebase 为 `2600ada8faef6490b7a5fbdf6708e12c29d86536`、`988c9e183c8dca4415fd9b5d02318b26664da619`。默认调度循环字节相同，独立 R 代码路径证明位于 `/data2/FreeToken/runs/dev_D06/r055_eff_code_path_basis_r_overlap_v2/review.json`，SHA256 `23219c992c587dc35ed8f956542a908835be3fd850ba6758c8f61b0aea8ce5a7`。代码路径证明不代替 R055 GPU 门。

R046a 仅新增 G3-on、G4 和 T06 四臂。原 R046 G3-off 是外部保留证据，启动前仅核其封存复核记录和只读权限；取得自己锁后才读取这份小 cold JSON 核验 SHA。G3-on 使用相同 cold_id，比对旧 OFF 与新 ON。R049 的训练与留出画像源改到 R046a；R045 的暂停测量也改用 eff，并要求 R040a measured 和 R055 kept。R050/R051 的父树为 eff。

R050/R051 采用新版本 `t16_private_port_base_runner.py`。同轮各臂使用同一个动态私有端口，保留严格参数比较；既有冷请求与 checkpoint 税脚本仅覆盖模块 URL，请求构造保持原有逻辑。gate 不探测其他监听端口，停止时检查已登记出生、会话与整个进程组。冻结原 base runner 不修改。

Linux CPU 报告：`/data2/FreeToken/runs/dev_D06/r046a_queue_cpu_20261007_v2/report.json`，SHA256 `2481b5686e9224b55de8f1dd28472114bb7f2eafb23d62e5040f7bc3191287d0`。93 项通过，空 CUDA 可见设备，socket guard，未启动模型/GPU，包原地只读。覆盖候选/native 身份、端口 bootstrap、真实 gate 的锁先验、G3-off 不重读/不重跑，以及首次停止失败即保锁的故障注入。首次 CPU 包中的 fixture 参数错误和缺少 parser 依赖已修正到 v2，失败包只读保留。

此交付不签发启动许可。R055 工装仍需真实冷四态与 pause/cancel 链路证据的 CPU 验证及独立 R 启动复核。后续轮次到队首时只核前置清单/round SHA、只读权限与 D04 history，再复核实际执行源码；不提前读取旧原始数据。

## 10-07 R055 连续工装失败后的停止点

R055 batch74/75 均在服务启动前失败，0 个完成臂，锁已释放；按 HANDOFF §7 已停止开发/启动并请求用户裁定。旧 CPU 93 PASS 只绑定当时的队列源码，不能作为后续修改源的证明。为防共享 D18 probe 漂移，R050/R051 adapter 已改用 t16_frozen_helpers_v1 四个原始客户端，owner 源清单绑定四个 helper；多提交 card 的比较父树按 merge-base(eff,HEAD)==eff 检查，候选 SHA 和 clean 要求不变。

新 helper CPU 包 42 项通过，随后真实预检查暴露旧 adapter 误要求最后一提交的直接父节点等于 eff；失败 CPU 包已原地只读，修复后的新 CPU 包尚未执行。R050 未获启动许可，等待 R055 后补裁定及实际门通过。T09 当前 D08 候选缺少 native 完成时序观测，默认关闭的三文件草稿候选变更也已提交用户确认，BODY_READY 保持 false。

## 第八节裁定后的执行记录

HANDOFF §8 已授权 R050 先跑、R055a 和 D08 新候选，上述停止点为历史记录。R050 的新版真实路径空跑复用四臂实际文件操作，冻结源包 `/data2/FreeToken/runs/dev_T16/r050_real_path_source_v5`；Linux 49 项 CPU 回归通过，独立 R 启动回执 SHA `1077b2f51a9f795b61e05944689419257dc31b53cfaa4991cf1a508c2573aeda`。R050 已以 batch76 启动；模型门尚待完成、独立原始复算和 D04。

R046a、R045 的暂停门前置已改为 R055a kept，R040a 候选恢复为生产树 0aa，并允许记录当时已经封存的独立前批作为插队依据。本地相关现有 CPU 回归 36 项通过。新绑定还需各自的最终封存源码、服务器真实路径空跑及 R 复核，旧 93 项 CPU 证明不能代替这些步骤。

D08 新候选为 `8bf0ad396f5d3104d9b4385fc6a3962c2c81dfd8`，新增事件字段默认关闭。Linux native 构建、R051 最终候选/产物绑定、实际 T16 门和 T09 仍须依序完成；R050 计时窗口不安排编译或 CPU 重基准。

R050/batch76：04:59 独立 R 逐臂原始复算后 canonical D04 kept。round SHA f707de8963172619ad932ff25b931d29e139eaedcdc88f4eff105b36a420dc4d，MANIFEST ae2e0e0e48f15a2b869fa15b90959513a4c74574bafae01b53a0d41774a01110。生产基线仍0aa。
R055a/batch77：05:06 已通过真实空跑和独立启动复核并持锁；最终 source_v1，Linux CPU19 PASS/1旧实现用例 deselected，六冷臂+PAUSE_ON实测尚在运行。启动复核SHA b7defa440fc6d45b0a65c54a35fc7621112b6174411b9fbb37879f817f9098c4。
R046a：最终source_v3位于 /data2/FreeToken/runs/dev_R046/r046a_real_path_source_v3；MANIFEST90088f12086809b0ce82f02fa56604a50eb961e5db0ada0de93b8c59f8036072，Linux CPU60 PASS，report SHA f6026e033320dd5171dadd101118c8c13b5bbbf71d7915d4b3bb507239840e73。旧空跑仅回执序列化失败，未起服务/拿锁/分配batch，原件原地只读；v3改用 .dryrun_R046a_v3_E2-R046a，新空跑尚未执行，启动复核尚未签。
R048：本地CPU25 PASS，完整五臂mock空跑、secret白名单、真实Parsed arguments、正式目录拒绝已补；待新D08 native证据及R051 kept后做实际服务器空跑，不能据CPU宣称GPU完成。

R055a 层优先三臂（PARENT0/PARENT1/NEW）已由R复算，业务UID/inputSHA/cached0/output128/全文及四类before_decode状态逐位一致；普通三臂与PAUSE仍待测，尚无整轮判定。
R051 新候选8bf正式适配器已绑定重新实际编译的CPU extension 4e3f1782d8de965837a817618642497097ab370e0b532a87f63afe924f1e3576（12,626,240字节），pinned沿用60e469f0…，父eff native保留10a2bd83…；候选源码及native Linux微小回归11 PASS，无skip，provenance_v5 SHA14b1d96e58522179e02dc13cf20d76e8d2157c559007b69bf4e97e005dddd9ec。
R051 最终source_v1=/data2/FreeToken/runs/dev_T16/r051_real_path_source_v1，MANIFEST1f54d2d23400ae6b071eb3f40a0729a71f47623a566bdd4cb6ef3e9255c3963b；Linux冻结工装CPU50 PASS，report6b2c5ec5b6b8ad74de714efd49762b6710d742cd2f154043f814897615f25f20。R050运行/封存source_v5字节未改。R051尚待队列头实际空跑与独立R签启动复核，没有GPU通过结论。
