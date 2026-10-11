# R061a OOM 恢复实测补跑审批包

准备完成时间：2026-10-07 21:52。R061/b95 已起 API 后因观察器工装失败，故按交接书第八节第 4 条，新的 GPU 补跑需用户批准。旧失败轮次及 v1–v6 冻结源、签字均保留。

产品候选保持 `608251f00deea85a0b12b31cc1f43725f45fbf9b`，父树 `0aa23431`；R060b 默认路径 T16 门已 D04 kept。新 v7 只修测试启动脚本：直接加载观察器并调用 CLI，保持真实 multiprocessing spawn 的 main 文件；每个 worker 写入独立 `workers/<pid>`，BackendHandle 记录放在分离目录。最终生成脚本 SHA 已重新绑定，启动前实际核验脚本、观察器与 hook 的当前字节。未改产品或发布配置。

范围：一个冷参照请求；另一个请求在真实产品 `before_forward` 边界注入 OOM；恢复期间再排队一个同输入请求。检查 API 出生/PID 保留、受影响请求明确报错、原 BackendHandle 的全部 worker 退出、新 epoch ready 后排队请求完成、冷参照与恢复后物理 token IDs 和全文逐位相同。窗口 98,304、比例 0.88，route trace、暂停和 D0 关闭。

| 启动证据 | 路径 / SHA256 |
|---|---|
| 实际完整入口 | `/data2/FreeToken/runs/dev_OOM/r061_v7_actual_spawn_cpu_20261007_215040/development/r061_oom_owned_launch_v7.py` / `7706a342a0b5032513f5a8acd04f157c837d8391c91bdaf9cffd8aeb1d7ce358` |
| Linux 11 PASS | `/data2/FreeToken/runs/dev_OOM/r061_v7_actual_spawn_cpu_20261007_215040/report.json` / `0ad0523b347316dd48f2f672d8fbfe4792fb459902570ea89e7aab78f01d2014` |
| 同入口、路径、uid1000 FILEdry | `/data2/FreeToken/runs/dev_OOM/r061_v7_actual_spawn_filedry_20261007_215102/receipt.json` / `601d35f0cb014c653684d54dfc231c3cb3f3aceceecec19482bb03ac9b1e1bee` |
| 独立 R 启动复核 | `/data2/FreeToken/runs/dev_OOM/reviews/E2-R061a-OOM-full-v7/review.json` / `646292591883cfcc0bcc8e7e90b66cb7ff339310bc0af46efd36550454146e60` |
| R pin | `/data2/FreeToken/runs/dev_OOM/reviews/E2-R061a-OOM-full-v7/pin.json` / `91fff1a9b88d8558bcd0dd4d99fe82967007d9e83b64485ccc6be82934c75250` |

11 项 CPU 回归包括实际生成 wrapper、真实 spawn 与真实 WorkerObserver 的两 worker epoch 输入/token 写入；原 v5 非空根目录错误实复现；新 worker 自身残留仍拒绝；完整故障协议及物理 sidecar binder；旧 worker 残留、token/全文变化、生成脚本字节变化均拒绝。CPU 服务边界是夹具，尚未作 GPU 故障接受声明。

独立 R 实际 `require_admission()` 回读通过，13 个启动来源、不可变输入与原生两 SO 绑定完整；FILEdry 未起模型、未取锁、未创建正式轮次。批准后依就绪队列接续，不抢占当前 R046e；完成后独立复算和 D04。此批准不包含 release/e2、生产部署或远端推送。
