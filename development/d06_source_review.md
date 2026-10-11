# D06 独立源码复核记录

复核者为独立 code-reviewer Agent；主线记录其报告，不将复核文本当 GPU 结果。

初次服务器四项退回：drain 吞掉 idle、迟发 pause、idle 中普通 abort 触碰缓存、默认 ACK 计数热路径。再次复核补充绝对 deadline、active cancel所有权、默认 wire无新增字段。最新源码已分别修复，并补充CPU回归。

客户端初次八项退回：暂停包装字段、ACK前内容、无总timeout/同伴取消、事件期间与事件后计数混淆、提交skew恒零、stall用ACK结束、模板kwargs不同、ctx不是前端长度。主线修复后实际本地30项通过。最后前端DSV4问题通过明确本次Qwen标准模板范围、在请求前拒绝非模板路径闭合；README及T05卡同步声明。

最终独立复核重点：
- API使用ensure_future加有界asyncio.wait，修复Python3.10 wait_for取消race；绝对deadline覆盖入队及回包。
- standard-template前端以enable_thinking=False匹配请求，非模板模型在请求前拒绝。
- 源码无剩余HIGH/MEDIUM问题，建议COMMENT：仍需Linux及GPU证据。
- 复核实际运行客户端30 PASS、compileall和diff-check；Windows缺Torch，没有伪称运行服务端/GPU。
- 当时审阅原字节API SHA aa6fe2dec6feb2a5ebf1e6b42002fef8953d3ba9cc500d4a3cf3726c9ebf24d8；客户端 SHA ef28c6774d4fca2b19a2a86e90281a30623f9b053aedac35aad8a76dff0e5e3e。提交只归一化CRLF为LF，源逻辑没有变化；准确Git blob SHA见d06_candidate_server.json。

复核之后主线已取得准确提交03692633df48456fb0baa78de7b64e5628a12ab1的服务器Linux CPU69 PASS及实际TokenizeManager.tokenize输入ID等值证据，详细报告见d06_candidate_server.json。两次先前Linux失败报告保留，未覆盖。T16、GPU G3/G4、T05均未执行，不以源码复核或CPU通过关闭D06。
