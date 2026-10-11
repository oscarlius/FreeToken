# OOM 发布候选父链与门证据

截至2026-10-09 07:34，发布候选为 `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9`。远端工作树 `/data2/FreeToken/wt/e2oom-protocol-restart` 已核实HEAD一致且clean。该候选的默认门与注入式OOM恢复门已通过；D16补项R040j已not_met，全部GPU停止，发布门未闭合，未建release分支、部署或推送。

阶段祖先链为 `0aa23431 → 4c878f6 → d577e32 → 481d3a7`。首个箭头跨越9个提交；其余两个箭头为直接父子关系。以下每一行的直接父都是上一行，依据当前实际 `git log --format='%H %P %s' 0aa23431..HEAD`，不是根据提交名推断。

| 顺序 | 完整提交 | 作用 |
|---|---|---|
| 0 | `0aa23431e5b800797543bdecbf35a01045131d7d` | 已定版E2-base.1基础 |
| 1 | `695955ee6c6cccf52287b2a309b57798d0ae3f3a` | CUDA OOM后重启backend workers |
| 2 | `e6195adc6169e5f177e3382b41fee52e399c9249` | 重启期间有界请求等待队列 |
| 3 | `da5032288fd184fe4390daca9c6f201b2ac16fc7` | worker完整退出和替换失败处理 |
| 4 | `ea35f97da0f54400923cc4977cc36ec3b40382db` | recovery epoch隔离backend replies |
| 5 | `cef854083366bee7534a858c99153ca5e4ac5a6e` | 显式开启的OOM故障身份记录 |
| 6 | `013d73a908eeae9225a999fc2815122ee2469af9` | 测试等待异步准入 |
| 7 | `0c2cfff7a1de98f2405bb21a16d531d9cb0d60cb` | OOM准入边界测试 |
| 8 | `608251f00deea85a0b12b31cc1f43725f45fbf9b` | 使用配置中的重启就绪超时 |
| 9 | `4c878f6b3251cca273d8548e7f5cf58a56711d3a` | DEV OOM receipt请求绑定修复 |
| 10 | `d577e32f695019fbeafb0f20ed7eaac08ec547b7` | OpenAI chat/completions重启准入 |
| 11 | `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9` | Anthropic messages/OpenAI responses重启准入 |

| 阶段 | 已有证据 | 尚未证明 |
|---|---|---|
| 0aa基础 | T17、R041 kept；其各自工装候选和原始绑定保持原记录 | 不含上述OOM恢复补丁 |
| 4c OOM | R060c默认门kept；R061c实测、独立复核及D04封存not_met | 公开路由restarting提前503，实际排队恢复未通过 |
| d577 OpenAI准入 | Linux三个测试模块46通过；独立代码复核通过 | 未单独运行GPU门，不以其CPU证据代替481门 |
| 481四协议准入 | Linux五个测试模块124通过；官方SDK真实loopback路由8通过；R064/b119默认门4/48 D04 kept；R061f/b122恢复1/3独立终审24项通过、D04 measured：API身份不变、waiter1、新epoch、旧worker退出、128 token及完整SSE相等 | GPU故障注入仅批准公开chat路由一次恢复，不等于四协议各自GPU故障或重复压力验收；D16补项仍是独立发布条件。R061d/e原件保持failed_harness |

新修复只修改三个产品路由文件：`openai_api.py`、`anthropic_api.py`、`responses_api.py`；同时更新CPU测试。官方SDK CPU服务器使用真实FrontendManager和协议路由，模型运算由CPU假backend代替，因此只证明准入与协议行为，不证明实际GPU恢复。

SDK回执：`/data2/FreeToken/runs/dev_OOM/public_sdk_cpu_20261009/run_20261009_0145/receipt.json`，SHA `0e488ba0ea0e8edcd95540205ff63d08c19668306294d306b101583be9fca1d3`。官方SDK为openai 2.54.0、anthropic 0.125.0，后者仅安装在evaluation隔离环境。

R064启动签：`/data2/FreeToken/runs/dev_OOM/reviews/E2-R064-gate-OOM-v1/review.json`，SHA `66335ff8a90cb814bcdedd72e0403d4f8aef58404644007529319e1360bed07a`。实际启动记录：`/data2/FreeToken/runs/dev_OOM/launch_E2-R064-gate-OOM_batch119.json`。

D16使用独立工装分支effb996，其结果与OOM候选的产品身份分开记录；不自动合并工装或E3优化。warm2未取得专家缓存实际命中证据，R040h已追加改判待定。R040i因就绪轮询工装缺陷封存failed_harness；R040j仅修该缺陷，原6服务/8调用范围实际完成6调用后发现长请求全文不等，07:27停止，07:32 D04封存not_met；见 [R040j结果](../plan/01_测试与调研/results/T20-E2-R040j_20261009.md)。门闭合前不宣布发布验收完成。

恢复门完整证据见 [R061f结果](../plan/01_测试与调研/results/OOM-E2-R061f_20261009.md) 与 [D04闭合回执](r061f_d04_close/closure_v1.json)。
