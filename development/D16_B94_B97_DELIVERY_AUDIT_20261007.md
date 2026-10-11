# b94–b97 原始交付核对

完成时间：2026-10-07 22:58。来源是每批已封存 round/D04 history/独立R review及必要小型失败日志；本报告不重写原始数据或任何 verdict。

|批次|起服/测量|seal/collect与首失败|可沿用 / 不可恢复|
|---|---|---|---|
|R040b/b94|0服务、0臂、0请求|真实输入JSON被误绑定为seed文本SHA，input validation前失败|只能保留失败记录；没有可补造的物理数据|
|R061-OOM/b95|API已起；模型未初始化；0业务请求、0故障注入|scheduler观察器目录已有文件导致初始化拒绝；SERVE_CMD/日志/ownership/failure/cleanup存在|缺少的是未发生的测量，不能补成已测|
|R046e/b96|G3 off/on完成，T06首请求有140token|API tool_calls和worker stop跨层终止状态绑定拒绝；路由终止forward计数需严格区分预算/EOS|G3保留；G4与完整T06画像未完成|
|R040c/b97|slots2六case完成，slots4首case已测|service_delivery.json存在，但512预期物理送出仅2行可验证，捕获历史不全|slots2保留；余24case需新批次，不许事后补造|

“缺失”须区分未发生业务、采集遗漏、文件缺失、文件存在但内容不完整。现有证据不支持把四批归为同一个丢失文件问题。新delivery错误将包含arm、准确文件路径、expected/verified及首个错误，以便定位。

R040c已closed为failed_harness；新的补测用R040d，不覆盖b97，也不修改其判定。用户本次续跑指令只用于D16剩余范围；R061a已就绪的GPU重试申请仍待回复，R046f完整启动准备已通过，提交仅G4/T06具体审批。
