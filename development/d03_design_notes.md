# D03 设计及开发验证记录

最新检查点（2026-10-04 14:40 CST）：T10 R017的72实际记录已复核封存，11实际token分叉；R013/b45/PID2977969已通过独立源码复核、Linux18PASS并实际启动，最新宿主机观察为2/22采集、1/11成对摘要，下一个新进程加载中。T04诊断传递修复已Linux26PASS/扩大447PASS（2原有FAIL、6SKIP），真实CPU边界构造10PASS，Y129预测archive12672；新候选默认GPU门及实际恢复尚待。D06独立本地树已开始客户端/服务端实现，离线检查及代码复核继续；未上传或过GPU门。历史观察保留为历史，以最新结果及快照为准。

## 当前验证状态（2026-10-04）

- 当前本地及服务器候选提交：`c30ae0d7003c3bbbf56867ce74da797332fa7ed5`，直接父提交 `2e5cdab707ff8dde8723f138c45a6ba73a3a43f6`，D03开发父树为 `23f2e2caa3395837c9474735ffc83321f3b9b5a1`；服务器 `/data2/FreeToken/wt/e1r003st` 的 tracked tree 干净。
- 最新提交修复G4跨进程UID比较：只有明确提供两侧UID选择且各自匹配记录，才能比较不同UID；默认、单侧选择、前缀冲突及合法包络对仍拒绝。CSV分别记录两侧UID和映射来源。独立代码复核PASS，服务器48/48专项PASS；日志 `runs/dev_D03/targeted_cpu_uid_selection.log` SHA256 `6040252609e7e05f76a8c91887f5bb9163caa644fdb0c068595c77a341b1c30c`。
- 当前候选扩大回归444 PASS、2个已有FAIL、6 SKIP，失败集合不多于基线；日志 `runs/dev_D03/cpu_regression_c30ae0d.log` SHA256 `c4ba1cc5bfaeaa660c19f93e2fb7d2326ae4f9844eee61e422457eb03c646125`。G1满足失败数不增加要求，整组回归不称全绿。
- 前候选2e5cdab增加实际终止请求引擎token记录，取自CPU host buffer，包含原始prompt/generated IDs及int32序列SHA，不使用文本重编码。仅随FT_DEV_LOGITS_DUMP开启，默认关闭；独立代码复核PASS。该候选专项46/46 PASS，包含真实Req.append_host测试；日志 `runs/dev_D03/targeted_cpu_terminal_tokens.log` SHA256 `0eae1ce8b860bce4694b97fc1c21836df657dcb8f99b55fc515a7017dd051af4`。
- 前候选3267490使用 `len(tokenizer)` 校验原始token-id总词表边界，包含新增特殊token，总词表248077；该候选专项35/35 PASS；日志 `targeted_cpu_added_tokens.log` SHA256 `afa8dfa74d162d158059281daab547dfdb72230d5387555a00a717d436c49f8d`。
- 专项25/25 PASS；日志 `/data2/FreeToken/runs/dev_D03/targeted_cpu_run3.log` SHA256 `acf37d54d2d43d454b84392b412e86651d972c9cee58e8d3bce7f35b4149bead`。
- 扩大回归431 PASS、2个已登记FAIL、6 SKIP；日志 `cpu_regression.log` SHA256 `4e0e5cc31f619ab6ff87e543f200e27a8e814ef0a16ce786b5a7750573dd22f5`。失败为 `test_prefix_commit_sentinel_guard`、`test_post_terminal_overlap_step_is_dropped`，不将整组回归写成全绿。
- G3已在真实历史dump_B→dump_A复现论文三长度首层/末五层两位小数结果，输出 `/data2/FreeToken/runs/dev_D03/g3_envelope_refB.csv`。默认长度集合不等拒绝也已实际验证；首次错误分母方向的输出保留，没有覆盖。
- G4/G5当前真实输入：`runs/dev_D03/historical_raw_ids_c30ae0d.json`，21976个token、messages_sha `3550ee9010430096`；文件SHA256 `6a08e2e855acacab103eeb4ea0d07972f3e477506020783ec930dbca744fa1e2`，int32序列SHA256 `327e35d27fec334e2907e91f278798f789d787157528a71dd0e4da46babd6285`。旧输入全部保留。历史回放上限32，与生成记录512及T10新回放200分开绑定；G4新UID从实际token记录与服务进程组证明取得。
- 两份D03候选CLI已同步：state_envelope.py MD5 `f95a58a588161f15b2b1efabd1a7b842`，logits_probe.py MD5 `e66328421bb9b8ae82af5595f9da942a`，本地/候选/正式scripts一致。T16隔离runner MD5 `00661195a6df1a6f6456fc938c489381`，服务器自检及inert preflight PASS；正式E2-R002-gate-D03 / batch38 已启动，父进程PID2391970。原基线T16未覆盖。
- 首轮GPU开发自检PID2209743因测试客户端重复拼接`/v1`而停止：实际POST为`/v1/v1/completions`，HTTP404；错误工件SHA256 `4cce4efa4864a2d5a87484bf68938df9fdd1df97286e59eeca55875b215d37eb`，原manifest SHA256 `00262c9f9923a0c867a540b0011bf005d07a5184e6d74585395cd93f87665b60`。原目录保留，服务与自检已退出，端口释放/锁不存在/GPU4MiB证明已保存。这不是logits数值比较失败，首轮未完成G5。
- 修正调用地址后的新GPU自检已结束并独立只读复核PASS：输出`runs/dev_D03/gpu_selfcheck_c30ae0d_urlfix/`，runner SHA256 `4cf751a93457ef28a88fc175004c86d12130b84943193cb43c55254c2e0fb453`；manifest `4e8d18429ecaef5b8f856f73a4c913c1a08068f9f433acce73091a4cb27764c3`，selfcheck.json `0df7652aa8014d0c5361ee78d51e79a34f7822cc606cde5253c94fb5336fa6cc`。冷parent OFF=candidate OFF=ON逐位一致；OFF无诊断工件；七边界完备；G5双独立进程64/64 FP32全词表逐位一致，top1=1、KL=0。六臂服务及PID2291096均已退出，锁/端口释放、GPU4MiB。历史12672记录有74层/角色，但没有合法包络阈值，不据此宣称科学验收通过。
- T04/T10消费者已按真实终端记录、G4哈希字段、logits客户端URL及D04检查CLI修正；11项专项工装回归在服务器PASS。当前冻结交付为`runs/dev_D03/phase2_tools_c30ae0d_ready/`；T04 SHA256 `d7226c466e5922ecc4e80d80dc2b634592e1449538587d3232d4f3b9176723eb`，T10阶段2 `d6e01dee6fd39e59976f5b9f90b798b27dded4a7e516bb97debe10e237c2e2e9`。较早两份开发工装交付保留，后续执行只用当前冻结版本。
- T04阶段2 CPU包络已独立复核：11历史A长度、814点、199点超出R4096→R8192包络，最大比值5.489091417；当前工具G3表复现通过。结果见 [T04阶段2记录](../plan/01_测试与调研/results/T04-E2-R014_20261004.md)，GPU边界/logits仍待。
- T04/T10阶段2消费者命令及原始token证据要求见 [d03_phase2_commands.md](d03_phase2_commands.md)。T10已封存输出只有文本/parts，尚缺真实生成token序列，不能把first_token_proxy作为引擎分叉位置。
- G4/G5及开发开关ON/OFF自检已留证；G2/T16 batch38四臂全部完成，独立01复核PASS并由D04封存，历史链/只读/全量清单校验通过。MANIFEST SHA256 `2bc41220885af37386e0f365ef2fba3be97c39e96ec585b4a4cf9ed7dbd8526f`，初版round SHA256 `77bfb5d0cf57950fdbea4b02550a18fdc0acd5373affa17163257238e7cdfeb4`，正式判定pending_review。T04已启动为E2-R014/batch39/PID2493982；T10实际token与阶段2仍待，D03尚未完成业务验收。
- T16封存wrapper已独立复核并发布，SHA256 `f188e3cc7ba228cd76b4b9afe690ea4d7ed8f09a34fcaefba06e7f2ff431db04`。写前核验所有输入，异常回滚仅本次新增文件，封存证据出现后保留；Linux真实D04工具故障回归5PASS，日志 `c45e78d927aa6cc86c3af7ffebe1bb506dc10d7ca7110009debbb589f0b63aac`。
- 阶段2收尾preparer已独立复核并在Linux实际D04封存fixture上19PASS/1.65s。SHA256 `24e8656380890c0eb04b3ee67c52b8c32525c8a96ad93fc0f5f4d9cc1d6f9d50`，测试 `46d3e67cc9a8fa0f19b2b9875367f03f5d6049f6cfad5ac0032e65c54d460894`，日志 `7a240a74c52e445123f4b8f822d8157e04ce0debd348ace073f144a94f31df0f`；发布于`runs/dev_D03/d03_phase2_prepare.py`。旧7b3a014版因Python哈希接口不兼容的19FAIL工件保留，未发布。
- 最新T04观察：2026-10-04 11:56:04 CST，R014/b39/PID2493982已退出，锁不存在；只完成candidate_boundary capture，restore臂`--require-restore`报`measurement did not prove an actual state restore`。其余recompute/legal未运行，完整数值比较未产生；失败工件保留并独立核对，不使用完成态preparer伪造封存。

