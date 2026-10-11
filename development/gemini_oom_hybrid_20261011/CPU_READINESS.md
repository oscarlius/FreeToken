# Gemini OOM & Hybrid Window CPU 就绪报告 (P1-G6)

- 指令依据：`plan/GEMINI_OOM_HYBRID_20261011.md`（SHA256 `043f18f079aaa4de8ad2f7888a3d92307bc1d37f589f98c9dc1007b2fbf0255c`，两侧核对一致）
- 工作目录：`/data2/FreeToken/development/gemini_oom_hybrid_20261011/`（本地镜像同步）
- 就绪时间：2026-10-11 15:36+08:00
- 状态：**P1 阶段（纯 CPU 准备）全部完成并通过验收**。生产 481（RESTORE481-MORNING-20261011-09）未受任何影响，仍持续服务。

---

## 1. G1 至 G5 交付清单与 SHA256

| 阶段 | 交付物 | 权限 | SHA256 | 说明 |
|---|---|---|---|---|
| P1-G1 | `OOM_MEMORY_MODEL.md` | 0644 | `c3791d59bdc1b335831d0437feb288be65e8dc645aac497e4fbd9ba31e5b56ea` | 显存解析模型、冷请求分项、碎片模型与阶梯预登记预测 |
| P1-G2 | `inputs/inputs_X.jsonl` | 0644 | `f63b3623bbb0ab10b0001d68a20138fb15a0ce8893f3a2d4c0202825a22a1162` | X 阶段单路/两路测试输入（2 条请求） |
| P1-G2 | `inputs/L64.json` | 0644 | `261d50af3092dfabd20514e6ad06393be4e5265a1e2b9d95c158746946356618` | 阶梯 L64：259,713 字符，64,000 prompt token |
| P1-G2 | `inputs/L80.json` | 0644 | `274620ae611b5b3e0e78589aff61e90e9ff8de1c469983f1bb7cc7d13939c683` | 阶梯 L80：320,524 字符，80,000 prompt token |
| P1-G2 | `inputs/L87.json` | 0644 | `84b3f62036409f719f759b167836378a7692c90f99b78f342450975a31c8959e` | 阶梯 L87：345,089 字符，87,100 prompt token（录制值，diff=0） |
| P1-G2 | `inputs/L95.json` | 0644 | `464dedd2d002cfaa1a28a365bed2c80995e00474b5a918e1ac391130432ef6f7` | 阶梯 L95：15 轮真实消息，95,352 prompt token（录制值，diff=0） |
| P1-G2 | `INPUTS.json` | 0644 | `252057fd4ff16819bbebcad89e29a8994ea9339ae1aeb4518024d21df630a4a1` | 输入源路径、字符数、token 数、截取方式与 KV 断言记录 |
| P1-G3 | `oh_window.py` | 0755 | `68680962baaa805568761abaf267dea352e0b45a929655d4fd41d553ab1b2751` | 窗口总控工装：argv 门禁、生命周期、AIPerf、SDK 阶梯、比对与 D0 统计 |
| P1-G3 | `PLAN.json` | 0644 | `862a623504d48332b328dd1a4638c2ebc80e34ced2a679284cb24513f0f5108d` | 窗口 6 服务执行计划（S1-S6） |
| P1-G3 | `test_oh_window.py` | 0644 | `4078ae2add3c121363460fff8034aa6e0e26e5032fd9862585292d8a025921bf` | 工装单元测试（18 个测试用例全部通过） |
| P1-G4 | `restore10/` | 0444 | — | 晚间恢复包（12 个审核源文件 + DEPLOYMENT_APPROVAL + ROOT_FINAL_REVIEW + SOURCE_MANIFEST + README） |
| P1-G4 | `restore10/DEPLOYMENT_APPROVAL.json` | 0444 | `16529ccb4e09cb1d2de7d70008e2ea6ecff49d94d690d00f915658d11f7fef8b` | 恢复包审批单（审批号 RESTORE481-MORNING-20261011-10，明早 9 点观察截止） |
| P1-G4 | `restore10/ROOT_FINAL_REVIEW.json` | 0444 | `6e77f7f995ba2060f8995f1dc9a6b1ece5caf8a3d8732d7813435644950c7a6f` | 终审签署（绑定本指令 SHA 043f18f079aa…，pending=false，verdict=PASS） |
| P1-G4 | `restore10/SOURCE_MANIFEST.json` | 0444 | `3972f67dd738d86e9342f14a05b6ae6fe121a61c16441d8df7cf8133a062ff07` | 源码清单 |
| P1-G4 | `restore10/observe_overnight.py` | 0444 | `994bb864a850097967ed2c12ff4c2baa5c4f4f4aa93b8befe12315f6352062ff` | 观察器脚本（身份 -10 替换） |
| P1-G4 | `restore10/test_cpu_orchestration.py` | 0444 | `d67bb508760b69f876d6edd13d7eb9919ac2eb55c63e1170bc5f6713d4a866ee` | CPU 编排测试（身份 -10 替换） |
| P1-G4 | `diff_restore10.txt` | 0644 | `135e8e21e6b4be060ffae41e2973a42ae8bf5640461b2759a5efe5bc1e808baf` | 与 restore09 的差异比对（仅允许的 6 处身份与派生项） |
| P1-G5 | `stub_server.py` | 0755 | `bd28b6ce6b7f0ce2309c4a6912b025ce43f83783c7b1cd33f051a306996df04e` | 真实演练纯标准库桩服务（支持确定/非确定输出、OOM 模拟、moe_cache_size 行打印） |
| P1-G5 | `REHEARSAL.json` | 0444 | `a980296e6f2a42f9dc8a889ed44d9d6a30ba7324ae359d763876622a059481f7` | R1-R4 演练命令、配置与回执记录 |

