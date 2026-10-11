# R036 第 15 组 reference_1 运行错误观察

只读观察记录；不是轮次终态或验收结论。

- 用例：prefix_12736_tail_65_reference_1；batch65 / E2-R036。
- 控制进程 PID 3851074，start_ticks 129813658；服务 PID 1064642，start_ticks 132887291。
- 服务器日志：/data2/_shared/runs/ft_rounds/E2-R036/prefix_12736_tail_65_reference_1/serve.log。
- 调度 worker traceback：scheduler.py:949 -> prefill.py:470 -> dev_prefill_schedule.py:104；ValueError: development schedule rewind requires a layer-major donor。
- 05:10:51 后端 supervisor 报 worker exited；05:11:01 API 报 worker cannot be restarted 并开始 shutdown，等待连接关闭。
- 05:15:27 CST 只读核实：控制进程和 API 前端仍存在，控制进程子进程为 1064642；failed_harness.json 与 result.json 均不存在。不能将前端存活或 HTTP 200 解释为后端继续生成。
- 按 INTERVENTION_20261005_2045.md：只记录，不停止、不重启、不改 batch65 及冻结输入，不新增快照或克隆。等待控制进程产生终态后再由 R 复核原始数据并 D04 追加封存。
## 自然终止后的证据

- status_batch65.json 更新于 2026-10-06 05:40:34 CST：state=failed，error=TimeoutError('timed out')。
- 随后只读核实控制 PID 3851074 已退出；failed_harness.json 存在且 admitted=false，result.json、round.json 不存在。
- GPU lock 已不存在；服务清理与 GPU 实际占用仍由 R 独立核查，锁不存在不等于清理已通过。
- 原始 schedules/prefix-12736-tail-65/schedule.json 为 [0,12480) layer_major（4096/4096/4096/192），[12480,12737) ordinary（257），[12736,12801) ordinary（65）。一 token 回退发生在普通 donor 段之后，被调度入口拒绝。
- 失败原件保持原地只读；R 已开始轮次结束复核。下一轮前先核对普通 donor 的检查点能力；尚未将超时归类为纯工装缺陷，也未宣称任何组正式接受。

## 保持实际调用结构的候选修复

- 本地 Git 工作树：development/e2d14-schedule；候选提交 e78bf8d090e57304bc3e4a5f7bddd88940517ffc（产品修复 c70c007，随后一项回归测试 tuple 构造修正）。
- 新服务器专属工作树：/data2/FreeToken/wt/e2d14-ordinary-rewind；R036 使用的 e2d14-schedule@e45e2c2 保持不变。
- 只修改 opt-in dev_prefill_schedule 的 admission：普通 donor 同样具备 FLA/GDN/PLE checkpoint 写入路径，允许保留其实际 ordinary 调用；仍检查回退网格对齐、内部 FLA 边界，新增零长度内部检查点拒绝。
- 引擎回归保留完整 [0,12480) layer_major / [12480,12737) ordinary / [12736,12801) ordinary 结构；核对 checkpoint slot=6、边界=12736，并在 tail forward 前调用现有全状态池 copy_from。模型和池为 CPU 替身，此证据不证明真实四态数值或输出逐位一致。
- 服务器 FT venv、既有 startup socket guard、CUDA_VISIBLE_DEVICES=''：解析与引擎回归共 29 PASS，3.45 秒，1 项 CPU Triton fallback warning，无服务启动、端口请求或 GPU 入场。
- 首次本地 pytest 遇到缺少 FT 环境的 conftest teardown；独立 parser 13 PASS。首次服务器回归发现新增测试把 tuple 写成 generator（27 PASS / 2 FAIL），已修正并完整重跑上述 29 项通过。
- 新 D14 提交须先完成对应 T16，再重跑 T17；轮次与批次重新登记、脚本新版本经 R 启动前复核，不能原地更新旧冻结源。R036 已完成组的保留/合并仍待 R 原始数据复核，尚未新建 E2-base.1 标签。

## 新候选 T16 启动准备