最新业务验证：T11 R011/b40已封存，科学写回归因仍未解决。T04 R015/b43在restore臂失败：实际host12416不是12672，末段FP32 index又丢logicalprompt初始缓存/proof。独立本地 `e2d03-continuation` 分支先写回归再修普通分段诊断传递，c30运行源不变，不改计算或阈值。T10 R012/R016失败保留；新R017/b44/PID2786369工装已独立复核及Linux28PASS、只读冻结后启动。结果见T11-R011、T04-R015、T10-R017。

R017元数据版本 `phase2_close_r017_a52e39e` 独立复核PASS、Linux55PASS，helper SHAa52e39e95cf002aa3909b860ff084ff7c85f3d91261d1c75baa9e74a38671581、日志SHA152e14aa605406de6ebf8020ef3ab9a816169a4dc7a378bd5a02a71e496dd60b。只有R017要求六实际HTTP replay、canonical12键、cap200和manifest/terminal原始结束语义绑定，RUN清单必须覆盖；历史格式保留。当前测量未完成，不执行prepare/封存。

父树 `E2-base@23f2e2c` 已经T16-D00及T00接受；T04阶段1完成后并行实施D03，固定基线GPU测试不混入候选代码。代码已交付，业务验收尚未完成。

受控R015工装最终交付：server `runs/dev_D03/t04_retry_r015_71d4846/` 全树只读，launcher SHA71d4846071762613989b22cfa76e52b6cbdf18e6ef7b4463aa8145d2b734a5d1、runner SHA1f8dcac3f75bcd98b38b496068e727d13435cdf60117f0d99c27b95370445458、client SHA14b1eb09a9a49ba4c46176ca3edc5d52b927a07f4c476ae55c1d144c979c50fb。独立源码复核PASS，本地及Linux20PASS；Linux日志SHA168bb88573b44876966c64ec2dc2b9e030fc7635ca0b18538678f1c492c97ea2。精确probe单次readbytes/SHA/compile，防旧轮finally写回，receipt启动前预占；继承旧源身份如实归档。较早_ready包18PASS保留不启动。R015/b43实际启动wrapper SHA1e442030204ae7f0af5b5f03d8c629c8cba2f88dcf539715fa5b338f86891f6b，13:05 CST身份一致且加载中，不将启动视作科学验收。