---

## 2. 单元测试与门链验证输出

### 2.1 工装单元测试 (`test_oh_window.py`)
```
CUDA_VISIBLE_DEVICES= /data2/FreeToken/venv/bin/python -B -m pytest test_oh_window.py -q
..................                                                       [100%]
18 passed in 0.04s
```
涵盖：argv 差异门（放行合法 3 类差异、拦截未授权差异）、OOM 判定、输出文本拼接提取、compare 首异字符定位、KV 断言、时限控制、D0 失误率计算。

### 2.2 恢复包 CPU 测试与门链 (`restore10/test_cpu_orchestration.py`)
```
cd /data2/FreeToken/development/gemini_oom_hybrid_20261011/restore10
CUDA_VISIBLE_DEVICES= /data2/FreeToken/venv/bin/python -B -m pytest test_cpu_orchestration.py -q
.......                                                                  [100%]
7 passed in 0.02s

CUDA_VISIBLE_DEVICES= /data2/FreeToken/venv/bin/python -B -c "import approved_attempt as a; d=a.load(); print('GATE_CHAIN_PASS', d['approval_id'], d['observation_until'])"
GATE_CHAIN_PASS RESTORE481-MORNING-20261011-10 2026-10-12T09:00:00+08:00
```
完整验证 ROOT_FINAL_REVIEW 与 SOURCE_MANIFEST 的哈希链。

### 2.3 真实入口演练 R1–R4 结果（`REHEARSAL.json`）
- **R1 正向演练**：确定输出，T > L95。6 个服务全部完成；S3/S4/S5 共 7 对 compare 全部 identical=True；S1 阶梯（L64, L80, L87, L95）全部 PASS；S2 阶梯（L95, L87）全部 PASS；summary.json 生成正确。
- **R2 反向一演练**：输出不确定（第 100 字符按调用变化）。HR 服务的 compare 全部判不同且首个不同字符精确为 100。
- **R3 反向二演练**：T=330,000 介于 L80 与 L87 之间。S1 阶梯在 L87 判 OOM 并立即停止，serve.log 截取至 oom_L87.log，恢复耗时 10.02s；S2 第一级 L95 立即判 OOM 并停止。
- **R4 清理验证**：各服务均生成 `cleanup.json`，`proved=true`，`remaining_members=[]`；清理后 8123 端口立即可绑定，无任何遗留进程。

---

## 3. 预登记预测引用

引用 `OOM_MEMORY_MODEL.md`（SHA256 `c3791d59bdc1b335831d0437feb288be65e8dc645aac497e4fbd9ba31e5b56ea`）：
- 干净服务极限：$N_{\text{fresh}} = 96,000$ tokens
- 碎片服务极限：$N_{\text{frag}} = 84,000$ tokens
- 阶梯结果预登记：
  - **S1 (O-warm，含碎片)**：L64 PASS，L80 PASS，L87 OOM，L95 跳过。
  - **S2 (O-fresh，干净服务)**：L95 PASS，L87 PASS。
  - **OOM 恢复时间**：约 8–10 秒重新进入 serving。
- **可复现 Hybrid 预登记（S3/S4/S5）**：`--moe-hybrid-max-fetch 0` 消除取数不确定性后，同一服务内重复请求文本比对 100% 相同（首异字符为 None）。
- **D0 埋点预登记（S6）**：两路请求失误率约为 29% ± 3%。

---

## 4. PLAN.json 全文

