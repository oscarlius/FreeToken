# R049 T21 real-path dry-run

## 最新§12发布窗口及同触窗重放（SSH9 2026-10-07 11:30）

当前R049九臂服务窗口统一98,304，性能ratio仍.88，512专家、988/eff、seed12k唯一训练+三个heldout和 `ft_r046b_route_manifest/v1` 保持。consumer新增精确98304/2048/96256 window绑定，旧49K manifest拒绝；实际file-dry在创建目录/build之前要求R046b measured、R050 kept及新window manifest，不能读active route。

heldout重放加载新 `r046_seed_agent_trace_v2.py`，每次发送前用实际candidate TokenizeManager/render_prompt/tokenize计算完整messages/tools/thinking IDs。源trace的window_completion给出真实completed_k及未发送的k+1完整payload；重放只发送已完成的k轮，并重新检查blocked payload仍>96256、IDs SHA/长度完全一致。每个已完成输入IDs也与producer绑定逐项比较，服务prompt_tokens必须等于实际前端计数。保留真实ft_dev SSE计时。冻结原replay的输出预算实际为 **32**，不改该科学预算；§12触窗判据仍预留2048且限96256，metadata同时记actual max_tokens和completion_reserve_tokens，不能混同。

Windows三套targeted **85 PASS/1 POSIX skip in 2.16s**，AST6 PASS，guard/CVD空/插件关闭、torch未导入；含真实R049入口的timed replay链、hash-pinned client loops、未改candidate frontend类方法及合成CPU tokenizer/IDs/SSE。此为源码契约证明，不是新真实模型前端或显存证明；没有正式route/raw/build画像/dry/GPU。旧Linux54/52保留，新Linux/source/real-dry/R由根重新冻结验证。新增CPU闭包为v2 client/test、producer新源/test、candidate tokenizer/tokenize.py，旧builder/reader/ACK/client2/D07/D0闭包沿用；真实前端还需FT venv transformers/torch及模型tokenizer小文件。六项raw/LF SHA见audit§12。

后续顺序为R056完整11测量measured+D04/R → R046b在98304/.80按真实客户端与observer完成/封存 → 本批最终filedry与精确source/receipt的R review → 性能.88测量。用户已批准窗口扩展，原seed超49K不再是待裁定输入阻塞；现场.80不足或测量开始后失败由根停问，不能静默再降ratio/剪seed/关闭科学trace。

## 最新 §11 producer/consumer契约补修（SSH9 2026-10-07 10:26:11）

本块优先于以下旧schema与修前CPU证据。实际最终 `r046b_d07_t06_prepare.py::manifest()` 输出 `ft_r046b_route_manifest/v1`；R049 consumer现仅接受该schema，拒绝旧 `ft_r046_route_manifest/v1`/其他schema。RID=b、candidate=eff、四role目录及typed训练bool、seed12k唯一训练和三个heldout逐项严格核验保持；其余已消费字段与实际producer一致。上游producer登记.80，T21性能.88不变；512专家常量及其真实CPU契约保留。

针对性tests **54 PASS in 1.33s**（R049单套、Windows），network guard身份/CVD空/插件关闭/torch未导入，AST2 PASS。全部T06 fixture现在直接调用实际producer的 `manifest()`，临时输出文件均标记fixture_only/not_measurement，不再手造manifest。新增producer→consumer原样消费契约及旧schema拒绝；既有错误RID/树/训练分区与高专家ID/256拒绝回归通过。未改producer或读取正式route/raw，未实际build画像/dry/GPU。

新CPU闭包在上一几何版本基础上仅加未改 `development/r046b_d07_t06_prepare.py`（SHA `4c4f5a8dda5574aa2da7faa0782c11688096749b7ac1e3183ade46f1006db1ab`），manifest调用仅需stdlib；同test相对目录提供即可，不需其运行工装/种子文件。新runner/test的raw/LF SHA登记于audit§11。旧Linux52保留为修前几何版来源，新Linux54/source identity及新review待根重新冻结验证；未同步服务器。seed_real87100>49152与真实R046b measured+D04前置仍阻塞，实际dry命令不得执行。

## 最新 §11 STRP几何修复（SSH9 2026-10-07 10:19:17）