- 保留 e78bf8d 本地原分支；以相同 Git tree 建立单提交 a9dca443cd07e1f60d1533e0a678935a09d21636，直接父树为 R032 接受的 e45e2c2。这是父树明确的正式门候选，不覆盖原始历史。
- 新服务器专属 worktree e2d14-ordinary-rewind 更新到 a9dca443；R036 原 e2d14-schedule 仍为 e45e2c2。
- 现有 T16 runner/launcher/stage 仅更新候选、父树、工作树与 CPU receipt 绑定；CPU stage 加入既有 startup socket guard。已冻结历史包不变。
- 候选 CPU receipt：/data2/FreeToken/runs/dev_D14/ordinary_cpu_a9dca443cd07/cpu_validation.json，SHA40047c2f321b07e00457eec82ac06ca67147f8c103a3e6287436c7678434390b；29 PASS，CPU，未发请求。
- 实际 T16 stage：/data2/FreeToken/runs/dev_D14/t16_schedule_506e8b062c73；CPU report SHA8271e4fc83dc7bde5956567ce715950eef50bf16b5a22d5293dc3cd56a594668，PASS。
- 只读预检核实两棵树的实际导入、compiled extensions、D18 探针、候选直接父树与 GPU 空闲：PASS；分配预览 E2-R037-gate-D14 / batch66。尚未 reserve/launch，启动时重新核实，若账本变动就重新取号。
- 已请求 R 在 R036 封存后对本次实际 T16 启动做一次独立复核；未经该复核不启动。

## E2-R037-gate-D14 / batch66 已启动

- R 启动前独立复核 PASS：development/R037_T16_D14_PRELAUNCH_R_REVIEW_20261006.json，SHA d505689f189882309ab4ebc2fd344aca6b12feb901da6288cb92295b83ad7cfd。
- 2026-10-06 05:55:58 CST 正式启动；controller PID/PGID/session 1196459，start_ticks 133184006。随后 /proc 只读检查存活，status state=running；GPU lock owner=E2-R037-gate-D14、card=T16、pid=1196459。
- 启动过程重新验证 frozen stage 及来源，local transport 与进程回执均保留在 development/t16_d14_schedule_506e8b062c73_launch_transport.json、development/t16_d14_schedule_E2-R037-gate-D14_launch_receipt.json。
- 新提交 a9dca443 与原接受父树 e45e2c2 对照；继续运行原 T16 layer-major / ordinary 双口径、D0 与生产臂，尚无测量或正式接受结论。
- 下一轮实际 T17 的 source admission、launcher、batchNN_T17_v3.sh 已在本地更新该候选及 R037/b66 前置绑定；未冻结、未发请求、未启动。原件保留规则下的剩余用例选择仍待 R036 原始数据复核，不能将本地 --cases all 草案直接当批准的续跑策略。

## 后续实际 T17 准备：复用历史 fixture

- 旧 startup stage 的 snapshot 复制步骤已删除；现有 source admission 和 CPU retained replay 都读取既有只读 /data2/FreeToken/runs/dev_D16/v2_retained_cpu_f0f3a1abd0fc/snapshot。
- 历史 fixture 仍明确 source_model_round=E2-R034a、source_candidate=e45e2c2，与新候选 a9dca443 区分；核对既有 replay receipt SHA ee4f8dbc5ff2feebdb98a393f0aca9277ddf299fcac35b796e8e6ddf560ab247、原始 snapshot 完整文件映射及只读模式，不复制和改写它们。
- 新 stage 的 CPU pytest/import/replay 环境加上既有 sitecustomize socket guard；当前 stage 的模块优先导入，避免 guard 目录旧工具遮蔽当前模块。
- 本地 socket guard + CUDA hidden 下，现有 source admission / launcher 测试 49 PASS / 1 Windows 权限相关 SKIP。新 Linux stage 与历史 fixture 原地复用仍待验证；尚未运行冻结流程或启动下一轮。

- 2026-10-06 06:08:10 CST：新版 source admission 通过服务器 Linux 原地旧 fixture 完整清单/只读/来源与 SHA 校验（通过 stdin 内存执行，socket guard+CUDA hidden，未落盘脚本）。retained_fixture_readonly_verified=true，copies_created/services_started/requests_sent=false；新正式 startup stage 仍未生成。

## 14组旧测量的补丁适用范围核对

R暂定reuse_permitted=false，理由是旧e45结果未直接证明a9接受；下一轮remaining入口暂停修改，等待实际启动前复核判定。随后通过已有socket guard + CUDA hidden，在服务器stdin只读执行两版dev_prefill_schedule.py。git diff e45→a9的产品Python路径只有该文件：删除ordinary donor拒绝，新增无interior checkpoint拒绝；engine/attention/models/kvcache源码没有改变。对R036已落盘14份实际schedule逐一运行两版parse/admit（rewind_alignment=64,fla_chunk_size=64），14份admission输出全部相同；所有rewind.previous.mode=layer_major，previous.start=512，current.start=8192或12416。因此此次补丁对这些实际schedule的admission不改变。未启动服务、未发送请求、未写服务器原始轮次。该检查是源码/调度适用范围证据，不证明新候选GPU数值接受；已交R在实际下一轮启动前复核中判断，原始14组清洁复算仍待完成。