新版初始元数据preparer SHA6016c37996a3e06d78002dc688cc693cca0a39a6ff915c3ae898787e706b7b2d，server版本化只读路径 `runs/dev_D03/phase2_close_6016c37/development/d03_phase2_prepare.py`；独立复核PASS、Linux43PASS，日志SHAcd41d0099d374d79ed49466f9cadf464b01e7034210b22e17d58e32810d31e74。新增R015/R016，绑定冻结terminal/raw-binding/trace三原始SHA，拒绝coherent替换、source/UIDPID伪造、缓存污染、短proof、branch改变和漏RUN成员。原全局24e8656版保留不覆盖。

- 多边界必须从同一次 `gdn_prefill_chunk_fla(return_h=True)` scan 取 h 行，复用现有 track 的 recurrent/conv 复制方式；不能用拆批或改变 token 执行顺序制造参考。内部 ×64 边界与完整 extension 末端分别处理，末端从 live state 读取。
- 所有边界要同时包含 conv、recurrent、PLE conv、PLE ngram；跨层与层优先 sub-batch 保留原 UID/global cached offset，完成全部层后才发布一个完整状态。默认环境不分配诊断状态、不建目录。
- 现有 recurrent pool 默认 **float32**，不能因 conv 是 BF16 而将 recurrent 改成 BF16。h 与 pool 的维度复制遵循现有实现，任何相对误差从实际比较报告，不用转置或阈值改动制造通过。
- 存储容量须在实现时闭合：hybrid_radix pool 是 `4*max_running_req + max(4,int(ratio*max_running_req)) + 1`；两路最低默认为13槽。诊断若直接 `alloc(7)` 会争用已有请求/树快照，不能假定始终有7空槽。采用只在开发环境启用的独立诊断存储，或在初始化时显式预算额外槽位；不得在有活跃请求时调用 destructive rebuild。落盘序号统一，防止两个 pool 的 `_dump_seq` 撞名覆盖。
- Logits 从同次完整 hidden 选最后 K<=64 行，经复用 TP gather 语义的 head 得到 FP32；普通 head 已只留最后行，不能从其输出倒推。层优先最后 chunk<K 时需跨已有末尾 hidden 拼接，不额外 forward。
- token-id 输入只在 FT_DEV_LOGITS_DUMP 环境启用，绕过模板且严格验证原始整数（排除bool、空/嵌套/负数/越 vocab）；未启用时保留原 unsupported 行为。
- 三臂必须记录同一真实 input_ids SHA、位置/预测下一token对齐、K、state角色和每层SHA。restore臂必须有真实 resume/cached 证据，不能仅凭 host_slots=32 称发生恢复；warmup 输入与测量输入分别记录。
- 离线 state envelope 按角色、长度、层和形状比较，集合不全失败关闭；合法重排包络单独提供，不拿固定2%阈值代替。零范数/零包络、NaN和无可比长度均需明确处理。
- 交付验证仍为单元/离线 -> 开发 GPU 无损自检 -> T16 默认门 -> T04/T10 阶段2；历史 G3 三行表、G4 boundary12672和G5双进程同输入 logits 独立留证。

