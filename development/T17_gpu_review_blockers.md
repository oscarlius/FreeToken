# T17 GPU 工装独立核查要求

当前核查状态（2026-10-05）：以下五项已在 R023 冻结工装中闭合并经独立源码复核；准确Linux CPU stage为 `/data2/FreeToken/runs/dev_D14/t17_08cd1c8ca06f/cpu_validation.json`，SHA `530a49543c54c4a3b4e1abd130dcc33f150a98765c5d942d892a81d305cbaae8`。R022默认门已封存kept；R023真实测量在128-token输出index36分叉，四角色恢复字节PASS而8256三个浮点计算态不等，已独立封存not_met。R025/b53同分块诊断已独立封存kept：8192前缀、8256计算态四角色及128个输出token均逐位一致，但它改变FT_LM_CHUNK并增加观察，不改写R023判定；继续原4096分块下首层投影定位。下文保留发现时的问题及其验收要求，CPU闭合不替代GPU接受证据。

核查时 `t17_d14_gpu.py` 已在共享工作区出现；不覆盖该并行实现。
以下是 R023 冻结前发现的历史问题，均已按上述 CPU/source proof 闭合；T17 业务接受仍未取得。验收要求保留：

1. donor 为 `L+1` 输入时必须避免首 token 就终止的工装设计。当前调用
   `max_tokens=1` 进入 finished donation，缺少非终止 `donate` dump。
   使用两个 token，并以实际非终止捐赠记录作为前提；若模型 EOS 提前终止，
   原始响应保留，不能伪造 donation。
2. HTTP 文本相同不能代替实际采样 token ID 相同。保存调度器发出的
   `DetokenizeMsg.next_token`，绑定实际 UID、输入 ID SHA、准入和终止记录。
3. 当前 `torch.equal` 不证明浮点张量逐位一致（例如 signed zero）。恢复角色
   需要 shape/dtype 一致后比较连续张量的 uint8 视图。
4. donor 与 query 长度不同；比较的是 query 在全冷进程和真实前缀命中进程
   的同一输入。必须从原始工件推出缓存长度和恢复状态，不能把计划值作为
   实测值写入结果。
5. 冷热计算状态差异和 D2D 拷贝错误应分别报告。门要求仍遵循测试卡，不
   放宽阈值；保留任何计算路径差异，用 T10 分叉证据进一步解释。

正在开发的 `t17_d14_observe.py` 与 `t17_d14_artifacts.py` 用于上述原始证据
核查，未通过准确 Linux 测试前不得作为已验证的启动器。