R037/b66 于2026-10-06 06:46:31 CST自然结束，8臂探针和清理完成；status=complete_measurements_pending_review、proposed_verdict=kept。原gate SHA c6afc376fe472b633e25be0df68bc2e39800f0d91fd69070d09ca7f12acebc7a，候选a9、父e45。controller1196459与最后service1325945退出；gpu.lock自然释放，nvidia compute-apps为空。原始目录155文件、1,042,197字节、无.pt工件。该结果仍待R原始复算/D04，不能当正式T16接受。已交R执行结束复核。

R独立核实14份旧schedule均在补丁未改变的layer_major分支；只有原始逐例重算全绿、原case/input/schedule SHA精确绑定后，才考虑许可限定14组跨候选保留。实际成功raw verdict为measurements_pass_pending_independent_review。remaining入口恢复实现，必须显式reuse_permitted=true，不以旧源测量直接宣称新候选通过。

实际T17启动器与batchNN_T17_v3.sh已接remaining参数：显式resume_review及caller SHA传入dry plan和运行入口；预检与最终launch分别重核SHA，all模式拒绝被忽略的resume proof。默认all行为保留，新入口尚需selector/runtime交付及R许可receipt。既有启动器目标测试在socket guard启用、CUDA hidden下21 PASS/1 Windows bash fixture SKIP；服务器bash -n语法通过，未执行批次。新包与GPU启动尚未进行。

remaining选择/runner/runtime已交付并统一验证：guard+CUDA hidden，selector、runner和launcher目标合计39 PASS/6 Windows相关SKIP。remaining必须绑定R036 canonical前14、原输入/逐例文档/schedule SHA及显式a9跨候选许可；原始result归档记录remaining_cases_only，不能当全28组接受。服务器即将用于R038的单一startup CPU stage已开始：t17_startup_cpu_cb6ef8de834d；原历史fixture原地复用，无全量复制；CPU报告尚待完成。local session76155。

R037 round-end R review PASS，SHA6097b66fe264221445c8bf1d13c45033cb191f445a5985012f037f7cab8efa87。本轮最小D04数据绑定development/t16_r037_close_binding.json已生成，SHA984d7ca5750fa0bcc6adf73d25cb8477b1caa24f32ba5736fb831154e9624187，同源服务器444文件/data2/FreeToken/runs/dev_D14/t16_r037_close_binding_984d7ca5750f.json交R核实并使用既有D04程序封存。未新增通用closer或CPU复核链，未写原round元数据。

R037已由R正式D04封存：round SHA470bccbf946b181dcc263fcebbbb9105577d5063f3ccec154769f400f3ec14b1；manifest SHA5e8f24f59dbc0b50c0dcfb306b01be06dc1a8eb21b64d6c24875f9b14869e6c7；closure /data2/FreeToken/runs/dev_D14/r037_gate_closure_r_overlap/closure_receipt.json SHA15d74a8c131f5cfdcf6b549d0d6a9d2f24a28ac46efa86fec57bc96a456bf8c9。实际下一轮runtime在server guard下verify_t16全部绑定通过，未启动服务；这里只接受T16 D14，T17/D17仍待验收。

startup CPU cb6ef8de834d自然失败：187 PASS/1 FAIL，test_t20_does_not_upgrade_a_bare_permit_json依赖既有t20_r041_sample4_closure.py未进入source archive。旧失败stage已555/444封存，未修改。packager只补这一个既有依赖，实际新版本t17_startup_cpu_1dd61d5458fe已开始，local session84952，尚无成功报告。没有新增读取器、fixture或GPU启动。

新版startup CPU 1dd61d5458fe完成：Linux188 PASS，无跳过；success/request_error/stop_error三种既有生命周期fixture replay全PASS；结构校验returncode0。报告/data2/FreeToken/runs/dev_D16/t17_startup_cpu_1dd61d5458fe/startup_cpu_report.json SHAe0e09defae6cf52b0670bde475122a41696ab37a92eaa25b0cad4d0d5a074a82。source_execution_ready=false/model_admitted=false，须实际GPU启动前R复核；不以CPU结果宣称T17通过。local session84952已exit0，不重启。实际R038冻结source、launcher和batch绑定已交R；待14组原始复算许可就绪后一次完成启动前复核。