实际overlay `config.json:103` 的 `text_config.num_experts=512` 已只读确认，qwen4_exp loader→cache→STRP reader完整传递该值。根随后授权修正本owner开发源：新增明确目标常量 `MODEL_NUM_EXPERTS=512`，builder的`--num-experts`和reader的expected geometry共用该值，移除两处错误256；候选988/父eff、性能.88、seed12k唯一训练与三个heldout保持。旧候选产品树、工具和冻结包未改。

本次Windows guard/CVD空、插件关闭的R049 **52 PASS** + R047 **25 PASS**，合计 **77 PASS in 0.84s**；AST2 PASS、torch未导入。新增契约在临时合成route中放入ID511/256/510，用现有纯CPU builder真实写fixture STRP，执行runner发出的reader脚本并确认512读入与ID511排名；256 builder几何拒绝高ID，256-header对512 cache拒绝。仅fixture读写，没有正式route/raw、正式画像build、实际filedry或GPU启动。

新test需要既有988源 `development/e2d15/tools/build_expert_profile.py`、`development/e2d15/python/freetoken/moe/expert_profile.py` 和FT venv的numpy；按测试相对目录提供两份只读小源即可，不需要package init/模型加载。根通报的修前Linux50/25=75 PASS（report f070…）和旧Windows75均保留为修前来源证据，不覆盖或续用。根接下来仅同步本runner/test新版本及必要既有CPU依赖，取得新LinuxCPU/source identity；新的启动review仍须最终source/receipt绑定。seed_real87100>49152与R046b未measured的阻塞不变，下面实际dry命令仍不得执行。

## 最新 §11 开发源更新（SSH9 2026-10-07 10:05:51）

根授权已将可写 `r049_t21_prepare.py` 的训练、heldout、manifest、D04前置和profile/prepare登记统一为 **E2-R046b**。必须是实际 R046b `measured`+D04，只读manifest schema保持 `ft_r046_route_manifest/v1`、RID=b、candidate=effb996；唯一训练源seed12k，heldout仅seed_45k/seed_real/two，四臂目录与typed bool绑定逐项核验。失败R046a、其他RID/树、重复臂或heldout、分区污染均拒绝。性能服务仍沿用D07 .88；route OFF/D0诊断分离不改。

本机新源码与R047两份targeted tests合计 **75 PASS in 0.65s**（Python3.14/pytest9.1.1），既有sitecustomize network guard生效、CUDA_VISIBLE_DEVICES空、第三方pytest插件关闭、torch未导入；两份运行源AST解析PASS。测试中的profile/服务/闭轮次只用临时fixture或mock；没有实际build STRP、读取旧route/raw、实际filedry、服务/GPU/锁/轮次启动。旧Linux33/20等证据属于旧源，不能证明本次修改后的来源。

此交付仅是未来冻结的开发源，未同步服务器。根需要Linux时仅同步当前runner和 `tests/test_r049_t21_prepare.py`，复用既有只读必要D07依赖，再获得新的LinuxCPU/source identity。seed_real首87100>49152的科学输入阻塞仍在；R046b没有measured/D04，**现在不得执行下面实际dry命令**。解决输入并取得真实R046b闭环后，才由根安排最终冻结入口的profile/filedry、新source SHA与精确receipt绑定的独立R review；不能沿用旧v1冻结/旧启动许可。

Before startup review, run as the intended FreeToken service user from
`/data2/FreeToken`:

```bash
/data2/FreeToken/venv/bin/python development/r049_t21_prepare.py --dry-run
```

It creates only `/data2/_shared/runs/ft_rounds/.dryrun_E2-R049`, never the
formal R049 directory. The nine formal arm names and order are retained. The
dry run dynamically binds a loopback port, writes the actual profile, service
environment/command/log/lifecycle, cold, heldout replay, two-decode, D0
journal, result, and measurement-journal paths with explicit `CPU_FILE_PROBE`
content. It never starts a service, connects to a model endpoint, takes the GPU
lock, or allocates a batch.

Formal service startup records only a whitelisted environment in `ENV.json` and
`ENV.txt`. Once healthy, it must extract non-empty `Parsed arguments` from the
real `serve.log` into `serve_args.txt`; the argv is not accepted as a substitute.
