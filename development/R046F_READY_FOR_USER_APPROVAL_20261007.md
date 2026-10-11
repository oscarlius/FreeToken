# R046f：仅补 G4/T06 的 GPU 重试准备

准备完成时间：2026-10-07 22:58。R046e/b96已原地D04 failed_harness封存；独立通过的G3开/关两臂保留，本轮不重跑G3。

范围：G4以及T06的 G_seed12k、G_seed_45k、G_seed_real、G_two 四个普通服务。候选4fc2320dc0a29422ab61e383e5e1579460e9926e；窗口98,304，比例0.88。暂停关闭，路由追踪打开，调度overlap显式记录环境键为0。只有seed12k用于D15训练，其余留出；seed_real完整原样，触窗自然结束。

工装修正：API tool_calls对应worker stop仅允许明确的跨层终态映射；物理token序列、UID、请求输入SHA、D0、路由和serve环境仍逐项严格绑定。预填产生首token；EOS且预算未用尽时有且只有一个未送出的overlap forward，length/预算已尽不允许该项。模型EOS配置SHA固定；历史离线重放的缺环境记录明确标记为推断，新测量必须记录ENV.json及SHA。新reader也接受已过门的layer_major_chunk_ranges，未改变路由数据判据。

|准备证据|路径 / SHA256|
|---|---|
|真实完整入口|/data2/FreeToken/development/r046f_d07_t06_prepare_v5.py / bab3604c1c09eb6f511464fd419cf680d5a4f89a8424ea9f64be9c6b94e2c04f|
|Linux47 PASS，含已封存EOS/length只读重放|/data2/FreeToken/runs/dev_R046/r046f_v5c_source_cpu_20261007_225344/report.json / a6e8025c05c5c8d8cbc50b70628fdf4af3c686b8920f7292c9858b9f78263f5e|
|同脚本/路径/uid1000四scope真实FILEdry|/data2/_shared/runs/ft_rounds/.filedry_E2-R046f/dry_run_receipt.json / 34fd02142115ec2c8d0bc1528f46657e18554d94fee7bfb39f3387b80e29e9f1|
|独立R启动签|/data2/FreeToken/runs/dev_R046/reviews/E2-R046f-v5/review.json / 697fbfe23f6ffbda3ae265073ebf07e3721a1185667485297688971b2c05c960|
|R pin|/data2/FreeToken/runs/dev_R046/reviews/E2-R046f-v5/pin.json / a583e68994c077edc2f76603d632fd1053a3833f80a48c64f8702164e12cbfed|

独立R已在服务器真实入口回读require_startup_review通过；冻结工具/回执/签字只读。前置仅核验封存元数据，不重读原始测量。空跑没有服务、请求、锁或正式轮次。GPU测量尚未开始；启动准备PASS不能替代G4/完整T06验收。

批准后在GPU空闲时排队启动；不影响当时已运行批次。启动、边跑边复核、D04逐项执行。R061a的独立OOM故障注入重试仍等待其原申请回复；本审批不包含release/e2、部署或远端推送。

要求用户裁定的依据：CODEX_HANDOFF_20261006.md 第八节第4条“仍须停下问我：测量开始后失败”；R046e业务已开始，因此此次未完成范围重试需用户批准。