```json
{
  "schema": "gemini_oom_hybrid_plan/v1",
  "created_at": "2026-10-11T15:00:00+08:00",
  "window_limit_seconds": 6600,
  "service_cutoff_reserve_seconds": 900,
  "baseline_freeze_path": "/data2/FreeToken/development/kimi_phase2_20261011/hybrid_verify/BASELINE_OWNER_FREEZE.json",
  "services": [
    {
      "name": "S1",
      "display_name": "O-warm",
      "type": "offload",
      "extra_argv": [],
      "extra_env": {},
      "phases": [
        {"type": "warmup", "name": "warmup"},
        {"type": "x_aiperf", "name": "x_single_1", "concurrency": 1, "request_count": 1},
        {"type": "x_aiperf", "name": "x_single_2", "concurrency": 1, "request_count": 1},
        {"type": "x_aiperf", "name": "x_two_1", "concurrency": 2, "request_count": 2},
        {"type": "x_aiperf", "name": "x_two_2", "concurrency": 2, "request_count": 2},
        {"type": "ladder", "name": "ladder", "steps": ["L64", "L80", "L87", "L95"]}
      ]
    },
    {
      "name": "S2",
      "display_name": "O-fresh",
      "type": "offload",
      "extra_argv": [],
      "extra_env": {},
      "phases": [
        {"type": "ladder", "name": "ladder", "steps": ["L95", "L87"]}
      ]
    },
    {
      "name": "S3",
      "display_name": "HR-a",
      "type": "hybrid",
      "extra_argv": ["--moe-hybrid-max-fetch", "0"],
      "extra_env": {},
      "phases": [
        {"type": "warmup", "name": "warmup"},
        {"type": "x_aiperf", "name": "x_single_1", "concurrency": 1, "request_count": 1},
        {"type": "x_aiperf", "name": "x_single_2", "concurrency": 1, "request_count": 1},
        {"type": "x_aiperf", "name": "x_single_3", "concurrency": 1, "request_count": 1},
        {"type": "x_aiperf", "name": "x_two_1", "concurrency": 2, "request_count": 2},
        {"type": "x_aiperf", "name": "x_two_2", "concurrency": 2, "request_count": 2},
        {"type": "compare", "name": "compare_single_1_2", "target_a": "S3/x_single_1", "target_b": "S3/x_single_2"},
        {"type": "compare", "name": "compare_single_1_3", "target_a": "S3/x_single_1", "target_b": "S3/x_single_3"},
        {"type": "compare", "name": "compare_two_1_2", "target_a": "S3/x_two_1", "target_b": "S3/x_two_2"}
      ]
    },
    {
      "name": "S4",
      "display_name": "HR-b",
      "type": "hybrid",
      "extra_argv": ["--moe-hybrid-max-fetch", "0"],
      "extra_env": {
        "FREETOKEN_CPU_MOE_NO_VNNI": "1"
      },
      "phases": [
        {"type": "warmup", "name": "warmup"},
        {"type": "x_aiperf", "name": "x_single_1", "concurrency": 1, "request_count": 1},
        {"type": "x_aiperf", "name": "x_single_2", "concurrency": 1, "request_count": 1},
        {"type": "x_aiperf", "name": "x_single_3", "concurrency": 1, "request_count": 1},
        {"type": "x_aiperf", "name": "x_two_1", "concurrency": 2, "request_count": 2},
        {"type": "x_aiperf", "name": "x_two_2", "concurrency": 2, "request_count": 2},
        {"type": "compare", "name": "compare_single_1_2", "target_a": "S4/x_single_1", "target_b": "S4/x_single_2"},
        {"type": "compare", "name": "compare_single_1_3", "target_a": "S4/x_single_1", "target_b": "S4/x_single_3"},
        {"type": "compare", "name": "compare_two_1_2", "target_a": "S4/x_two_1", "target_b": "S4/x_two_2"}
      ]
    },
    {
      "name": "S5",
      "display_name": "HR-b-fresh",
      "type": "hybrid",
      "extra_argv": ["--moe-hybrid-max-fetch", "0"],
      "extra_env": {
        "FREETOKEN_CPU_MOE_NO_VNNI": "1"
      },
      "phases": [
        {"type": "x_aiperf", "name": "x_single_1", "concurrency": 1, "request_count": 1},
        {"type": "compare", "name": "compare_S5_S4_single_1", "target_a": "S5/x_single_1", "target_b": "S4/x_single_1"}
      ]
    },
    {
      "name": "S6",
      "display_name": "H-stats",
      "type": "hybrid",
      "extra_argv": [],
      "extra_env": {
        "FT_DEV_D0": "1",
        "FT_DEV_D0_PATH": "<SERVICE_OUT>/d0"
      },
      "phases": [
        {"type": "x_aiperf", "name": "x_two_1", "concurrency": 2, "request_count": 2},
        {"type": "d0_read", "name": "d0_read"}
      ]
    }
  ]
}
```
