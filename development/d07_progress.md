# D07 候选源码交付（2026-10-04）

状态：已交付待验证；代码、CPU 与 GPU/正式业务验收分别维护。

- 分支/完整提交：exp/e2d07 / fefb19cbac6bb1cb08835c411c895310600b3677
- 直接父提交：D06 / 03692633df48456fb0baa78de7b64e5628a12ab1
- 本地工作树：development/e2d07
- 服务器隔离工作树：/data2/FreeToken/wt/e2d07
- 源码bundle SHA256：d9975522e5c1add1c8b88ac7d9a12523e1d5a156d7b43bcb9f879adaa0b25510
- 准确Git blob Linux CPU：28 PASS、1 SKIP / 3.51s；来源明确指向服务器e2d07。跳过项为真实CUDA D2H abort，等待串行GPU验证。
- CPU日志SHA256：ce1c42ea16d4bc9901061811439cce157a845a5da5b71daaf226683f58cb271f
- 机器报告：development/d07_candidate_server.json

代码在cache原地改写expert id前导出真实top10、稳定实际MoE层编号、请求UID和真实token布局。默认不开FT_DEV_ROUTE_TRACE时无收集器、额外buffer或writer；明确运行单测验证该守卫。开启后异步pinned D2H由event保护，失败/拒收/abort/close路径同步或保留buffer并显式报错；队列有界，后台独立线程写JSON/NPZ。trace模式关闭CUDA图与layer-major prefill并写日志，因此该轮计时不能作为性能数。

客户端使用候选树scripts/agent_trace.py --route-evidence generate/replay；服务器启用FT_DEV_ROUTE_TRACE与FT_DEV_PAUSE_ENDPOINT=1。默认客户端保留冻结工具行为，新增模式记录全部真实ACK（含delta0）、非负UID、准确wire输出预算、实际完成token累计数和finish_reason。2048接受/2049拒绝及真实generate输出schema→analyzer已做CPU回归。冻结companion逐字节固定，公共历史工具未修改。

分析器按请求合并完整prefill chunks，排除decode于suffix，逐UID交叉校验服务日志和轨迹recomputed_tokens；业务分布只使用trace所绑定UID，保留readiness等原始诊断数据。输出每请求/每层f、实测均值与范围、理论值、差和无条件界，越界报错。suffix及completion均有min/P25/中位/P75/max、≤64和>233占比、length和真实2048截断计数。

R_B定义：两路各10个专家时 R_B=20/|两路专家并集|。只对--two-decode所指定真实D06结果的两个UID、不同实际输入token SHA及各自token sidecar绑定的同批decode记录计算；缺证据pending，有证据却出现其他B=2组合则失败。已通过实际two-decode CLI输出+sidecars→analyzer及手算回归。

体积：原始数组20字节/token/MoE层；48层960字节/token，10万token约96MB（压缩前）。TP>1 trace明确拒绝，不提供虚假分布式轨迹。

独立源码审查的四项HIGH已修复并复验通过；T06命令模板已补显式客户端选项、server ACK选项和two-decode输入。早期失败CPU包/日志与旧源快照保留，不能累计计数或替代新commit证据。

尚未执行：D07父树与候选默认T16门（G2）、开/关钩子cold全文一致（G3）、真实逐请求suffix日志对照（G4）、CUDA异常生命周期回归和T06三条12轮真实轨迹/双路decode。候选以D06为父，其默认GPU门也仍待；仅CPU通过不宣称卡完成或科学子条件成立。当前单GPU由D03 f506的R018/b46占用，按主线队列串行。


### R024默认四臂门（追加）

2026-10-04：E2-R024-gate-D07已独立复算并D04封存kept，父D06与候选D07四臂128-token全文一致，13预填事件包含就绪请求。当前round SHA `27c30ef5bfc2aa1e0cb5e4ecc8e2bbe78fbdbe60003609492f4477448a935ae4`，manifest SHA `54401ae6c0bca5709c01b46bfc14e84e3619ae1f01e6ce54ed79d4868199610f`。仅默认等价门通过；G3/G4/T06及T17接受仍待各自验证，不授予E2-base.1接受。完整结果为 `plan/01_测试与调研/results/T16-E2-R024-gate-D07_20261004.md`。