## 当前源码补充挂点

- `server/openai_api.py:_completion_unsupported_reason` 目前会在tokenizer之前拒绝所有token-id prompt；仅改tokenizer无法实现开发探针。D03需要同时处理开发环境下的前端严格整数验证、单个id序列封装和后端原样传递，默认仍返回原unsupported行为。
- `models/qwen4_exp/model.py:forward_layer_major` 仅对最后chunk做top mixer并返回；开发用末尾K行若跨chunk，应从已计算的hidden选行后做只读投影，正常最后行采样仍走原调用。不得为补齐K另起model forward。
- 每请求的K、UID、完整input_ids SHA必须随消息/请求传入；不能根据被模板重新编码的字符串或输出token猜测。小于64的X也须准确记录实际K。
- T03实物已确认D02 `reqs.cached_tokens` 是首次admission的cache hit，continuation贡献0。它不是执行前缀累积量；D03边界全局长度应读取调度Req的实际cached/extend偏移，不从D0 cached字段递推。
- 原agent trace的`messages_sha`是canonical SHA256的16hex前缀；逆序回放的`round`是原列表位置，而`record.round`保留源轮次。D03工具若读取这些轨迹，沿用已核实的输入绑定语义。

## 同次scan边界与真实历史张量的只读证明

- `h` 的实际形状为 `[1,sum(ceil(extend_len/64)),V,Dv,Dk]`；请求i的内部边界用 `h[0,boh_i+(L-cached_len)//64]`。只有前向相对偏移为64倍数的内部边界可直接取样。若cached_len不对齐，不能把相邻h行冒充全局L处状态；需明确拒绝或采用卡片允许且独立标注的另一合法重排。
- `L == extend-end` 时h不含最后行。必须在当前GDN层/当前chunk完成后立即复制live状态；层优先下一chunk会覆盖同一槽，不能等整个forward结束才读取旧chunk末端。每层即时只读复制，收齐全部36 GDN层和两PLE角色后才发布完整boundary记录。
- PLE ngram窗口取 `tail(进入当前chunk的ngram_context + 当前input_ids[:local_L],ctx_len)`；PLE conv同理取 `tail(进入当前chunk的conv_state + x[:local_L],state_len)`。短局部前缀与packed多请求须保留各自incoming状态，禁止负索引穿过请求边界。
- 真实历史A/B各有11个共同donate长度；G3三处无重复：12416 Aseq33/Bseq12，14080 A23/B7，21568 A10/B2。device四角色按名称比较，不以文件名匹配。archive的host和hostslot是额外搬运证据，不能混入A/B donate曲线。
- G3只读CPU复现相对L2百分比（首层；末5层）：12416 conv `0.24;11.77,14.59,11.69,10.89,8.50`，rec `0.40;3.18,14.23,3.62,8.21,9.71`；14080 conv `0.00;9.89,11.05,15.58,9.68,8.40`，rec `0.18;4.98,14.22,6.91,14.04,12.29`；21568 conv `0.12;15.07,16.76,17.83,14.04,11.18`，rec `0.39;15.54,20.78,13.74,24.49,17.42`。与论文已有发布精度相符，正式工具仍须自行重现并存自身输出。
- G4确有A/archive12672，seq4/uid1，四个device角色完整：conv `(36,1,10240,3)` bf16，rec `(36,1,48,128,128)` fp32，PLEconv `(1,1,10240,9)` bf16，PLEngram `(1,1,2)` int32；另有host角色。默认设备侧比较须显式选择device角色，host侧独立规范化，不能忽略任意未知角色制造匹配。
- 最小测试案例已明确：packed extend65/128/130、精确end128、cached64+extend128、cached32不对齐拒绝、层优先早期chunk-end不被后来状态替代、PLE短前缀和packed窗口隔离。
- 历史donate长度集合并不完全相同：A为 `12416,12736,13056,13248,14080,18944,20096,21248,21312,21568,21952`；B额外有 `13376`（uid8）。D03默认必须拒绝集合不匹配。G3复现使用显式 `--lengths 12416,14080,21568`；指定范围外不参与本次计算，范围内任何缺失仍拒绝，不静默取交集。
- G4是历史A/archive12672与D03**新采集**的同输入boundary12672；历史B并无12672记录，不能以B/donate13376替代。工具需支持左右独立kind选择和明确device/host tier；多个UID在同一长度产生boundary时，需显式UID/输入筛选或报告歧义，不能按最后seq把不同前缀配在一起。开发记录应保留完整prefix hash；历史无hash时以实际trace输入绑定及UID证明关联。
- T04阶段1实测R4096/R8192/RLM各12donate长度。历史B→R4096全部逐位一致；RLM在12416/18944的 `slot:ple_ngram_ctx`（int32）maxabs分别108521/4073，经01实际tensor复算确认。这两处不能解释为普通浮点舍入，也不能直接将RLM曲线当作已准入的合法数值误差包络；D03只读边界工具应明确取样语义，不能顺手修缓存恢复计算。
- logits末尾K也可能跨**普通分块的多个forward**，不只跨层优先内部chunk。例如完整输入8254、K64，第二块止于8192只覆盖末尾区域前2位置，最后62token块覆盖其余62位置。每个forward仅投影与全局末尾区间相交的已算hidden，按UID/全局位置保存并在K行和全部最终state齐备后发布，不能把最后62行当64或重新forward补2行。原始完整input长度/SHA、K随请求保留，不能用当前截断segment的input重算“完整输入SHA”。
- G3论文的相对范数分母是重算B：`--ref dump_B --test dump_A`。实际12416末五conv，以A为ref得到11.66/14.67/11.62/10.91/8.45%，以B为ref得到11.77/14.59/11.69/10.89/8.50%，差别源于分母方向。工具仍严格使用ref分母，不调整数值或精度迎合表格；首次refA输出保留为g3_envelope.csv。
- 层优先可包含已缓存前缀，调度器没有cached_len=0限制。诊断另携带 `_dev_cached_len=原请求cached_len+内部lo`，原计算字段cached_len=lo保持现状；边界/logits绝对位置使用诊断偏移。当前基线的此路径计算是否正确由后续状态实物判断，D03不修恢复计算。
- D03开发落盘仅支持TP=1，多rank初始化失败关闭，避免各rank争写同名文件；关闭新环境时不限制既有TP路径。
